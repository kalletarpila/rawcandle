# 🌕 RawCandle — Flet Web App for Render.com

RawCandle is a simple **Python + Flet** web application that runs
both locally and in the cloud via **Render.com**.
It provides a clean, desktop-style user interface — directly in the browser.

[...]

## 🧠 Simulation Module Specification (WIP)

The upcoming `simu` package adds a backtesting-style simulation tab to RawCandle. Key requirements captured from the product brief:

- **Data sources**: two SQLite databases located in `data/`; schema must be introspected at runtime. Analysis rows provide `signal_strength` (REAL) and pattern names (`downtrend`, `Hammer`, `Bullish Engulfing`, `Piercing Pattern`, `Three White Soldiers`, `Morning Star`, `Dragonfly Doji`). Price/volume history comes from the stock-data database (Open, High, Low, Close, Volume columns identified programmatically).
- **Routing & scope**: simulation executes per ticker (UI resets capital between tickers) across the user-specified date range `[start, end]`. Both bounds are inclusive; if the end date has no trading session, use the latest prior session when valuing the portfolio.
- **t₀ selection**: iterate trading days chronologically, find the first qualifying `t0` candle that matches any selected pattern. When several patterns appear on the same day, pick the strongest (`signal_strength` max, first occurrence breaks ties), except `downtrend`, which is only considered if it is the sole user-selected pattern. Ignore duplicate events beyond the chosen candle.
- **Indicator filters**: compute RSI(14) from Close prices and volume SMA10 from the ten sessions preceding `t0`. Require RSI ≤ user threshold, volume growth % ≥ threshold, and `signal_strength` ≥ min strength. Skip signals lacking sufficient history.
- **Combo mode**: optional “Vain kynttilä + divergenssi” toggle requires that a selected candlestick pattern (downtrend counts as a candle) and a divergence signal fire on the same day. Divergence is valid if it occurs on `t₀` or within the previous three sessions (same window as `results_data`). The UI shows how many tickers / t₀-päiviä täyttävät ehdot valitulla aikavälillä.
- **Trade logic**: capital input represents thousands USD (e.g. `10 → 10,000`). On a qualifying `t0`, buy on the next available session’s Open using the configured percentage of free cash (full shares only; skip trade if even one share cannot be purchased). Maintain weighted-average cost. Evaluate stop-loss / take-profit on each close; trigger sales at the next available Open (process all exits before new entries on the same day). If future pricing is missing, carry positions until data resumes or the simulation end.
- **Results**: for each ticker emit `{ticker, start_capital, end_capital, growth_pct, buy_trades}` with numeric fields (growth in percent). The final portfolio value equals remaining cash plus mark-to-market of open lots at the final day’s Close (or latest prior session if the end date is a holiday).

### 🚀 Enjoy coding with Flet + Render!
