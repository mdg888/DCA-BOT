# 🤖 DCA Trading Bot (BTCAUD)

A professional, industrial-grade Dollar-Cost Averaging (DCA) trading bot built in Python.

This bot automatically purchases a fixed fiat amount of Bitcoin on a scheduled weekly basis using the Binance API. It features a triple-phase architecture (Backtest → Paper Trade → Live) to ensure your strategy is profitable and safe before risking real capital.

---

## 🏗️ Architecture & Features

### The Legend of Three Phases
The bot is designed to explicitly progress through three stages, configurable via `config.yaml`:
1. **`backtest`:** Simulates historical Monday buys using real 1W klines from Binance. Calculates ROI vs. Market performance.
2. **`forward_test`:** Paper trading. Fetches live prices every Monday and logs simulated trades against a mock `simulated_balance_aud`. No real money is spent.
3. **`live`:** Advanced spot trading. Performs real balance checks, duplicate order protection, and executes market buys via `quoteOrderQty`.

### 🛡️ Safety-First Engineering
- **Duplicate Guard:** Checks the SQLite database 48 hours prior to every trade. If a `live` trade was already logged this week, it refuses to run again—protecting you from accidental double-spending.
- **Kill Switch:** Automatically aborts the trade if your AUD spot balance falls below your `min_balance_aud` threshold.
- **Network Resilience:** Implements a 3x retry loop for Binance API timeouts during volatile market conditions.
- **SQLite Persistence:** Every phase logs to the same shared table in `data/trades.db` for unified history tracking.

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- A Binance Account
- API Keys with "Spot Trading" enabled (Never enable withdrawals).

### 2. Installation
```bash
git clone <your-repo-url>
cd DCA-BOT
pip install -r requirements.txt
```

### 3. Configuration
**Secrets (`.env`)**
Rename `.env.example` to `.env` and add your `BINANCE_API_KEY` and `BINANCE_API_SECRET`.

**Strategy (`config.yaml`)**
```yaml
mode: forward_test       # Start here!
trading_pair: BTCAUD
buy_amount_aud: 100
schedule:
  time: "09:00"          # AEST (Monday Morning)
```

---

## 🧪 Verification & Testing

Before going live, it is **strongly recommended** to run the unit test suite to verify your local environment:

```bash
python -m unittest discover -v
```
This runs 10 exhaustive tests covering config validation, database integrity, and safety-guard logic—all without hitting the real API.

---

## 📊 Running the Bot

Start the bot in your chosen mode:
```bash
python main.py
```
The bot will verify your configuration and enter a wait loop. Press **`Ctrl + C`** at any time to shut down safely.

---

*Disclaimer: Trading involves risk. Use this bot at your own discretion. The developer is not responsible for financial losses incurred via automated trading.*
