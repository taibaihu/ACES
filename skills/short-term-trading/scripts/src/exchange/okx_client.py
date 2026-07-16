"""OKX 交易所 API 客户端封装（基于 ccxt）。

支持两种模式：
  - 真实模式：需要 OKX_API_KEY / SECRET / PASSPHRASE
  - 模拟模式（mock=True）：使用本地生成的随机游走 K 线 + 模拟 ticker，无需任何 API
"""

from typing import Optional
import random
from datetime import datetime, timedelta

import ccxt
import pandas as pd

from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class OKXClient:
    def __init__(self, use_sandbox: bool = False, mock: bool = False):
        self.mock = mock
        self.exchange = None
        if not mock:
            self.exchange = ccxt.okx({
                "apiKey": config.OKX_API_KEY,
                "secret": config.OKX_SECRET_KEY,
                "password": config.OKX_PASSPHRASE,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},  # 永续合约
            })
            if use_sandbox:
                self.exchange.set_sandbox_mode(True)

    # ---- 模拟数据 ----
    def _mock_ohlcv(self, timeframe: str, limit: int) -> pd.DataFrame:
        tf_min = self._tf_to_minutes(timeframe)
        end = datetime.now()
        idx = [end - timedelta(minutes=tf_min * i) for i in range(limit)][::-1]
        base = 64000.0
        rows = []
        price = base
        for _ in range(limit):
            price *= (1 + random.uniform(-0.0035, 0.0035))
            high = price * (1 + random.uniform(0, 0.003))
            low = price * (1 - random.uniform(0, 0.003))
            vol = random.uniform(50, 200)
            rows.append({
                "timestamp": idx.pop(0),
                "open": price,
                "high": max(high, price),
                "low": min(low, price),
                "close": price,
                "volume": vol,
            })
        df = pd.DataFrame(rows).set_index("timestamp")
        return df

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
        n, unit = int(tf[:-1]), tf[-1]
        return n * (60 if unit == "h" else 1)

    # ---- 行情 ----
    def fetch_ohlcv(self, symbol: str = "", timeframe: str = "", limit: int = 500) -> pd.DataFrame:
        symbol = symbol or config.SYMBOL
        timeframe = timeframe or config.TIMEFRAME
        if self.mock:
            return self._mock_ohlcv(timeframe, limit)
        try:
            data = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            logger.error(f"获取 K 线失败 [{symbol} {timeframe}]: {e}")
            return pd.DataFrame()

    def fetch_ticker(self, symbol: str = "") -> dict:
        symbol = symbol or config.SYMBOL
        if self.mock:
            # 用主周期最后 close 当最新价
            df = self._mock_ohlcv(config.TIMEFRAME, 2)
            last = float(df["close"].iloc[-1])
            return {"last": last, "symbol": symbol}
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"获取 ticker 失败 [{symbol}]: {e}")
            return {}

    # ---- 订单（真实下单，需授权）----
    def create_market_order(self, side: str, amount: float, symbol: str = "") -> Optional[dict]:
        symbol = symbol or config.SYMBOL
        if self.mock:
            logger.warning(f"[MOCK] 模拟下单: {side} {amount} {symbol}")
            return {"mock": True, "side": side, "amount": amount, "symbol": symbol}
        try:
            order = self.exchange.create_market_order(symbol, side, amount)
            logger.info(f"市价单: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"创建市价单失败: {e}")
            return None
