# Architecture Overview
- **Data Ingestion:** WebSocket streams tick data -> aggregated into 1m/15m candles.
- **Indicator Engine:** Calculates RSI, EMA, MACD, Volume SMA.
- **Signal Engine:** Stage-A (Early Radar), Stage-B (Entry Trigger) based on 20-bar lookback.
- **Risk Engine:** Configurable sizing, daily kill-switch, max open positions.
- **Execution Engine:** Interfaces with m.Stock via REST for market orders and tracking.
- **Frontend:** React SPA for viewing dashboards and alerts.
