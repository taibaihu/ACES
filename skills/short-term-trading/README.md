# 短线交易 LLM 分析决策 Skill

基于「技术指标 + 本地 Gatekeeper 预筛 + LLM 双模式决策」的加密货币短线信号工具。
**只生成信号，默认不自动下单**（需 `--confirm-order` 显式授权才会真实下单）。

> 这是一个 [CodeBuddy](https://www.codebuddy.ai) Skill：把本目录整体放入 CodeBuddy 的 `skills/` 目录后即可被自动加载，
> 当对话涉及「短线交易 / 加密币种分析 / 开仓信号 / OKX 行情」等意图时触发。
> 同时它也是一个**独立 Python 工具**，可脱离 CodeBuddy 单独运行（见下方「独立运行」）。

## 目录结构

```
short-term-trading/
├── SKILL.md            # skill 说明（触发条件 / 参数 / 领域知识）
├── README.md
├── requirements.txt
├── .env.example        # 复制为 .env 并填 API Key
└── scripts/
    ├── analyze.py      # CLI 入口
    └── src/            # 自包含源码（无外部项目依赖）
        ├── config.py
        ├── exchange/okx_client.py
        ├── data/data_fetcher.py
        ├── llm/{base,provider,prompts,memory}.py
        ├── strategy/llm_strategy.py
        └── report.py
```

## 安装

```bash
cd short-term-trading
pip install -r requirements.txt
cp .env.example .env      # 填 OKX_API_KEY / LLM_API_KEY
```

## 使用

```bash
# 1) 模拟演示（无需任何 API，用本地随机行情跑通全流程）
python scripts/analyze.py --mock

# 2) 真实分析（需 .env 配置 OKX + LLM）
python scripts/analyze.py --symbol ETH-USDT --timeframe 15m

# 3) 生成信号后真实下单（高危，需 OKX API Key + 二次确认）
python scripts/analyze.py --symbol BTC-USDT --confirm-order
```

## 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--symbol` | BTC-USDT | 交易对 |
| `--timeframe/--tf` | 5m | 主周期 |
| `--aux` | 15m | 辅助周期 |
| `--macro4h` | 4h | 宏观周期 1 |
| `--macro1d` | 1d | 宏观周期 2 |
| `--provider` | openai | LLM 厂商 |
| `--model` | gpt-4o | 模型名 |
| `--mock` | 关 | 模拟模式 |
| `--confirm-order` | 关 | 真实下单（需授权） |

## 决策逻辑

1. **多周期特征**：5m（主）+ 15m + 4h/1d，含 EMA/RSI/MACD/布林/ATR/KDJ
2. **Gatekeeper 本地预筛**（省成本 + 防垃圾信号）：
   - 波动率一票否决：ATR < 阈值 或 近 12 根振幅 < 阈值 → 死鱼市拦截
   - RSI 极端硬约束（>=70 不开多 / <=30 不开空）
   - 顺势苗头（EMA9/21 双线交叉 + 斜率拐头）或 均值回归（触布林带）
3. **LLM 双模式**：MODE A 开仓（open_long/short/hold）/ MODE B 持仓管理（hold/close/reduce）
4. **价位由引擎算**：LLM 只给方向 + ATR 倍数，SL/TP/R:R 按实时 ATR 精确计算，强制 R:R ≥ 1:2
5. **连亏冷却**：连续 3 笔止损 → 强制 30 分钟观望

阈值（ATR/振幅/Gatekeeper）可在 `.env` 或 `config.py` 调整。
