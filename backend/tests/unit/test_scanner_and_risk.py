"""
Unit tests for SignalScanner — Stage-A, Stage-B, Re-entry conditions.
"""
import asyncio
import pandas as pd
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock


def make_test_df(n: int = 30, close_series=None, rsi_val=55.0, vol_ratio=1.0) -> pd.DataFrame:
    """Build a minimal test DataFrame that already has computed indicator columns."""
    closes = close_series or [100.0 + i * 0.05 for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [100000] * n

    df = pd.DataFrame({
        "datetime": pd.date_range("2024-01-01 09:15", periods=n, freq="15min"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    # Pre-inject indicator columns (bypass IndicatorEngine for unit test speed)
    df["rsi_14"] = rsi_val
    df["macd"] = 0.005
    df["macd_signal"] = 0.003
    df["macd_hist"] = 0.002
    df["vol_sma_20"] = df["volume"].rolling(20).mean().fillna(100000)
    df["vol_ratio"] = vol_ratio
    df["high_20"] = df["high"].rolling(20).max().fillna(df["high"])
    df["low_20"] = df["low"].rolling(20).min().fillna(df["low"])
    df["high_20_shifted"] = df["high_20"].shift(1).fillna(df["high_20"])
    df["rolling_range_pct"] = ((df["high_20"] - df["low_20"]) / df["close"]) * 100
    df["distance_to_high_pct"] = ((df["high_20"] - df["close"]) / df["close"]) * 100
    df["ema_50"] = df["close"].ewm(span=50).mean()
    df["ema_200"] = df["close"].ewm(span=200).mean()
    return df


def make_scanner(config_overrides=None):
    from backend.engine.signals.scanner import SignalScanner
    config = {
        "strategy": {
            "early_radar_compression_pct": 3.5,
            "early_radar_near_resistance_pct": 1.5,
            "early_radar_rsi_min": 50,
            "early_radar_rsi_max": 62,
            "early_radar_vol_ratio_min": 0.8,
            "entry_rsi_min": 52,
            "entry_rsi_max": 72,
            "entry_vol_ratio_min": 1.5,
            "no_chase_pct": 1.5,
            "lookback_breakout": 20,
            "retest_tolerance_pct": 0.5,
            "retest_rsi_min": 50,
            "retest_vol_ratio_min": 1.1,
            "stop_loss_pct": 3.0,
            "target_pct": 5.0,
            "breakout_tracking_window": 50,
        }
    }
    if config_overrides:
        config["strategy"].update(config_overrides)

    event_bus = MagicMock()
    event_bus.subscribe = MagicMock()
    event_bus.publish = AsyncMock()
    return SignalScanner(event_bus, config)


class TestStageAEarlyRadar:
    def test_all_conditions_pass_emits_event(self):
        scanner = make_scanner()

        # Build a tight consolidation setup
        closes = [100.0] * 30  # completely flat = 0% range
        df = make_test_df(n=30, close_series=closes, rsi_val=55.0, vol_ratio=0.9)
        # Near resistance: set high_20 just 1% above close
        df["high_20"] = 101.0
        df["low_20"] = 99.5
        df["rolling_range_pct"] = 1.5   # < 3.5 ✓
        df["distance_to_high_pct"] = 1.0  # < 1.5 ✓
        # MACD hist must be RISING: last > prev
        df["macd_hist"] = 0.001  # all bars set to 0.001
        df.loc[df.index[-1], "macd_hist"] = 0.003  # last bar higher → rising ✓
        last = df.iloc[-1]
        prev = df.iloc[-2]

        asyncio.run(scanner._check_early_radar("TEST", last, prev, True, "IT"))
        scanner.event_bus.publish.assert_awaited_once()
        args = scanner.event_bus.publish.call_args[0]
        assert args[0] == "on_early_radar_found"
        assert args[1]["symbol"] == "TEST"

    def test_rsi_too_high_fails(self):
        scanner = make_scanner()
        df = make_test_df(n=30, rsi_val=70.0)  # RSI > 62 → fail
        df["rolling_range_pct"] = 1.5
        df["distance_to_high_pct"] = 1.0
        df["macd_hist"] = 0.002
        last = df.iloc[-1]
        prev = df.iloc[-2]

        asyncio.run(scanner._check_early_radar("TEST", last, prev, True, "IT"))
        scanner.event_bus.publish.assert_not_awaited()

    def test_daily_trend_fail_blocks_radar(self):
        scanner = make_scanner()
        df = make_test_df(n=30, rsi_val=55.0, vol_ratio=0.9)
        df["rolling_range_pct"] = 1.5
        df["distance_to_high_pct"] = 1.0
        df["macd_hist"] = 0.002
        last = df.iloc[-1]
        prev = df.iloc[-2]

        asyncio.run(scanner._check_early_radar("TEST", last, prev, False, "IT"))  # daily_trend_ok=False
        scanner.event_bus.publish.assert_not_awaited()


class TestStageBEntryTrigger:
    def test_breakout_with_all_conditions_emits_event(self):
        scanner = make_scanner()
        closes = [99.0] * 29 + [101.5]  # big move on last candle
        df = make_test_df(n=30, close_series=closes, rsi_val=60.0, vol_ratio=1.8)
        df["high_20_shifted"] = 100.0  # breakout level
        df["macd"] = 0.010
        df["macd_signal"] = 0.005
        last = df.iloc[-1]
        prev = df.iloc[-2]

        result = asyncio.run(scanner._check_entry_trigger("INFY", last, prev, True, "IT", 29))
        assert result is True
        scanner.event_bus.publish.assert_awaited_once()
        args = scanner.event_bus.publish.call_args[0]
        assert args[0] == "on_entry_triggered"

    def test_no_chase_rule_blocks_entry(self):
        scanner = make_scanner()
        # Price is 3% above breakout level (> 1.5% limit)
        closes = [99.0] * 29 + [103.0]
        df = make_test_df(n=30, close_series=closes, rsi_val=60.0, vol_ratio=2.0)
        df["high_20_shifted"] = 100.0  # breakout level = 100, close = 103 → 3% away
        df["macd"] = 0.010
        df["macd_signal"] = 0.005
        last = df.iloc[-1]
        prev = df.iloc[-2]

        result = asyncio.run(scanner._check_entry_trigger("INFY", last, prev, True, "IT", 29))
        assert result is False  # no-chase rule hit

    def test_insufficient_volume_blocks_entry(self):
        scanner = make_scanner()
        closes = [99.0] * 29 + [101.5]
        df = make_test_df(n=30, close_series=closes, rsi_val=60.0, vol_ratio=1.0)  # vol_ratio < 1.5
        df["high_20_shifted"] = 100.0
        df["macd"] = 0.010
        df["macd_signal"] = 0.005
        last = df.iloc[-1]
        prev = df.iloc[-2]

        result = asyncio.run(scanner._check_entry_trigger("INFY", last, prev, True, "IT", 29))
        assert result is False  # VOLUME_FAIL


class TestPositionSizing:
    def test_basic_sizing(self):
        from backend.engine.risk.portfolio_manager import PortfolioManager
        config = {
            "risk": {"risk_per_trade_pct": 0.75, "max_concurrent_positions": 5,
                     "max_positions_per_sector": 2, "portfolio_risk_limit_pct": 10.0,
                     "kill_switch_daily_loss_pct": 5.0, "loss_streak_threshold": 3,
                     "size_reduction_pct": 50, "size_reduction_trade_count": 5},
            "strategy": {"stop_loss_pct": 3.0, "target_pct": 5.0},
            "paper_trading": {"initial_capital": 100000.0},
        }
        pm = PortfolioManager(config)
        result = pm.calculate_position_size("INFY", entry_price=1000.0)

        assert result is not None
        assert result.qty == 25  # 750 / 30 = 25
        assert result.sl_price == 970.0
        assert result.target_price == 1050.0
        assert result.risk_amount == 750.0

    def test_kill_switch_blocks_sizing(self):
        from backend.engine.risk.portfolio_manager import PortfolioManager
        config = {
            "risk": {"risk_per_trade_pct": 0.75, "max_concurrent_positions": 5,
                     "max_positions_per_sector": 2, "portfolio_risk_limit_pct": 10.0,
                     "kill_switch_daily_loss_pct": 5.0, "loss_streak_threshold": 3,
                     "size_reduction_pct": 50, "size_reduction_trade_count": 5},
            "strategy": {"stop_loss_pct": 3.0, "target_pct": 5.0},
            "paper_trading": {"initial_capital": 100000.0},
        }
        pm = PortfolioManager(config)
        pm.kill_switch_active = True
        result = pm.calculate_position_size("INFY", entry_price=1000.0)
        assert result is None  # kill switch blocks

    def test_drawdown_guard_reduces_qty(self):
        from backend.engine.risk.portfolio_manager import PortfolioManager
        config = {
            "risk": {"risk_per_trade_pct": 0.75, "max_concurrent_positions": 5,
                     "max_positions_per_sector": 2, "portfolio_risk_limit_pct": 10.0,
                     "kill_switch_daily_loss_pct": 5.0, "loss_streak_threshold": 3,
                     "size_reduction_pct": 50, "size_reduction_trade_count": 5},
            "strategy": {"stop_loss_pct": 3.0, "target_pct": 5.0},
            "paper_trading": {"initial_capital": 100000.0},
        }
        pm = PortfolioManager(config)
        pm.drawdown_guard_active = True
        result = pm.calculate_position_size("INFY", entry_price=1000.0)
        assert result is not None
        assert result.qty == 12  # floor(25 * 0.5) = 12


class TestPaperBroker:
    def test_buy_order_applies_slippage_upward(self):
        from backend.engine.brokers.paper_broker import PaperBroker
        config = {"paper_trading": {"entry_slippage_max_pct": 0.5, "exit_slippage_max_pct": 0.3,
                                     "brokerage_pct": 0.03, "initial_capital": 100000.0}}
        broker = PaperBroker(config)
        resp = asyncio.run(broker.place_order("INFY", "BUY", 10, "MARKET", 1000.0))
        assert resp["status"] == "FILLED"
        assert resp["filled_price"] >= 1000.0  # BUY slips up

    def test_fees_calculated_correctly(self):
        from backend.engine.brokers.paper_broker import PaperBroker
        config = {"paper_trading": {"entry_slippage_max_pct": 0.0, "exit_slippage_max_pct": 0.0,
                                     "brokerage_pct": 0.03, "initial_capital": 100000.0}}
        broker = PaperBroker(config)
        resp = asyncio.run(broker.place_order("INFY", "BUY", 100, "MARKET", 1000.0))
        # fees = 100 * 1000 * 0.03/100 = 30
        assert abs(resp["fees"] - 30.0) < 0.01
