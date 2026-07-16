---
name: short-term-trading
description: 短线交易 LLM 分析决策工具。基于多周期技术指标（EMA/RSI/MACD/布林带/ATR/KDJ）+ 本地 Gatekeeper 预筛 + LLM 双模式决策（开仓 MODE A / 持仓管理 MODE B），生成带精确止损止盈价位的短线交易信号。支持可配置交易对与周期，提供模拟模式与手动确认下单。当用户需要 BTC/加密货币短线分析、AI 交易信号、结合技术面与 LLM 的买卖决策时使用。
---

# 短线交易 LLM 分析决策 (Short-Term Trading Signal)

## 何时使用

- 用户想分析某个币种（BTC、ETH 等）的短线走势并获取买卖信号
- 用户需要「AI + 技术指标」结合的交易决策，而非纯指标
- 用户说：「分析一下 BTC 短线」「给我个 ETH 15m 交易信号」「用 LLM 看看现在能不能开多」

## 核心能力

1. **多周期特征工程**：15m（主）+ 1h（辅助）+ 4h / 1d（宏观过滤），计算 EMA9/21/50/200、RSI、MACD、布林带、ATR、KDJ、量比。主周期选 15m 而非 5m：噪音更小、止损被扫概率更低、手续费占比更省。
2. **Gatekeeper 本地预筛（省成本 + 防垃圾信号）**：
   - 波动率一票否决：ATR < 阈值 或 近 12 根振幅 < 阈值 → 死鱼市拦截
   - RSI 极端硬约束（>=70 不开多 / <=30 不开空）
   - 顺势苗头（EMA9/21 双线交叉 + 斜率拐头）或 均值回归苗头（触布林带）
   - 无信号直接 HOLD，**不调用 LLM**
3. **LLM 双模式决策**：
   - MODE A（无持仓）：open_long / open_short / hold
   - MODE B（有持仓）：hold / close / reduce
   - LLM 只输出「方向 + ATR 倍数」，价位由引擎按实时 ATR 精确计算（SL/TP/R:R）
4. **风控**：连亏 3 笔自动 30 分钟冷却

## 运行模式

| 模式 | 说明 | 是否需 API |
|------|------|------------|
| `--mock` | 用内置示例行情跑通全流程，演示/教学 | 否 |
| 真实模式 | 连 OKX 实时行情 + 用户 LLM Key 生成信号 | 是（.env 配置） |

**下单安全边界**：本 skill **绝不自动下单**。它只生成信号报告（方向、入场、SL、TP、R:R、理由）。模拟模式下打印「模拟下单」日志；真实下单需用户自己在 OKX 手动操作，或用 `--confirm-order` 显式确认后由脚本调用交易所（需已配置 OKX API Key）。

## 使用方法

```bash
cd skills/short-term-trading

# 1) 模拟演示（无需任何 API）
python scripts/analyze.py --mock --symbol BTC-USDT --timeframe 15m

# 2) 真实分析（需 .env 配置 OKX + LLM）
cp .env.example .env   # 填入 OKX_API_KEY 等 与 LLM_API_KEY
python scripts/analyze.py --symbol ETH-USDT --timeframe 15m

# 3) 生成信号后，手动确认才真实下单（高危，需用户明确授权）
python scripts/analyze.py --symbol BTC-USDT --confirm-order

# 4) 轮询模式：每隔 5 分钟自动分析一次（默认间隔，Ctrl+C 退出）
python scripts/analyze.py --symbol BTC-USDT --loop

#    自定义轮询间隔（例如每 10 分钟）
python scripts/analyze.py --symbol BTC-USDT --loop --interval 10
```

## 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--symbol` | BTC-USDT | 交易对 |
| `--timeframe` | 15m | 主周期（15m 噪音小、止损被扫概率低、手续费占比小） |
| `--aux` | 1h | 辅助周期（方向确认） |
| `--macro4h` | 4h | 宏观周期 1 |
| `--macro1d` | 1d | 宏观周期 2 |
| `--mock` | 关 | 模拟模式 |
| `--loop` | 关 | 轮询模式：每隔 --interval 分钟自动分析一次（默认 5 分钟，Ctrl+C 退出） |
| `--interval` | 5 | 轮询间隔（分钟） |
| `--confirm-order` | 关 | 真实下单（需 API + 用户授权；轮询模式下不自动下单） |
| `--provider` | 见 .env | LLM 厂商 openai/claude/deepseek |
| `--model` | 见 .env | 模型名 |

## 输出示例

```
═══ 短线信号 BTC-USDT @ 64230.7 (15m) ═══
决策: 开多 OPEN_LONG
入场: 64230.7    SL: 63801.3 (-429.4, 1.5×ATR)
TP1: 64989.3 (+758.6, 3.0×ATR)   TP2: 65748.0
R:R = 1:2.0
─────────────────────────────────────
理由: 15m EMA9 上穿 EMA21 且斜率向上，量能配合，短线偏多。
─────────────────────────────────────
⚠ 模拟模式：未真实下单。真实操作请在 OKX 手动执行或 --confirm-order。
```

## 领域知识（决策体系）

调用本 skill 时，请理解其决策逻辑：

- **信号优先于价格计算**：LLM 不预测价位，只给方向 + ATR 倍数，避免模型乱编价格
- **Gatekeeper 是守门员**：先判「有没有油水」（波动率），再判「有没有苗头」（指标结构），都没有就安静观望——这是反 FOMO 设计
- **R:R 强制 >= 1:2**：TP 距离至少是 SL 的 2 倍
- **冷却机制**：连续止损 3 次强制休息 30 分钟，对抗报复性交易

详细 Prompt 与风控约束见 `scripts/src/llm/prompts.py`。
