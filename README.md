# ACES

A collection of CodeBuddy Skills.

## Contents

| Skill | Path | Description |
|-------|------|-------------|
| 短线交易 LLM 分析决策 | [`skills/short-term-trading/`](skills/short-term-trading/) | 基于「技术指标 + 本地 Gatekeeper 预筛 + LLM 双模式决策」的加密货币短线信号工具。只生成信号，默认不自动下单（需显式授权才真实下单）。 |

## What is a CodeBuddy Skill?

[CodeBuddy](https://www.codebuddy.ai) 的 Skill 是一段「领域知识 + 可执行脚本」的可分发包：
把 skill 目录整体放入 CodeBuddy 的 `skills/` 目录后即可被自动加载，当对话涉及相关意图时触发；
同时 skill 内的脚本通常也是独立可运行的 CLI 工具。

## How to use a Skill

以 `short-term-trading` 为例：

```bash
# 作为 CodeBuddy Skill：把 skills/ 目录放入 CodeBuddy 的 skills/ 目录即可自动加载

# 或独立运行
cd skills/short-term-trading
pip install -r requirements.txt
cp .env.example .env      # 填 OKX_API_KEY / LLM_API_KEY
python scripts/analyze.py --mock              # 无需 API 的模拟演示
python scripts/analyze.py --symbol ETH-USDT --timeframe 15m   # 真实分析
python scripts/analyze.py --symbol BTC-USDT --confirm-order   # 手动确认下单
```

详细的实现原理与参数说明见各 skill 子目录内的 `README.md`。
