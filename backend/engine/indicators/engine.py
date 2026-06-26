"""
engine/indicators/engine.py
Calculates all technical indicators using pure pandas/numpy.
No external TA library required — works on Python 3.11+.

Indicators computed:
  - rsi_14          : RSI(14) via Wilder's exponential smoothing
  - macd            : MACD line (EMA12 - EMA26)
  - macd_signal     : Signal line (EMA9 of MACD)
  - macd_hist       : Histogram (MACD - signal)
  - ema_50          : EMA(50) of close
  - ema_200         : EMA(200) of close
  - vol_sma_20      : SMA(20) of volume
  - high_20         : Rolling max of high over 20 bars
  - low_20          : Rolling min of low over 20 bars
  - high_20_shifted : high_20 shifted 1 bar back (previous 20-bar high for breakout level)
  - rolling_range_pct : ((high_20 - low_20) / close) * 100
  - distance_to_high_pct : ((high_20 - close) / close) * 100
  - vol_ratio       : volume / vol_sma_20
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from typing import List
from backend.logging_config import get_logger

logger = get_logger(__name__)

_REQUIRED_COLS: List[str] = ["open", "high", "low", "close", "volume"]


class IndicatorEngine:
    """
    Stateless indicator calculator.
    All methods are @staticmethod and operate on copies of the input DataFrame.
    """

    @staticmethod
    def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all indicators and return an enriched copy of df.

        Args:
            df: OHLCV DataFrame with at least columns open, high, low, close, volume

        Returns:
            DataFrame with all indicator columns added.

        Raises:
            ValueError: if required columns are missing.
        """
        IndicatorEngine._validate_columns(df)
        df = df.copy()

        # Momentum
        df = IndicatorEngine._calculate_rsi(df, period=14)
        df = IndicatorEngine._calculate_macd(df, fast=12, slow=26, signal=9)

        # Trend
        df = IndicatorEngine._calculate_ema(df, period=50, col_name="ema_50")
        df = IndicatorEngine._calculate_ema(df, period=200, col_name="ema_200")

        # Volume & rolling windows
        df = IndicatorEngine._calculate_rolling_stats(df)

        # Derived signals
        df = IndicatorEngine._calculate_derived(df)

        return df

    # ──────────────────────────────────────────────
    # RSI — Wilder's Smoothed Moving Average
    # ──────────────────────────────────────────────

    @staticmethod
    def _calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        RSI using Wilder's exponential smoothing (RMA).
        RSI = 100 - (100 / (1 + RS))
        RS  = avg_gain / avg_loss over `period` bars.
        """
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        # Wilder's smoothing: alpha = 1/period
        alpha = 1.0 / period
        avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi_14"] = (100 - (100 / (1 + rs))).round(2)
        df["rsi_14"] = df["rsi_14"].fillna(50.0)  # neutral fallback
        return df

    # ──────────────────────────────────────────────
    # MACD
    # ──────────────────────────────────────────────

    @staticmethod
    def _calculate_macd(
        df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        """
        MACD = EMA(fast) - EMA(slow)
        Signal = EMA(signal) of MACD
        Histogram = MACD - Signal
        """
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()

        df["macd"] = macd_line.round(4)
        df["macd_signal"] = signal_line.round(4)
        df["macd_hist"] = (macd_line - signal_line).round(4)
        return df

    # ──────────────────────────────────────────────
    # EMA
    # ──────────────────────────────────────────────

    @staticmethod
    def _calculate_ema(df: pd.DataFrame, period: int, col_name: str) -> pd.DataFrame:
        """Exponential Moving Average of close price."""
        df[col_name] = df["close"].ewm(span=period, adjust=False).mean().round(2)
        return df

    # ──────────────────────────────────────────────
    # ROLLING STATS
    # ──────────────────────────────────────────────

    @staticmethod
    def _calculate_rolling_stats(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
        """
        Volume SMA, rolling high/low, shifted high for breakout detection.
        """
        df["vol_sma_20"] = df["volume"].rolling(window=window, min_periods=1).mean()
        df["high_20"] = df["high"].rolling(window=window, min_periods=1).max()
        df["low_20"] = df["low"].rolling(window=window, min_periods=1).min()
        # Shift by 1: use PREVIOUS 20-bar high as breakout level (Part B spec)
        df["high_20_shifted"] = df["high_20"].shift(1)
        return df

    # ──────────────────────────────────────────────
    # DERIVED SIGNAL INPUTS
    # ──────────────────────────────────────────────

    @staticmethod
    def _calculate_derived(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute percentage-based inputs used directly in scanner conditions.
        """
        close = df["close"].replace(0, np.nan)

        # Compression: range of last 20 bars as % of close (Part A, condition 1)
        range_20 = df["high_20"] - df["low_20"]
        df["rolling_range_pct"] = ((range_20 / close) * 100).round(3)

        # Distance to resistance: how far close is from 20-bar high (Part A, condition 2)
        df["distance_to_high_pct"] = (((df["high_20"] - close) / close) * 100).round(3)

        # Volume ratio: current vol vs 20-bar average (Parts A/B/C conditions)
        df["vol_ratio"] = (df["volume"] / df["vol_sma_20"].replace(0, np.nan)).round(3)
        df["vol_ratio"] = df["vol_ratio"].fillna(1.0)

        return df

    # ──────────────────────────────────────────────
    # VALIDATION
    # ──────────────────────────────────────────────

    @staticmethod
    def _validate_columns(df: pd.DataFrame) -> None:
        """Raise ValueError if required OHLCV columns are missing."""
        missing = [c for c in _REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"IndicatorEngine: missing required columns: {missing}")
        if len(df) == 0:
            raise ValueError("IndicatorEngine: DataFrame is empty")
