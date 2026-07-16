"""LLM 驱动交易策略：双模式决策（开仓 / 持仓管理）。"""

import json
import re
import time
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from ..config import config
from ..data.data_fetcher import DataFetcher
from ..llm.base import LLMClient
from ..llm.memory import TradeRecord, TradingMemory
from ..llm.provider import create_llm_client
from ..llm.prompts import (
    SYSTEM_PROMPT, PROMPT_MODE_A, PROMPT_MODE_B,
    build_market_context, build_position_block,
)
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


def _extract_json_fragment(text: str) -> str:
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced[0]
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return m.group(1)
    return text


def _repair_json(s: str) -> str:
    out = s.strip()
    out = re.sub(r",\s*([}\]])", r"\1", out)
    return out


def parse_llm_response(text: str) -> dict:
    if not text:
        return {"decision": "hold", "reason": "LLM 返回空"}
    frag = _extract_json_fragment(text)
    candidates = [frag, _repair_json(frag)]
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    logger.warning(f"无法解析 LLM 输出: {text[:200]}")
    return {"decision": "hold", "reason": "解析失败"}


class LLMStrategy:
    def __init__(self, client: Optional[LLMClient] = None, memory: Optional[TradingMemory] = None,
                 fetcher: Optional[DataFetcher] = None):
        self.client = client or create_llm_client()
        self.memory = memory or TradingMemory()
        self.fetcher = fetcher
        self._current_position: Optional[TradeRecord] = None
        self._cooldown_until: Optional[float] = None

    # ---- 外部调用 ----
    def decide(self, fetcher: Optional[DataFetcher] = None) -> dict:
        fetcher = fetcher or self.fetcher
        if fetcher is None:
            return {"decision": "hold", "reason": "无数据获取器"}

        main_df = fetcher.fetch_features(timeframe=config.TIMEFRAME, limit=300)
        if main_df.empty:
            return {"decision": "hold", "reason": "无主周期数据"}

        aux_df = fetcher.fetch_features(timeframe=config.AUX_TIMEFRAME, limit=300)
        macro_4h = fetcher.fetch_features(timeframe=config.MACRO_TIMEFRAME_4H, limit=120)
        macro_1d = fetcher.fetch_features(timeframe=config.MACRO_TIMEFRAME_1D, limit=120)

        ticker = fetcher.client.fetch_ticker()
        if not ticker:
            return {"decision": "hold", "reason": "无行情"}

        price = float(ticker.get("last", main_df.iloc[-1]["close"]))
        last = main_df.iloc[-1]
        atr = float(last["atr_14"])

        if self._cooldown_until and time.time() < self._cooldown_until:
            remain = int((self._cooldown_until - time.time()) / 60)
            return {"decision": "hold", "direction": None, "entry": None,
                    "sl": None, "tp1": None, "tp2": None, "rr_ratio": 0.0,
                    "reason": f"连亏冷却中，剩余约 {remain} 分钟，强制观望降温"}
        if self._cooldown_until is None and self.memory.consecutive_losses() >= 3:
            self._cooldown_until = time.time() + 30 * 60
            return {"decision": "hold", "direction": None, "entry": None,
                    "sl": None, "tp1": None, "tp2": None, "rr_ratio": 0.0,
                    "reason": "连续 3 笔止损，启动 30 分钟情绪降温，强制观望"}
        if self._cooldown_until and time.time() >= self._cooldown_until:
            self._cooldown_until = None

        has_position = self._current_position is not None
        if not has_position:
            gate = self._gatekeeper_open(main_df, price, atr)
            if gate is not None:
                logger.info(f"Gatekeeper 拦截（无开仓信号）：{gate}")
                return {"decision": "hold", "direction": None, "entry": None,
                        "sl": None, "tp1": None, "tp2": None, "rr_ratio": 0.0,
                        "reason": f"本地预筛：{gate}"}

        positions = []
        if has_position:
            p = self._current_position
            unreal = (price - p.entry_price) / p.entry_price * 100
            if p.action in ("open_short", "sell", "short"):
                unreal = -unreal
            positions.append({
                "side": p.action, "amount": config.SINGLE_TRADE_SIZE,
                "entry_price": p.entry_price, "unrealized_pnl": unreal,
            })

        tf_main = self._tf_main_text(main_df, price)
        tf_aux = self._tf_aux_text(aux_df)
        tf_macro = self._tf_macro_text(macro_4h, macro_1d)

        context = build_market_context(
            symbol=config.SYMBOL, price=price,
            tf_main=tf_main, tf_aux=tf_aux, tf_macro=tf_macro,
            positions=positions, memory_text=self.memory.recent_summary(10),
        )

        if has_position:
            mode_prompt = PROMPT_MODE_B.format(position_block=build_position_block(positions))
        else:
            mode_prompt = PROMPT_MODE_A

        full_user = mode_prompt + "\n\n" + context

        logger.info(f"调用 LLM 决策（{'MODE B 持仓管理' if has_position else 'MODE A 开仓'}）...")
        raw = self.client.chat(SYSTEM_PROMPT, full_user)
        decision = parse_llm_response(raw)
        decision = self._normalize(decision, price, main_df, has_position)
        logger.info(f"LLM 决策: {decision.get('decision')} | 原因: {decision.get('reason','')[:80]}")
        return decision

    def _gatekeeper_open(self, main_df: "pd.DataFrame", price: float, atr: float) -> Optional[str]:
        last = main_df.iloc[-1]
        prev = main_df.iloc[-2]

        rsi = float(last["rsi_14"])
        ema9 = float(last["ema_9"])
        ema21 = float(last["ema_21"])
        ema9_prev = float(prev["ema_9"])
        bb_upper = float(last["bb_upper"])
        bb_lower = float(last["bb_lower"])

        # 1. 波动率否决（前置，最优先，阈值从 config 读）
        window = main_df.iloc[-12:]
        swing = float(window["high"].max() - window["low"].min())
        atr_min = config.GATEKEEPER_ATR_MIN
        swing_min = config.GATEKEEPER_SWING_MIN
        if atr < atr_min:
            return f"市场波动率极低（死鱼市，ATR={atr:.1f}<{atr_min:.0f}），强行拦截"
        if swing < swing_min:
            return f"市场波幅极小（近12根振幅={swing:.1f}<{swing_min:.0f}），死鱼市拦截"

        # 2. C1 HARD：RSI 极端
        if rsi >= 70:
            return "RSI 超买(>=70)，无做多苗头"
        if rsi <= 30:
            return "RSI 超卖(<=30)，无做空苗头"

        # 3. 顺势苗头（双线交叉 + 斜率拐头）
        ema9_slope = ema9 - ema9_prev
        bull_stack_light = (ema9 > ema21) and (ema9_slope > 0)
        bear_stack_light = (ema9 < ema21) and (ema9_slope < 0)

        # 4. 均值回归苗头
        mean_rev_long = (price <= bb_lower * 1.001) and rsi < 40
        mean_rev_short = (price >= bb_upper * 0.999) and rsi > 60

        if bull_stack_light or bear_stack_light or mean_rev_long or mean_rev_short:
            return None
        return "无均线交叉/布林带触边信号，横盘观望"

    def record_open(self, decision: dict, price: float):
        side = "open_long" if decision.get("direction") == "long" else "open_short"
        entry = self._to_float(decision.get("entry"), price)
        rec = TradeRecord(
            action=side, entry_price=entry,
            confidence=float(decision.get("confidence", 0.6)),
            reasoning=decision.get("reason", ""),
        )
        self.memory.add(rec)
        self._current_position = rec

    def record_exit(self, exit_price: float):
        if self._current_position is None:
            return
        p = self._current_position
        pnl = (exit_price - p.entry_price) / p.entry_price * 100
        if p.action in ("open_short", "sell", "short"):
            pnl = -pnl
        p.exit_price = exit_price
        p.pnl_pct = pnl
        self.memory.add(p)
        logger.info(f"平仓 | PnL: {pnl:+.2f}% | 入场: {p.entry_price} -> 出场: {exit_price}")
        self._current_position = None

    @property
    def current_position(self):
        return self._current_position

    # ---- 内部：上下文 ----
    def _tf_main_text(self, df: pd.DataFrame, price: float) -> dict:
        last = df.iloc[-1]
        lines = [
            f"  Price: {price:.1f}",
            f"  EMA9:  {last['ema_9']:.1f}",
            f"  EMA21: {last['ema_21']:.1f}",
            f"  EMA50: {last['ema_50']:.1f}",
            f"  EMA200:{last['ema_200']:.1f}",
            f"  RSI14: {last['rsi_14']:.1f}",
            f"  ATR14: {last['atr_14']:.1f}",
            f"  MACD:  {last['macd']:.2f} / Signal {last['macd_signal']:.2f} / Diff {last['macd_diff']:.2f}",
            f"  KDJ:   K {last['k']:.1f} D {last['d']:.1f} J {last['j']:.1f}",
            f"  BB:    upper {last['bb_upper']:.1f} lower {last['bb_lower']:.1f}",
            f"  VolRatio: {last['volume_ratio']:.2f}",
        ]
        recent = df["close"].tail(12).round(1).astype(str)
        lines.append("  Recent closes: " + " -> ".join(recent.values))
        return {"text": "\n".join(lines)}

    def _tf_aux_text(self, df: pd.DataFrame) -> dict:
        if df.empty:
            return {"text": "  (no data)"}
        last = df.iloc[-1]
        lines = [
            f"  EMA9:  {last['ema_9']:.1f}",
            f"  EMA21: {last['ema_21']:.1f}",
            f"  RSI14: {last['rsi_14']:.1f}",
            f"  MACD:  {last['macd']:.2f} / Signal {last['macd_signal']:.2f}",
        ]
        return {"text": "\n".join(lines)}

    def _tf_macro_text(self, df4h: pd.DataFrame, df1d: pd.DataFrame) -> dict:
        lines = []
        for name, df in (("4H", df4h), ("1D", df1d)):
            if df.empty:
                lines.append(f"  {name}: (no data)")
                continue
            last = df.iloc[-1]
            trend = "UP" if last["ema_9"] > last["ema_50"] else "DOWN"
            lines.append(f"  {name}: EMA9 {last['ema_9']:.1f} / EMA50 {last['ema_50']:.1f} -> {trend}, RSI {last['rsi_14']:.1f}")
        return {"text": "\n".join(lines)}

    # ---- 内部：归一化 ----
    def _normalize(self, decision: dict, price: float, main_df: pd.DataFrame, has_position: bool) -> dict:
        last = main_df.iloc[-1]
        atr = float(last["atr_14"])
        decision.setdefault("reason", "")

        if not has_position:
            dec = str(decision.get("decision", "hold")).lower()
            direction = str(decision.get("direction", "")).lower()
            if dec not in ("open_long", "open_short", "hold"):
                dec = "hold"
            if dec == "hold":
                return {"decision": "hold", "direction": None, "entry": None,
                        "sl": None, "tp1": None, "tp2": None, "rr_ratio": 0.0,
                        "reason": decision.get("reason", "观望")}

            entry = float(price)
            sl_mult = self._to_float(decision.get("sl_atr_multiplier"), config.STOP_LOSS_ATR_MULT)
            tp_mult = self._to_float(decision.get("tp_atr_multiplier"),
                                     config.STOP_LOSS_ATR_MULT * config.MIN_RR_RATIO)
            sl_mult = max(1.0, sl_mult)
            tp_mult = max(tp_mult, sl_mult * config.MIN_RR_RATIO)

            if direction == "long":
                sl = entry - sl_mult * atr
                tp1 = entry + tp_mult * atr
            else:
                sl = entry + sl_mult * atr
                tp1 = entry - tp_mult * atr
            tp2 = tp1 + (tp1 - entry)

            sl_dist = abs(entry - sl)
            tp_dist = abs(tp1 - entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0.0
            return {
                "decision": dec, "direction": direction, "entry": round(entry, 1),
                "sl": round(sl, 1), "tp1": round(tp1, 1), "tp2": round(tp2, 1),
                "rr_ratio": round(rr, 2),
                "sl_atr_multiplier": round(sl_mult, 2), "tp_atr_multiplier": round(tp_mult, 2),
                "reason": decision.get("reason", ""),
            }
        else:
            dec = str(decision.get("decision", "hold")).lower()
            if dec not in ("hold", "close", "reduce"):
                dec = "hold"
            close_pct = int(decision.get("close_pct", 0) or 0)
            if dec == "hold":
                close_pct = 0
            close_pct = max(0, min(100, close_pct))
            return {"decision": dec, "reason": decision.get("reason", ""), "close_pct": close_pct}

    @staticmethod
    def _to_float(v, default):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default
