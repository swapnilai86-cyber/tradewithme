"""
data_ingestion/polling_scanner.py
Nifty 500 scheduled polling engine.
Fetches historical candles from m.Stock every 2 minutes during market hours
and feeds finalized 15m candles to the SignalScanner (Part N).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta, time as dt_time
from typing import Dict, List, Optional
import os
import pandas as pd

from backend.logging_config import get_logger
from backend.engine.signals.scanner import SignalScanner
from backend.engine.brokers.mstock.instruments import NiftyInstruments

logger = get_logger(__name__)

CACHE_DIR = "/app/data/historical"
os.makedirs(CACHE_DIR, exist_ok=True)

FILTER_CONFIG_FILE = "/app/config/cmp_filter.json"

logger = get_logger(__name__)

# IST offset
IST_OFFSET = timedelta(hours=5, minutes=30)
MARKET_OPEN_IST  = dt_time(9, 15)
MARKET_CLOSE_IST = dt_time(15, 30)

# How many historical 15m candles to fetch per symbol per scan
CANDLE_LOOKBACK_DAYS = 30


class PollingScanner:
    """
    Scheduled scanner that polls Nifty 500 stocks every N seconds during market hours.
    Implements Part N (finalized candles only) and the 2-minute scan interval.
    """

    def __init__(
        self,
        mconnect_obj,
        signal_scanner: SignalScanner,
        instruments: NiftyInstruments,
        order_engine,
        config: dict,
    ):
        self.mconnect = mconnect_obj
        self.scanner = signal_scanner
        self.instruments = instruments
        self.order_engine = order_engine
        self.config = config
        strategy = config.get("strategy", {})

        self.scan_interval: int = strategy.get("scan_interval_seconds", 120)
        self.timeframe: str = strategy.get("timeframe", "15minute")
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Daily EMA cache: symbol -> DataFrame of daily candles
        self._daily_cache: Dict[str, pd.DataFrame] = {}
        self._daily_cache_date: Optional[str] = None
        self.offline_mode: bool = False
        self.scan_enabled: bool = True
        self._offline_scan_done: bool = False

        # CMP Filter
        self.cmp_filter_mode: str = "none" # "none", "less_than", "greater_than", "between"
        self.cmp_filter_min: float = 0.0
        self.cmp_filter_max: float = 0.0
        self._load_cmp_filter()

    def _load_cmp_filter(self) -> None:
        try:
            if os.path.exists(FILTER_CONFIG_FILE):
                with open(FILTER_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.cmp_filter_mode = data.get("mode", "none")
                    self.cmp_filter_min = float(data.get("min_val", 0.0))
                    self.cmp_filter_max = float(data.get("max_val", 0.0))
        except Exception as e:
            logger.error(f"Failed to load CMP filter config: {e}")

    def save_cmp_filter(self, mode: str, min_val: float, max_val: float) -> None:
        self.cmp_filter_mode = mode
        self.cmp_filter_min = float(min_val)
        self.cmp_filter_max = float(max_val)
        try:
            with open(FILTER_CONFIG_FILE, "w") as f:
                json.dump({
                    "mode": self.cmp_filter_mode,
                    "min_val": self.cmp_filter_min,
                    "max_val": self.cmp_filter_max
                }, f)
        except Exception as e:
            logger.error(f"Failed to save CMP filter config: {e}")

    # ──────────────────────────────────────────────
    # LIFECYCLE
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"PollingScanner started — interval={self.scan_interval}s, "
            f"timeframe={self.timeframe}, symbols={len(self.instruments.get_scannable_symbols())} (Offline: {self.offline_mode})",
            extra={"reason_code": "POLLING_SCANNER_STARTED"},
        )

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PollingScanner stopped.")

    # ──────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main async loop — runs every scan_interval seconds during market hours."""
        while self._running:
            try:
                if not self.scan_enabled:
                    await asyncio.sleep(self.scan_interval)
                    continue

                ist_now = datetime.now(timezone.utc) + IST_OFFSET
                ist_time = ist_now.time()

                # TEMPORARY BYPASS FOR TESTING: Run regardless of market hours
                if self.offline_mode or (MARKET_OPEN_IST <= ist_time <= MARKET_CLOSE_IST):
                    if self.offline_mode and self._offline_scan_done:
                        logger.debug("Offline scan already completed. Waiting for next trigger or market open.")
                    else:
                        await self._refresh_daily_cache_if_needed(ist_now)
                        await self._run_scan()
                        
                        if self.offline_mode:
                            self._offline_scan_done = True
                            logger.info("Offline scan completed. Going into sleep mode until re-triggered.")
                else:
                    logger.debug(
                        f"Market closed (IST {ist_time.strftime('%H:%M')}) — scanner idle"
                    )

            except Exception as e:
                logger.error(f"PollingScanner loop error: {e}", exc_info=True)

            await asyncio.sleep(self.scan_interval)

    # ──────────────────────────────────────────────
    # DAILY CACHE (EMA-50/200 trend filter)
    # ──────────────────────────────────────────────

    async def _refresh_daily_cache_if_needed(self, ist_now: datetime) -> None:
        """Refresh daily candle cache once per day after 09:20 IST."""
        today_str = ist_now.strftime("%Y-%m-%d")
        refresh_time = dt_time(9, 20)

        if (
            self._daily_cache_date != today_str
            and ist_now.time() >= refresh_time
        ):
            logger.info("Refreshing daily candle cache for EMA-50/200 filter...")
            symbols = self.instruments.get_scannable_symbols()
            # Fetch daily candles for a sample of symbols (batch to avoid API overload)
            new_cache: Dict[str, pd.DataFrame] = {}
            for item in symbols:
                sym = item["symbol"]
                token = item["token"]
                try:
                    df = await self._fetch_candles(token, "day", lookback_days=300)
                    if df is not None and len(df) > 0:
                        new_cache[sym] = df
                    await asyncio.sleep(0.2)  # 200ms throttle between symbols
                except Exception as e:
                    logger.debug(f"Daily cache fetch failed for {sym}: {e}")

            self._daily_cache = new_cache
            self._daily_cache_date = today_str
            logger.info(f"Daily cache refreshed: {len(new_cache)} symbols")

    # ──────────────────────────────────────────────
    # SCAN RUN
    # ──────────────────────────────────────────────

    async def _run_scan(self) -> None:
        """Fetch 15m candles for all Nifty 500 symbols and run signal scanner."""
        symbols = self.instruments.get_scannable_symbols()
        ist_now = datetime.now(timezone.utc) + IST_OFFSET
        logger.info(
            f"Scan run started at IST {ist_now.strftime('%H:%M:%S')} "
            f"— {len(symbols)} symbols"
        )

        # Build ltp_map for exit checks while scanning
        ltp_map: Dict[str, float] = {}
        scan_count = 0
        signal_count = 0

        for item in symbols:
            if not self._running:
                break

            sym = item["symbol"]
            token = item["token"]
            sector = item.get("sector", "Unknown")

            try:
                if self.offline_mode:
                    df = self._load_from_cache(sym)
                else:
                    df = await self._fetch_candles(token, self.timeframe, lookback_days=CANDLE_LOOKBACK_DAYS)
                    if df is not None and not df.empty:
                        self._save_to_cache(sym, df)

                if df is None or len(df) < 21:
                    logger.info(f"Skipping {sym} (token {token}) - df length: {len(df) if df is not None else 'None'}")
                    continue

                # Only process FINALIZED candles (Part N)
                # The last candle in historical data is always finalized
                # Drop the in-progress candle if its timestamp is within current 15m window
                df = self._drop_live_candle(df)
                if len(df) < 21:
                    continue

                # Track LTP from latest close for exit checks
                cmp = float(df.iloc[-1]["close"])
                ltp_map[sym] = cmp

                # Apply CMP Filter
                if self.cmp_filter_mode == "less_than" and cmp > self.cmp_filter_max:
                    continue
                elif self.cmp_filter_mode == "greater_than" and cmp < self.cmp_filter_min:
                    continue
                elif self.cmp_filter_mode == "between" and (cmp < self.cmp_filter_min or cmp > self.cmp_filter_max):
                    continue

                daily_df = self._daily_cache.get(sym)

                # Run signal evaluation
                await self.scanner.process_new_candle(sym, df, daily_df=daily_df, sector=sector)
                scan_count += 1

                # Throttle: small sleep between symbols to avoid API overload
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"Scan error for {sym}: {e}", exc_info=True)

        # Check exits for all open positions using latest LTP
        if ltp_map and self.order_engine:
            await self.order_engine.check_exits(ltp_map)
            # Tick pilot timers
            await self.order_engine.tick_pilot_timers()

        logger.info(
            f"Scan complete — {scan_count} symbols scanned",
            extra={"reason_code": "SCAN_COMPLETE"},
        )

    # ──────────────────────────────────────────────
    # DATA FETCHING
    # ──────────────────────────────────────────────

    async def _fetch_candles(
        self, token: str, interval: str, lookback_days: int = 30
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV candles from m.Stock API.
        Returns a pandas DataFrame with columns: open, high, low, close, volume, datetime.
        """
        if not self.mconnect:
            return None

        try:
            from_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            loop = asyncio.get_running_loop()
            
            # Retry up to 3 times on timeout/failure
            resp = None
            for attempt in range(3):
                try:
                    resp = await loop.run_in_executor(
                        None,
                        self.mconnect.get_historical_chart,
                        "NSE",
                        token,
                        interval,
                        from_date,
                        to_date,
                    )
                    break # Success
                except Exception as e:
                    if attempt == 2:
                        raise e
                    await asyncio.sleep(0.5 * (attempt + 1))
            
            if not resp or not hasattr(resp, "json"):
                return None

            data = resp.json()
            candles = None

            # Handle different response structures from m.Stock SDK
            if isinstance(data, dict):
                candles = data.get("data") or data.get("candles") or data.get("result")
                # Sometimes mStock nests data inside data -> data
                if isinstance(candles, dict):
                    candles = candles.get("data") or candles.get("candles") or candles.get("result")
            elif isinstance(data, list):
                candles = data

            if not candles:
                return None

            return self._parse_candles(candles)

        except Exception as e:
            logger.debug(f"Candle fetch error for token {token}: {e}")
            return None

    def _parse_candles(self, candles: list) -> pd.DataFrame:
        """
        Parse m.Stock candle data into a standardized DataFrame.
        Handles both dict-list and list-of-lists formats.
        """
        rows = []
        for c in candles:
            try:
                if isinstance(c, (list, tuple)) and len(c) >= 6:
                    # Format: [timestamp, open, high, low, close, volume]
                    rows.append({
                        "datetime": pd.to_datetime(c[0], unit="ms") if isinstance(c[0], (int, float)) else pd.to_datetime(c[0]),
                        "open":   float(c[1]),
                        "high":   float(c[2]),
                        "low":    float(c[3]),
                        "close":  float(c[4]),
                        "volume": int(c[5]),
                    })
                elif isinstance(c, dict):
                    rows.append({
                        "datetime": pd.to_datetime(c.get("date") or c.get("timestamp") or c.get("t")),
                        "open":   float(c.get("open") or c.get("o", 0)),
                        "high":   float(c.get("high") or c.get("h", 0)),
                        "low":    float(c.get("low") or c.get("l", 0)),
                        "close":  float(c.get("close") or c.get("c", 0)),
                        "volume": int(c.get("volume") or c.get("v", 0)),
                    })
            except (ValueError, TypeError, KeyError):
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.sort_values("datetime").reset_index(drop=True)
        return df

    def _drop_live_candle(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Drop the last candle if it represents the currently building 15m candle.
        A candle is considered live if its timestamp is within the current 15m window.
        Part N: only finalized candles should be processed.
        """
        if df.empty:
            return df

        now_utc = datetime.now(timezone.utc)
        last_ts = df.iloc[-1]["datetime"]

        # Make timezone-aware if needed
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)

        # If last candle is less than 15 minutes old, it may still be building
        age_minutes = (now_utc - last_ts).total_seconds() / 60
        if age_minutes < 15:
            logger.debug(f"Dropping live candle (age={age_minutes:.1f}m < 15m)")
            return df.iloc[:-1].copy()

        return df

    # ──────────────────────────────────────────────
    # CACHING (OFFLINE MODE)
    # ──────────────────────────────────────────────

    def _save_to_cache(self, symbol: str, df: pd.DataFrame) -> None:
        """Save a fetched dataframe to the local CSV cache for offline scanning."""
        if df is None or df.empty:
            return
        try:
            filepath = os.path.join(CACHE_DIR, f"{symbol}_{self.timeframe}.csv")
            df.to_csv(filepath, index=False)
        except Exception as e:
            logger.debug(f"Failed to save cache for {symbol}: {e}")

    def _load_from_cache(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load a dataframe from the local CSV cache."""
        try:
            filepath = os.path.join(CACHE_DIR, f"{symbol}_{self.timeframe}.csv")
            if os.path.exists(filepath):
                df = pd.read_csv(filepath, parse_dates=["datetime"])
                # Ensure timezone awareness if not present
                if not df.empty and df["datetime"].dt.tz is None:
                    df["datetime"] = df["datetime"].dt.tz_localize("UTC")
                return df
        except Exception as e:
            logger.debug(f"Failed to load cache for {symbol}: {e}")
        return None
