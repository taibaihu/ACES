"""数据获取与特征工程模块。"""

import numpy as np
import pandas as pd
import ta

from ..config import config
from ..exchange.okx_client import OKXClient
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class DataFetcher:
    """负责从交易所获取数据并加工为特征。"""

    def __init__(self, client: OKXClient):
        self.client = client

    def fetch_features(self, timeframe: str = "", limit: int = 500) -> pd.DataFrame:
        df = self.client.fetch_ohlcv(timeframe=timeframe, limit=limit)
        if df.empty:
            return df
        df = self._add_technical_indicators(df)
        df = self._add_lagged_features(df)
        df.dropna(inplace=True)
        return df

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        df["ema_9"] = ta.trend.ema_indicator(close, 9)
        df["ema_21"] = ta.trend.ema_indicator(close, 21)
        df["ema_50"] = ta.trend.ema_indicator(close, 50)
        df["ema_200"] = ta.trend.ema_indicator(close, 200)

        bb = ta.volatility.BollingerBands(close, 20, 2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / close

        df["rsi_14"] = ta.momentum.rsi(close, 14)

        macd = ta.trend.MACD(close)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()

        df["atr_14"] = ta.volatility.average_true_range(high, low, close, 14)

        df["volume_sma_20"] = ta.trend.sma_indicator(volume, 20)
        df["volume_ratio"] = volume / df["volume_sma_20"]

        low_9 = low.rolling(9).min()
        high_9 = high.rolling(9).max()
        rsv = (close - low_9) / (high_9 - low_9 + 1e-10) * 100
        df["k"] = rsv.ewm(com=2).mean()
        df["d"] = df["k"].ewm(com=2).mean()
        df["j"] = 3 * df["k"] - 2 * df["d"]
        return df

    def _add_lagged_features(self, df: pd.DataFrame, n_lags: int = 5) -> pd.DataFrame:
        for i in range(1, n_lags + 1):
            df[f"ret_{i}"] = df["close"].pct_change(i)
            df[f"volume_{i}"] = df["volume"].shift(i)
            df[f"rsi_{i}"] = df["rsi_14"].shift(i)
        return df
