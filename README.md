# 🤖 DCA Trading Bot

A robust, set-and-forget Dollar-Cost Averaging (DCA) trading bot built in Python.

This bot automatically purchases a fixed fiat amount of Bitcoin (or any cryptocurrency) on a scheduled weekly basis using the Binance API. It's designed to run silently in the background (e.g., on a Raspberry Pi or VPS) and log every trade to a local SQLite database for easy tracking.

---

## 🏗️ Architecture & Features

### The Three Phases
The bot is built to explicitly progress through three stages, configurable strictly via `config.yaml`:
1. **`backtest`:** Pulls public historical weekly data (klines) from Binance and simulates Monday buys over a specified time period. Outputs total ROI, average buy price, and compares performance against simply holding.
2. **`forward_test`:** *(In Development)* Connects to the real Binance ticker on a live weekly schedule and logs simulated buys if a mock balance is sufficient. No real orders are placed.
3. **`live`:** *(In Development)* The real deal. Connects to your Binance account, validates balance, prevents duplicate runs, and places real market buy orders every Monday.

### Key Features
- **Config-Driven:** Everything from the trading pair, buy amount, operating mode, and safety margins is controlled externally via `config.yaml`.
- **Absolute Safety:** The bot enforces strict Phase boundaries. Real orders can only be placed in `live` mode. It also includes kill-switches (won't buy if fiat balance is too low) and duplicate-order guards (will only buy once per Monday).
- **Graceful Error Handling:** If Binance rejects an order (e.g., insufficient funds), it halts safely. If a network timeout occurs, it retries. If the retry fails, the job fails gracefully without killing the background scheduler.
- **Data Persistence:** Every simulated or real trade is written to `data/trades.db` (a local SQLite file) using identical columns, meaning your backtest logic and live tracking share the exact same database.

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- A Binance Account
- Binance API Keys (*Read Only* permissions needed for Backtesting/Forward Testing. *Spot Trading* needed for Live. **Never enable Withdrawals**).

### 2. Installation
Clone the repository and install the pinned dependencies:
```bash
git clone <your-repo-url>
cd DCA-BOT
pip install -r requirements.txt
```

### 3. Configuration
**Environment Variables (API Keys)**
Copy the template to create your `.env` file:
```bash
copy .env.example .env     # Windows
cp .env.example .env       # Mac/Linux
```
Add your Binance keys to the `.env` file. These are never committed to version control.

**Bot Settings (`config.yaml`)**
Open `config.yaml` to adjust your strategy.
- Set `mode: backtest` to test historical performance.
- Set `buy_amount_aud: 100` (or whatever amount you wish to spend per week).
- Set `trading_pair: BTCAUD` (Buy BTC with AUD. For USD, use `BTCUSDT`).

### 4. Running the Bot
Everything is routed through the main entry point:
```bash
python main.py
```

---

## 📊 Viewing Your Trades
Every action the bot takes is logged to the database (`data/trades.db`).
You can query this directly using Python, or use a GUI tool like [DB Browser for SQLite](https://sqlitebrowser.org/) to view, sort, and export your trade history to Excel.

---

*Note: This bot is a solo-developer project tailored for long-term set-and-forget acquisition. It is not designed for high-frequency trading.*
