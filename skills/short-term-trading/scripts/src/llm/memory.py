"""交易记忆模块：记录 LLM 每次决策及结果。"""

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional


class TradeRecord:
    def __init__(self, action: str, entry_price: float, confidence: float, reasoning: str = "",
                 exit_price: Optional[float] = None, pnl_pct: Optional[float] = None):
        self.time = datetime.now()
        self.action = action
        self.entry_price = entry_price
        self.confidence = confidence
        self.reasoning = reasoning
        self.exit_price = exit_price
        self.pnl_pct = pnl_pct

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat(),
            "action": self.action,
            "entry_price": self.entry_price,
            "confidence": self.confidence,
            "reasoning": self.reasoning[:200],
            "exit_price": self.exit_price,
            "pnl_pct": self.pnl_pct,
        }

    def short_summary(self) -> str:
        pnl_str = f" PnL:{self.pnl_pct:+.2f}%" if self.pnl_pct is not None else ""
        return f"[{self.time.strftime('%m-%d %H:%M')}] {self.action.upper()} @ {self.entry_price} c:{self.confidence:.2f}{pnl_str}"


class TradingMemory:
    def __init__(self, max_records: int = 20, persist_path: str = "memory/trades.json"):
        self.max_records = max_records
        self.persist_path = Path(persist_path)
        self.records: deque[TradeRecord] = deque(maxlen=max_records)
        self._load()

    def add(self, record: TradeRecord):
        self.records.append(record)
        self._save()

    def recent_summary(self, n: int = 10) -> str:
        recent = list(self.records)[-n:]
        if not recent:
            return "No trade history yet"
        lines = ["Recent trades:"]
        for r in recent:
            lines.append(f"  {r.short_summary()}")
        wins = sum(1 for r in recent if r.pnl_pct is not None and r.pnl_pct > 0)
        losses = sum(1 for r in recent if r.pnl_pct is not None and r.pnl_pct < 0)
        if wins + losses > 0:
            wr = wins / (wins + losses) * 100
            lines.append(f"  Win rate: {wins}/{wins+losses} ({wr:.0f}%)")
        return "\n".join(lines)

    def consecutive_losses(self) -> int:
        count = 0
        for r in reversed(self.records):
            if r.pnl_pct is not None and r.pnl_pct < 0:
                count += 1
            else:
                break
        return count

    def _save(self):
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self.records]
        self.persist_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _load(self):
        if self.persist_path.exists():
            try:
                data = json.loads(self.persist_path.read_text())
                for d in data[-self.max_records:]:
                    r = TradeRecord(
                        action=d["action"], entry_price=d["entry_price"],
                        confidence=d["confidence"], reasoning=d.get("reasoning", ""),
                        exit_price=d.get("exit_price"), pnl_pct=d.get("pnl_pct"),
                    )
                    self.records.append(r)
            except Exception:
                pass
