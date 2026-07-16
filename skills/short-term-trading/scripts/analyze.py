#!/usr/bin/env python3
"""短线交易 LLM 分析决策 CLI。

用法:
  python analyze.py --mock                       # 模拟演示（无需 API）
  python analyze.py --symbol ETH-USDT --tf 15m  # 真实分析（需 .env）
  python analyze.py --symbol BTC-USDT --confirm-order  # 真实下单（需授权）

绝不默认自动下单。--confirm-order 才会调用交易所。
"""

import argparse
import sys
from pathlib import Path

# 让 scripts/ 可作为包根被导入
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from src.config import config                      # noqa: E402
from src.exchange.okx_client import OKXClient    # noqa: E402
from src.data.data_fetcher import DataFetcher    # noqa: E402
from src.strategy.llm_strategy import LLMStrategy  # noqa: E402
from src.llm.base import LLMClient               # noqa: E402
from src.report import render_report             # noqa: E402


class FakeLLM(LLMClient):
    """演示用假 LLM：模拟一个合理的开仓决策（仅在 mock 且无真实 LLM Key 时启用）。"""

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if "You currently HOLD" in user_prompt:
            return '{"decision":"hold","reason":"演示假LLM：趋势未破，继续持有观察","close_pct":0}'
        return ('{"decision":"open_long","direction":"long",'
                '"sl_atr_multiplier":1.5,"tp_atr_multiplier":3.0,'
                '"reason":"演示假LLM：5m EMA9上穿EMA21且斜率向上，量能配合，短线偏多，按ATR设止损止盈"}')


def parse_args():
    p = argparse.ArgumentParser(description="短线交易 LLM 分析决策工具")
    p.add_argument("--symbol", default=config.SYMBOL, help="交易对，如 BTC-USDT")
    p.add_argument("--timeframe", "--tf", dest="timeframe", default=config.TIMEFRAME, help="主周期，如 5m/15m")
    p.add_argument("--aux", default=config.AUX_TIMEFRAME, help="辅助周期，如 15m")
    p.add_argument("--macro4h", default=config.MACRO_TIMEFRAME_4H, help="宏观周期 4h")
    p.add_argument("--macro1d", default=config.MACRO_TIMEFRAME_1D, help="宏观周期 1d")
    p.add_argument("--provider", default="", help="LLM 厂商 openai/claude/deepseek（覆盖 .env）")
    p.add_argument("--model", default="", help="模型名（覆盖 .env）")
    p.add_argument("--mock", action="store_true", help="模拟模式，用本地随机行情，无需 API")
    p.add_argument("--confirm-order", action="store_true",
                   help="真实下单（高危，需 OKX API Key 且用户明确授权）")
    return p.parse_args()


def main():
    args = parse_args()

    config.apply_cli(symbol=args.symbol, timeframe=args.timeframe,
                     aux=args.aux, macro4h=args.macro4h, macro1d=args.macro1d)
    if args.provider:
        config.LLM_PROVIDER = args.provider
    if args.model:
        config.LLM_MODEL = args.model

    print(f"[*] 模式: {'模拟(mock)' if args.mock else '真实'} | "
          f"交易对: {config.SYMBOL} | 主周期: {config.TIMEFRAME}")
    print(f"[*] LLM: {config.LLM_PROVIDER} / {config.LLM_MODEL}")

    if not args.mock:
        if not config.OKX_API_KEY:
            print("[!] 未配置 OKX_API_KEY，无法获取真实行情。请复制 .env.example 为 .env 并填写。")
            print("    或使用 --mock 跑演示。")
            sys.exit(1)
        if not (config.OPENAI_API_KEY or config.CLAUDE_API_KEY or config.DEEPSEEK_API_KEY):
            print("[!] 未配置任何 LLM API Key（OPENAI/CLAUDE/DEEPSEEK）。")
            sys.exit(1)

    client = OKXClient(mock=args.mock)
    fetcher = DataFetcher(client)

    # mock 且未配 LLM Key → 用 FakeLLM 演示完整流程
    strategy = LLMStrategy(fetcher=fetcher)
    if args.mock and not (config.OPENAI_API_KEY or config.CLAUDE_API_KEY or config.DEEPSEEK_API_KEY):
        from src.llm.provider import create_llm_client
        strategy.client = FakeLLM()

    try:
        decision = strategy.decide(fetcher=fetcher)
    except Exception as e:
        print(f"[!] 决策过程出错: {e}")
        sys.exit(1)

    price = float(client.fetch_ticker().get("last", 0))
    print(render_report(decision, config.SYMBOL, price, config.TIMEFRAME, args.mock))

    # ---- 下单逻辑（安全边界）----
    if decision.get("decision") in ("open_long", "open_short"):
        side = "buy" if decision["decision"] == "open_long" else "sell"
        if args.confirm_order:
            if args.mock:
                print("[!] 模拟模式下 --confirm-order 不会真实下单（仅打印）。")
            if not config.OKX_API_KEY:
                print("[!] 无 OKX_API_KEY，无法真实下单。")
                sys.exit(1)
            print(f"[*] 真实下单: {side} {config.SINGLE_TRADE_SIZE} {config.SYMBOL}")
            ok = input("  确认真实下单? 输入 YES 继续: ").strip().upper()
            if ok == "YES":
                client.create_market_order(side, config.SINGLE_TRADE_SIZE)
                strategy.record_open(decision, price)
                print("[*] 已下单并记入本地记忆。")
            else:
                print("[*] 已取消下单。")
        else:
            print("[*] 未加 --confirm-order，跳过下单。信号仅供参考。")
    elif decision.get("decision") in ("close", "reduce") and strategy.current_position:
        if args.confirm_order and not args.mock and config.OKX_API_KEY:
            side = "sell" if strategy.current_position.action == "open_long" else "buy"
            ok = input(f"  确认平仓({side})? 输入 YES 继续: ").strip().upper()
            if ok == "YES":
                client.create_market_order(side, config.SINGLE_TRADE_SIZE)
                strategy.record_exit(price)
                print("[*] 已平仓。")
        else:
            print("[*] 持仓管理信号（close/reduce）仅建议，未执行。")


if __name__ == "__main__":
    main()
