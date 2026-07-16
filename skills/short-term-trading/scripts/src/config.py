"""短线交易 skill 全局配置，支持环境变量 + 运行时参数覆盖。"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- OKX API（真实模式需要；模拟模式可留空）---
    OKX_API_KEY = os.getenv("OKX_API_KEY", "")
    OKX_SECRET_KEY = os.getenv("OKX_SECRET_KEY", "")
    OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")

    # --- 交易对 / 周期（可被 CLI 参数覆盖）---
    SYMBOL = os.getenv("SYMBOL", "BTC-USDT")
    TIMEFRAME = os.getenv("TIMEFRAME", "5m")
    AUX_TIMEFRAME = os.getenv("AUX_TIMEFRAME", "15m")
    MACRO_TIMEFRAME_4H = os.getenv("MACRO_TIMEFRAME_4H", "4h")
    MACRO_TIMEFRAME_1D = os.getenv("MACRO_TIMEFRAME_1D", "1d")

    # --- 仓位 / 风控 ---
    LEVERAGE = int(os.getenv("LEVERAGE", "100"))
    SINGLE_TRADE_SIZE = float(os.getenv("SINGLE_TRADE_SIZE", "0.001"))
    MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.005"))
    STOP_LOSS_ATR_MULT = float(os.getenv("STOP_LOSS_ATR_MULT", "1.5"))
    MIN_RR_RATIO = float(os.getenv("MIN_RR_RATIO", "2.0"))

    # --- Gatekeeper 波动率阈值（可调）---
    GATEKEEPER_ATR_MIN = float(os.getenv("GATEKEEPER_ATR_MIN", "100"))
    GATEKEEPER_SWING_MIN = float(os.getenv("GATEKEEPER_SWING_MIN", "150"))

    # --- LLM ---
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    def apply_cli(self, symbol=None, timeframe=None, aux=None, macro4h=None, macro1d=None):
        if symbol:
            self.SYMBOL = symbol
        if timeframe:
            self.TIMEFRAME = timeframe
        if aux:
            self.AUX_TIMEFRAME = aux
        if macro4h:
            self.MACRO_TIMEFRAME_4H = macro4h
        if macro1d:
            self.MACRO_TIMEFRAME_1D = macro1d


config = Config()
