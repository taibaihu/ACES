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

---

## 实现原理

### 整体架构

本 Skill 采用 **「本地规则预筛 + LLM 决策」的两层架构**，核心思想是：
**用便宜、确定、可解释的本地指标过滤掉 90% 的垃圾行情，只在真正有交易机会时，才调用 LLM 做最终的主观判断与理由生成。** 这样既省 LLM 成本，又避免 LLM 在「死鱼市」里硬编故事。

```
                ┌──────────────┐
   OKX 行情 ──►│  DataFetcher │  多周期 K 线
                └──────┬───────┘
                       │ 技术指标(EMA/RSI/MACD/布林/ATR/KDJ)
                       ▼
                ┌──────────────┐
                │   Gatekeeper  │  本地硬规则预筛（一票否决）
                └──────┬───────┘
            ┌──────────┴──────────┐
         拦截(死鱼市/       放行 → 组装 prompt
         极端RSI/无苗头)            │
            │ 返回 HOLD           ▼
            │              ┌──────────────┐
            │              │  LLMProvider │  调用用户自己的 LLM
            │              └──────┬───────┘
            │                     │ JSON 决策
            │                     ▼
            │              ┌──────────────┐
            └──────────────│  Engine 算价 │  SL/TP/R:R 按实时 ATR 精确计算
                           └──────┬───────┘
                                  ▼
                           ┌──────────────┐
                           │   Reporter    │  人类可读信号报告
                           └──────────────┘
```

### 关键设计决策

1. **Gatekeeper 一票否决（不调 LLM 即省钱）**
   - 波动率否决：主周期 ATR < `GATEKEEPER_ATR_MIN` 或近 12 根平均振幅 < `GATEKEEPER_AMP_MIN` → 判定「死鱼市」，直接 `HOLD`，不消耗 LLM。
   - RSI 硬约束：`RSI >= 70` 禁止开多，`RSI <= 30` 禁止开空(Lua 数值比较，LLM 改不了)。
   - 机会苗头：必须出现「EMA9/21 双线交叉 + 斜率拐头(顺势)」或「价格触及布林带(均值回归)」任一信号才放行。
   这些阈值在 `src/config.py` 与 `.env` 中可调。

2. **LLM 只做「主观判断」，不做「算账」**
   - LLM 在 MODE A(空仓)只输出 `open_long/open_short/hold` + 方向 + `sl/tp` 的 **ATR 倍数** + 自然语言理由。
   - LLM 在 MODE B(持仓)只输出 `hold/close/reduce` + 平仓比例 + 理由。
   - **SL/TP 具体价位、R:R 由 `LLMStrategy` 引擎用实时 ATR 计算**，并强制 `R:R ≥ 1:2`，防止 LLM 给出风险收益比不合理的单子。

3. **双模式决策(MODE A / MODE B)**
   - 根据 `memory.py` 中是否有未平仓记录,自动切换 prompt:
     - 空仓 → MODE A 找开仓点;
     - 持仓 → MODE B 做加减仓/止损持有判断。

4. **记忆与冷却(`memory.py`)**
   - 用 `deque` 维护最近交易记录与连亏计数;**连续 3 笔止损 → 强制 30 分钟观望**,避免情绪化连续亏损。

5. **安全边界(默认不开单)**
   - `LLMStrategy.decide()` **只生成信号,绝不下单**;`--confirm-order` 时才在 CLI 层调交易所,且需要二次输入 `YES` 确认。
   - `--mock` 用本地随机游走生成 K 线(无需任何 API),内置 `FakeLLM` 演示完整开仓流程,方便零成本试用。

### 核心模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `src/config.py` | 交易对/周期、Gatekeeper 阈值、OKX/LLM 参数读取(支持 `.env` 覆盖) |
| 行情 | `src/exchange/okx_client.py` | 连接 OKX 拉 K 线;`--mock` 时生成随机行情 |
| 数据 | `src/data/data_fetcher.py` | 多周期 K 线聚合、技术指标计算 |
| LLM | `src/llm/{base,provider,prompts,memory}.py` | 抽象 client、`create_llm_client` 工厂、prompt 模板、交易记忆 |
| 策略 | `src/strategy/llm_strategy.py` | **核心**:Gatekeeper 预筛 + 双模式 prompt + ATR 算价 + 冷却 |
| 报告 | `src/report.py` | 把决策渲染成人类可读信号报告 |
| 入口 | `scripts/analyze.py` | CLI:参数解析、模式选择(mock/真实/下单)、调策略、出报告 |

### 技术栈与依赖

- Python 3.10+,依赖见 `requirements.txt`:`ccxt`(交易所)、`pandas/numpy`(数据处理)、`ta`(技术指标)、`requests`(LLM HTTP)、`python-dotenv`(配置)。
- 无任何对外部私有项目的依赖,可独立分发运行。

### 数据流一句话总结

> 拉多周期行情 → 算指标 → Gatekeeper 硬规则过滤 → 过滤通过才问 LLM 要方向 → 引擎按 ATR 算 SL/TP → 渲染报告 →(可选)手动确认下单。
