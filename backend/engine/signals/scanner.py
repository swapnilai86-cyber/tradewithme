"""
signals/scanner.py — Stage-A Early Radar, Stage-B Entry Trigger, Re-entry Logic
Implements Parts A, B, C, K, N of the trading engine specification.
"""
from __future__ import annotations

import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import json
import os
from backend.logging_config import get_logger
from backend.engine.indicators.engine import IndicatorEngine

logger = get_logger(__name__)

ALERT_STATE_FILE = "/app/config/scanner_alerts_state.json"

class BreakoutTracker:
    """Tracks recent breakout events for re-entry evaluation (Part C)."""

    def __init__(self, window_bars: int = 50):
        self.window_bars = window_bars
        # symbol -> {breakout_level, breakout_bar_index, entry_executed}
        self._breakouts: Dict[str, dict] = {}

    def record_breakout(self, symbol: str, level: float, bar_index: int) -> None:
        self._breakouts[symbol] = {
            "breakout_level": level,
            "breakout_bar_index": bar_index,
            "entry_executed": False,
        }

    def mark_entry_executed(self, symbol: str) -> None:
        if symbol in self._breakouts:
            self._breakouts[symbol]["entry_executed"] = True

    def get_active_breakout(self, symbol: str, current_bar_index: int) -> Optional[dict]:
        """Return active breakout if it's within the tracking window and entry not yet done."""
        b = self._breakouts.get(symbol)
        if not b:
            return None
        if b["entry_executed"]:
            return None
        if (current_bar_index - b["breakout_bar_index"]) > self.window_bars:
            # Expired — clean up
            del self._breakouts[symbol]
            return None
        return b

    def clear(self, symbol: str) -> None:
        self._breakouts.pop(symbol, None)


class SignalScanner:
    """
    Evaluates 15-minute OHLCV DataFrames for Nifty 500 swing trade signals.

    Stage-A: Early Radar (6 conditions) → yellow Discord alert
    Stage-B: Entry Trigger (6 conditions + no-chase) → green Discord alert
    Stage-C: Re-entry on Retest (4 conditions) → cyan Discord alert
    """

    def __init__(self, event_bus, config: dict):
        self.event_bus = event_bus
        self.config = config
        strategy = config.get("strategy", {})

        # Stage-A thresholds
        self.compression_pct = strategy.get("early_radar_compression_pct", 3.5)
        self.near_res_pct = strategy.get("early_radar_near_resistance_pct", 1.5)
        self.radar_rsi_min = strategy.get("early_radar_rsi_min", 50)
        self.radar_rsi_max = strategy.get("early_radar_rsi_max", 62)
        self.radar_vol_ratio = strategy.get("early_radar_vol_ratio_min", 0.8)

        # Stage-B thresholds
        self.entry_rsi_min = strategy.get("entry_rsi_min", 52)
        self.entry_rsi_max = strategy.get("entry_rsi_max", 72)
        self.entry_vol_ratio = strategy.get("entry_vol_ratio_min", 1.5)
        self.no_chase_pct = strategy.get("no_chase_pct", 1.5)
        self.lookback = strategy.get("lookback_breakout", 20)

        # Re-entry thresholds
        self.retest_tol_pct = strategy.get("retest_tolerance_pct", 0.5)
        self.retest_rsi_min = strategy.get("retest_rsi_min", 50)
        self.retest_vol_ratio = strategy.get("retest_vol_ratio_min", 1.1)

        # Breakout tracker for re-entry
        window = strategy.get("breakout_tracking_window", 50)
        self.breakout_tracker = BreakoutTracker(window_bars=window)

        # In-memory radar candidates list
        self.radar_candidates: List[str] = []
        
        # Repetitive alert throttling
        self.last_alert_targets: Dict[str, float] = {}
        self.last_radar_prices: Dict[str, float] = {}
        self._load_alert_state()

    def _load_alert_state(self) -> None:
        try:
            if os.path.exists(ALERT_STATE_FILE):
                with open(ALERT_STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.last_radar_prices = data.get("last_radar_prices", {})
                    self.last_alert_targets = data.get("last_alert_targets", {})
        except Exception as e:
            logger.error(f"Failed to load alert state: {e}")

    def _save_alert_state(self) -> None:
        try:
            with open(ALERT_STATE_FILE, "w") as f:
                json.dump({
                    "last_radar_prices": self.last_radar_prices,
                    "last_alert_targets": self.last_alert_targets
                }, f)
        except Exception as e:
            logger.error(f"Failed to save alert state: {e}")

    async def process_new_candle(
        self,
        symbol: str,
        df: pd.DataFrame,
        daily_df: Optional[pd.DataFrame] = None,
        sector: str = "Unknown",
    ) -> None:
        """
        Entry point: called with a finalized 15m candle DataFrame.
        Evaluates Stage-A, Stage-B, and Re-entry conditions.
        Only processes finalized candles (Part N).

        Args:
            symbol: NSE trading symbol
            df: DataFrame with OHLCV columns and at least 20 rows (15m candles)
            daily_df: Daily OHLCV DataFrame for EMA-50/200 trend filter (optional)
            sector: Sector classification for the symbol
        """
        if len(df) < 21:
            logger.debug(f"{symbol}: insufficient candles ({len(df)} < 21), skipping")
            return

        df = IndicatorEngine.calculate_all(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        bar_index = len(df) - 1

        # Daily trend filter — check EMA-50 and EMA-200 on daily candles
        daily_trend_ok = self._check_daily_trend(symbol, daily_df, last)

        # Stage-A: Early Radar
        await self._check_early_radar(symbol, last, prev, daily_trend_ok, sector)

        # Stage-B: Entry Trigger
        triggered = await self._check_entry_trigger(symbol, last, prev, daily_trend_ok, sector, bar_index)

        # Stage-C: Re-entry (only if no fresh entry triggered)
        if not triggered:
            await self._check_retest_reentry(symbol, last, prev, sector, bar_index)

    # ──────────────────────────────────────────────
    # DAILY TREND FILTER
    # ──────────────────────────────────────────────

    def _check_daily_trend(
        self, symbol: str, daily_df: Optional[pd.DataFrame], last_15m: pd.Series
    ) -> bool:
        """
        Check if daily_close > daily_ema_50 AND daily_close > daily_ema_200.
        Falls back to True if daily_df not available (don't block scanning).
        """
        if daily_df is None or len(daily_df) < 200:
            return True  # graceful fallback

        daily_df = IndicatorEngine.calculate_all(daily_df)
        daily_last = daily_df.iloc[-1]
        close = daily_last.get("close", 0)
        ema50 = daily_last.get("ema_50", 0)
        ema200 = daily_last.get("ema_200", 0)

        ok = close > ema50 and close > ema200
        if not ok:
            logger.debug(f"{symbol}: daily trend bearish (close={close:.2f}, ema50={ema50:.2f}, ema200={ema200:.2f})")
        return ok

    # ──────────────────────────────────────────────
    # STAGE-A: EARLY RADAR (Part A)
    # ──────────────────────────────────────────────

    async def _check_early_radar(
        self,
        symbol: str,
        last: pd.Series,
        prev: pd.Series,
        daily_trend_ok: bool,
        sector: str,
    ) -> None:
        """Evaluate all 6 Stage-A conditions and emit EARLY_RADAR event if all pass."""
        failures: List[str] = []

        # 1) Compression
        rng_pct = last.get("rolling_range_pct", 999)
        if rng_pct > self.compression_pct:
            failures.append(f"COMPRESSION_FAIL(range={rng_pct:.2f}%>={self.compression_pct}%)")

        # 2) Near resistance
        dist_pct = last.get("distance_to_high_pct", 999)
        if dist_pct > self.near_res_pct:
            failures.append(f"NEAR_RESISTANCE_FAIL(dist={dist_pct:.2f}%>={self.near_res_pct}%)")

        # 3) RSI buildup zone
        rsi = last.get("rsi_14", 0)
        if not (self.radar_rsi_min <= rsi <= self.radar_rsi_max):
            failures.append(f"RSI_FAIL(rsi={rsi:.1f} not in [{self.radar_rsi_min},{self.radar_rsi_max}])")

        # 4) MACD histogram rising
        cur_hist = last.get("macd_hist", 0)
        prev_hist = prev.get("macd_hist", 0)
        if cur_hist <= prev_hist:
            failures.append(f"MACD_HIST_FAIL(cur={cur_hist:.4f}<=prev={prev_hist:.4f})")

        # 5) Volume not dead
        vol_ratio = last.get("vol_ratio", 0)
        if vol_ratio < self.radar_vol_ratio:
            failures.append(f"VOLUME_FAIL(ratio={vol_ratio:.2f}<{self.radar_vol_ratio})")

        # 6) Daily trend bullish
        if not daily_trend_ok:
            failures.append("DAILY_TREND_FAIL(close<ema50 or close<ema200)")

        if failures:
            logger.debug(f"{symbol} EARLY_RADAR: conditions not met — {', '.join(failures)}")
            return

        # All 6 passed
        current_price = float(last.get("close", 0))
        last_price = self.last_radar_prices.get(symbol)
        if last_price is not None:
            diff_pct = abs((current_price - last_price) / last_price) * 100
            if diff_pct <= 3.0:
                logger.debug(f"{symbol} EARLY_RADAR: Suppressing repetitive alert (price diff {diff_pct:.2f}% <= 3%)")
                return

        self.last_radar_prices[symbol] = current_price
        self._save_alert_state()
        if symbol not in self.radar_candidates:
            self.radar_candidates.append(symbol)

        logger.info(
            f"EARLY_RADAR triggered for {symbol}",
            extra={"reason_code": "EARLY_RADAR_FOUND", "symbol": symbol, "sector": sector},
        )
        
        await self.event_bus.publish("on_early_radar_found", {
            "symbol": symbol,
            "sector": sector,
            "price": float(last.get("close", 0)),
            "rsi": float(rsi),
            "macd_hist": float(cur_hist),
            "vol_ratio": float(vol_ratio),
            "compression_pct": float(rng_pct),
            "dist_to_high_pct": float(dist_pct),
            "reason_code": "EARLY_RADAR_FOUND",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ──────────────────────────────────────────────
    # STAGE-B: ENTRY TRIGGER (Parts B + K)
    # ──────────────────────────────────────────────

    async def _check_entry_trigger(
        self,
        symbol: str,
        last: pd.Series,
        prev: pd.Series,
        daily_trend_ok: bool,
        sector: str,
        bar_index: int,
    ) -> bool:
        """
        Evaluate all 6 Stage-B conditions including No-Chase rule.
        Returns True if entry signal was emitted.
        """
        failures: List[str] = []
        close = float(last.get("close", 0))

        # 1) Breakout confirmation — use PREVIOUS 20 bars high
        breakout_level = float(last.get("high_20_shifted", 0))
        if breakout_level <= 0:
            # Fallback: compute from prev bar's rolling high
            breakout_level = float(prev.get("high_20", close))
        if close <= breakout_level:
            failures.append(f"BREAKOUT_FAIL(close={close:.2f}<=level={breakout_level:.2f})")

        # 2) Volume surge
        vol_ratio = float(last.get("vol_ratio", 0))
        if vol_ratio < self.entry_vol_ratio:
            failures.append(f"VOLUME_FAIL(ratio={vol_ratio:.2f}<{self.entry_vol_ratio})")

        # 3) RSI entry zone
        rsi = float(last.get("rsi_14", 0))
        if not (self.entry_rsi_min < rsi < self.entry_rsi_max):
            failures.append(f"RSI_FAIL(rsi={rsi:.1f} not in ({self.entry_rsi_min},{self.entry_rsi_max}))")

        # 4) MACD confirmation
        macd = float(last.get("macd", 0))
        macd_signal = float(last.get("macd_signal", 0))
        if macd <= macd_signal:
            failures.append(f"MACD_FAIL(macd={macd:.4f}<=signal={macd_signal:.4f})")

        # 5) Daily trend
        if not daily_trend_ok:
            failures.append("DAILY_TREND_FAIL")

        # 6) No-Chase Rule (Part K)
        if breakout_level > 0:
            dist_from_breakout = ((close - breakout_level) / breakout_level) * 100
            if dist_from_breakout > self.no_chase_pct:
                failures.append(
                    f"NO_CHASE_RULE_HIT(distance={dist_from_breakout:.2f}%>{self.no_chase_pct}%)"
                )
        else:
            dist_from_breakout = 0.0

        if failures:
            logger.debug(
                f"{symbol} ENTRY_TRIGGER: conditions not met — {', '.join(failures)}",
                extra={"reason_codes": failures},
            )
            return False

        # All 6 passed — record breakout for re-entry tracking
        self.breakout_tracker.record_breakout(symbol, breakout_level, bar_index)

        sl_price = close * (1 - self.config.get("strategy", {}).get("stop_loss_pct", 3.0) / 100)
        target_price = close * (1 + self.config.get("strategy", {}).get("target_pct", 5.0) / 100)

        # Repetitive alert throttling (Part 6)
        last_target = self.last_alert_targets.get(symbol)
        if last_target is not None:
            diff_pct = abs((target_price - last_target) / last_target) * 100
            if diff_pct <= 3.0:
                logger.debug(f"{symbol} ENTRY_TRIGGER: Suppressing repetitive alert (target diff {diff_pct:.2f}% <= 3%)")
                return True # Technically triggered, but we don't alert

        self.last_alert_targets[symbol] = target_price
        self._save_alert_state()

        logger.info(
            f"ENTRY_TRIGGER for {symbol} @ {close:.2f} | SL={sl_price:.2f} | TP={target_price:.2f}",
            extra={"reason_code": "ENTRY_TRIGGERED_ALL_CONDITIONS_MET", "symbol": symbol},
        )

        await self.event_bus.publish("on_entry_triggered", {
            "symbol": symbol,
            "sector": sector,
            "entry_price": close,
            "sl": sl_price,
            "target": target_price,
            "breakout_level": breakout_level,
            "dist_from_breakout_pct": dist_from_breakout,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
            "macd": macd,
            "reason_code": "ENTRY_TRIGGERED_ALL_CONDITIONS_MET",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return True

    # ──────────────────────────────────────────────
    # STAGE-C: RE-ENTRY (Part C)
    # ──────────────────────────────────────────────

    async def _check_retest_reentry(
        self,
        symbol: str,
        last: pd.Series,
        prev: pd.Series,
        sector: str,
        bar_index: int,
    ) -> None:
        """Evaluate 4 re-entry conditions on a retest candle."""
        active = self.breakout_tracker.get_active_breakout(symbol, bar_index)
        if not active:
            return

        breakout_level = active["breakout_level"]
        close = float(last.get("close", 0))
        low = float(last.get("low", 0))
        failures: List[str] = []

        # 1) Price retests breakout level — low >= breakout * 0.995
        retest_floor = breakout_level * (1 - self.retest_tol_pct / 100)
        if low < retest_floor:
            failures.append(f"RETEST_FLOOR_FAIL(low={low:.2f}<floor={retest_floor:.2f})")

        # 2) Close back above breakout level
        if close <= breakout_level:
            failures.append(f"CLOSE_ABOVE_FAIL(close={close:.2f}<=level={breakout_level:.2f})")

        # 3) RSI still bullish
        rsi = float(last.get("rsi_14", 0))
        if rsi <= self.retest_rsi_min:
            failures.append(f"RSI_FAIL(rsi={rsi:.1f}<={self.retest_rsi_min})")

        # 4) Volume reconfirmation
        vol_ratio = float(last.get("vol_ratio", 0))
        if vol_ratio < self.retest_vol_ratio:
            failures.append(f"VOLUME_FAIL(ratio={vol_ratio:.2f}<{self.retest_vol_ratio})")

        if failures:
            logger.debug(f"{symbol} RETEST_REENTRY: not confirmed — {', '.join(failures)}")
            return

        # All 4 passed
        self.breakout_tracker.mark_entry_executed(symbol)
        sl_price = close * (1 - self.config.get("strategy", {}).get("stop_loss_pct", 3.0) / 100)
        target_price = close * (1 + self.config.get("strategy", {}).get("target_pct", 5.0) / 100)

        # Repetitive alert throttling
        last_target = self.last_alert_targets.get(symbol)
        if last_target is not None:
            diff_pct = abs((target_price - last_target) / last_target) * 100
            if diff_pct <= 3.0:
                logger.debug(f"{symbol} RETEST_REENTRY: Suppressing repetitive alert (target diff {diff_pct:.2f}% <= 3%)")
                return

        self.last_alert_targets[symbol] = target_price
        self._save_alert_state()

        logger.info(
            f"RETEST_REENTRY confirmed for {symbol} @ {close:.2f}",
            extra={"reason_code": "RETEST_REENTRY_CONFIRMED", "symbol": symbol},
        )

        await self.event_bus.publish("on_retest_reentry", {
            "symbol": symbol,
            "sector": sector,
            "entry_price": close,
            "sl": sl_price,
            "target": target_price,
            "breakout_level": breakout_level,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
            "reason_code": "RETEST_REENTRY_CONFIRMED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
