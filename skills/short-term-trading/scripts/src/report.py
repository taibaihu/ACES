"""把决策 dict 渲染成人类可读的短线信号报告。"""


SYM_MAP = {"open_long": "开多 OPEN_LONG", "open_short": "开空 OPEN_SHORT",
           "hold": "观望 HOLD", "close": "平仓 CLOSE", "reduce": "减仓 REDUCE"}


def render_report(decision: dict, symbol: str, price: float, tf: str, mock: bool) -> str:
    dec = decision.get("decision", "hold")
    label = SYM_MAP.get(dec, dec)
    line = "=" * 50
    head = f"═══ 短线信号 {symbol} @ {price:.1f} ({tf}) ═══"
    out = [head, line]

    if dec in ("open_long", "open_short"):
        direction = decision.get("direction", "")
        entry = decision.get("entry")
        sl = decision.get("sl")
        tp1 = decision.get("tp1")
        tp2 = decision.get("tp2")
        rr = decision.get("rr_ratio", 0)
        sl_dist = abs(entry - sl) if entry and sl else 0
        tp_dist = abs(tp1 - entry) if entry and tp1 else 0
        out.append(f"决策: {label}")
        out.append(f"入场: {entry}    "
                   f"SL: {sl} ({-sl_dist:+.1f}, {decision.get('sl_atr_multiplier')}×ATR)")
        out.append(f"TP1: {tp1} ({tp_dist:+.1f}, {decision.get('tp_atr_multiplier')}×ATR)"
                   f"   TP2: {tp2}")
        out.append(f"R:R = 1:{rr}")
    else:
        out.append(f"决策: {label}")

    out.append(line)
    out.append(f"理由: {decision.get('reason', '')}")
    out.append(line)
    if mock:
        out.append("[模拟模式] 未真实下单。真实操作请在 OKX 手动执行或加 --confirm-order。")
    else:
        out.append("[真实分析模式] 下单需手动在 OKX 操作，或用 --confirm-order 显式授权。")
    return "\n".join(out)
