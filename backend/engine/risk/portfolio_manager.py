"""
risk/portfolio_manager.py
Implements Parts D, F, I, J of the trading engine specification:
  D — Position sizing formula (6-step)
  F — Pre-entry validation (7 risk guards)
  I — Drawdown guard / loss streak tracker
  J — Kill-switch daily loss monitor
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, time as dt_time
from typing import Dict, List, Optional, Any, Tuple
from backend.logging_config import get_logger

logger = get_logger(__name__)

# IST market hours (UTC+5:30 = UTC 03:45 – 10:00)
MARKET_OPEN_UTC = dt_time(3, 45)   # 09:15 IST
MARKET_CLOSE_UTC = dt_time(10, 0)  # 15:30 IST


class OpenPosition:
    """Represents a single open trade position."""

    def __init__(
        self,
        symbol: str,
        qty: int,
        entry_price: float,
        sl_price: float,
        target_price: float,
        risk_amount: float,
        sector: str,
        entry_mode: str,
        entry_time: datetime,
        is_paper: bool = True,
    ):
        self.symbol = symbol
        self.qty = qty
        self.entry_price = entry_price
        self.sl_price = sl_price
        self.target_price = target_price
        self.risk_amount = risk_amount
        self.sector = sector
        self.entry_mode = entry_mode
        self.entry_time = entry_time
        self.is_paper = is_paper
        # Mutable SL for breakeven/trail updates
        self.current_sl = sl_price
        self.breakeven_activated = False
        self.trail_activated = False


class SizeResult:
    """Output of position sizing calculation (Part D)."""

    def __init__(
        self,
        qty: int,
        sl_price: float,
        target_price: float,
        risk_amount: float,
        reward_amount: float,
        risk_reward_ratio: float,
    ):
        self.qty = qty
        self.sl_price = sl_price
        self.target_price = target_price
        self.risk_amount = risk_amount
        self.reward_amount = reward_amount
        self.risk_reward_ratio = risk_reward_ratio

    def to_dict(self) -> Dict[str, Any]:
        return {
            "qty": self.qty,
            "sl_price": self.sl_price,
            "target_price": self.target_price,
            "risk_amount": self.risk_amount,
            "reward_amount": self.reward_amount,
            "risk_reward_ratio": self.risk_reward_ratio,
        }


class PortfolioManager:
    """
    Manages portfolio state, position sizing, and risk controls.
    Implements Parts D, F, I, J of the trading engine specification.
    """

    def __init__(self, config: dict):
        self.config = config
        risk = config.get("risk", {})
        paper = config.get("paper_trading", {})
        strategy = config.get("strategy", {})

        # Capital
        self.total_equity: float = paper.get("initial_capital", 100000.0)
        self.available_cash: float = self.total_equity

        # Risk parameters
        self.risk_per_trade_pct: float = risk.get("risk_per_trade_pct", 0.75)
        self.stop_loss_pct: float = strategy.get("stop_loss_pct", 3.0)
        self.target_pct: float = strategy.get("target_pct", 5.0)
        self.max_concurrent_positions: int = risk.get("max_concurrent_positions", 5)
        self.max_positions_per_sector: int = risk.get("max_positions_per_sector", 2)
        self.portfolio_risk_limit_pct: float = risk.get("portfolio_risk_limit_pct", 10.0)
        self.kill_switch_daily_loss_pct: float = risk.get("kill_switch_daily_loss_pct", 5.0)

        # Drawdown guard (Part I)
        self.loss_streak_threshold: int = risk.get("loss_streak_threshold", 3)
        self.size_reduction_pct: float = risk.get("size_reduction_pct", 50)
        self.size_reduction_trade_count: int = risk.get("size_reduction_trade_count", 5)
        self.consecutive_losses: int = 0
        self.consecutive_wins: int = 0
        self.drawdown_guard_active: bool = False
        self.drawdown_guard_remaining_trades: int = 0

        # Kill-switch (Part J)
        self.kill_switch_active: bool = False
        self.daily_closed_pnl: float = 0.0

        # State
        self.open_positions: Dict[str, OpenPosition] = {}
        self.event_bus = None  # Set by core.py after init

    # ──────────────────────────────────────────────
    # PART D: POSITION SIZING
    # ──────────────────────────────────────────────

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_pct: Optional[float] = None,
        target_pct: Optional[float] = None,
    ) -> Optional[SizeResult]:
        """
        6-step position sizing formula (Part D).

        Args:
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss_pct: Override SL % (uses config default if None)
            target_pct: Override target % (uses config default if None)

        Returns:
            SizeResult if valid, None if rejected
        """
        # Kill-switch guard — block all sizing when activated
        if self.kill_switch_active:
            logger.warning(
                f"{symbol}: position sizing blocked — kill switch active",
                extra={"reason_code": "KILL_SWITCH_ACTIVE"},
            )
            return None

        sl_pct = stop_loss_pct if stop_loss_pct is not None else self.stop_loss_pct
        tgt_pct = target_pct if target_pct is not None else self.target_pct

        # Step 1: Risk amount
        risk_amount = self.total_equity * (self.risk_per_trade_pct / 100)

        # Step 2: SL price
        sl_price = entry_price * (1 - sl_pct / 100)

        # Step 3: Risk per share
        risk_per_share = entry_price - sl_price

        if risk_per_share <= 0:
            logger.error(
                f"{symbol}: invalid risk_per_share={risk_per_share} (entry={entry_price}, sl={sl_price})",
                extra={"reason_code": "INVALID_RISK_PER_SHARE"},
            )
            return None

        # Step 4: Quantity (round down)
        qty = math.floor(risk_amount / risk_per_share)

        # Apply drawdown guard reduction (Part I)
        if self.drawdown_guard_active and qty > 0:
            original_qty = qty
            qty = math.floor(qty * (1 - self.size_reduction_pct / 100))
            logger.info(
                f"{symbol}: drawdown guard active — qty reduced {original_qty} → {qty}",
                extra={"reason_code": "DRAWDOWN_GUARD_ACTIVE_TRADING_50PCT"},
            )

        # Step 5: Validate
        if qty <= 0:
            logger.warning(
                f"{symbol}: qty={qty} after sizing — insufficient capital",
                extra={"reason_code": "INSUFFICIENT_CAPITAL"},
            )
            return None

        trade_value = qty * entry_price
        if trade_value > self.available_cash:
            logger.warning(
                f"{symbol}: trade_value={trade_value:.2f} > available_cash={self.available_cash:.2f}",
                extra={"reason_code": "INSUFFICIENT_LIQUIDITY"},
            )
            return None

        # Step 6: Target price
        target_price = entry_price * (1 + tgt_pct / 100)
        reward_amount = qty * (target_price - entry_price)
        rr_ratio = round(reward_amount / risk_amount, 2) if risk_amount > 0 else 0.0

        return SizeResult(
            qty=qty,
            sl_price=round(sl_price, 2),
            target_price=round(target_price, 2),
            risk_amount=round(risk_amount, 2),
            reward_amount=round(reward_amount, 2),
            risk_reward_ratio=rr_ratio,
        )

    # ──────────────────────────────────────────────
    # PART F: PRE-ENTRY VALIDATION (7 checks)
    # ──────────────────────────────────────────────

    def pre_entry_validate(
        self,
        symbol: str,
        sector: str,
        risk_amount: float,
        data_quality_ok: bool = True,
    ) -> Tuple[bool, str]:
        """
        Run all 7 pre-entry guards before placing any order.

        Returns:
            (passed: bool, reason_code: str)
        """
        # 1) Kill-switch check (Part J)
        if self.kill_switch_active:
            return False, "KILL_SWITCH_ACTIVE"

        # 2) Market hours check
        if not self._is_market_open():
            return False, "MARKET_CLOSED"

        # 3) Max concurrent positions
        if len(self.open_positions) >= self.max_concurrent_positions:
            return False, f"MAX_POSITIONS_REACHED({len(self.open_positions)}/{self.max_concurrent_positions})"

        # 4) Max positions per sector
        sector_count = sum(
            1 for p in self.open_positions.values() if p.sector == sector
        )
        if sector_count >= self.max_positions_per_sector:
            return False, f"SECTOR_LIMIT_HIT(sector={sector},{sector_count}/{self.max_positions_per_sector})"

        # 5) Portfolio risk limit (10% of equity)
        total_open_risk = sum(p.risk_amount for p in self.open_positions.values())
        max_portfolio_risk = self.total_equity * (self.portfolio_risk_limit_pct / 100)
        if total_open_risk + risk_amount > max_portfolio_risk:
            return False, (
                f"PORTFOLIO_RISK_LIMIT_EXCEEDED"
                f"(open={total_open_risk:.0f}+new={risk_amount:.0f}"
                f">max={max_portfolio_risk:.0f})"
            )

        # 6) Data quality
        if not data_quality_ok:
            return False, "DATA_QUALITY_FLAG"

        logger.info(
            f"{symbol}: pre-entry validation PASSED",
            extra={"reason_code": "PRE_ENTRY_VALIDATION_PASSED"},
        )
        return True, "PRE_ENTRY_VALIDATION_PASSED"

    # ──────────────────────────────────────────────
    # PART I: LOSS STREAK TRACKER
    # ──────────────────────────────────────────────

    def record_trade_result(self, exit_reason: str, pnl: float) -> None:
        """
        Update consecutive loss/win counters on trade close.
        Activates drawdown guard after N consecutive losses.
        """
        is_loss = exit_reason in ("SL_HIT", "TIME_EXIT") or pnl < 0

        if is_loss:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            logger.info(f"Loss streak: {self.consecutive_losses}")
        else:
            self.consecutive_wins += 1
            self.consecutive_losses = 0

        # Activate drawdown guard
        if self.consecutive_losses >= self.loss_streak_threshold and not self.drawdown_guard_active:
            self.drawdown_guard_active = True
            self.drawdown_guard_remaining_trades = self.size_reduction_trade_count
            logger.warning(
                f"Drawdown guard ACTIVATED after {self.consecutive_losses} consecutive losses. "
                f"Sizing at {100 - self.size_reduction_pct:.0f}% for next "
                f"{self.drawdown_guard_remaining_trades} trades.",
                extra={"reason_code": "DRAWDOWN_GUARD_ACTIVE"},
            )

        # Decrement guard counter
        if self.drawdown_guard_active:
            self.drawdown_guard_remaining_trades -= 1
            if self.drawdown_guard_remaining_trades <= 0:
                self.drawdown_guard_active = False
                self.consecutive_losses = 0
                logger.info(
                    "Drawdown guard DEACTIVATED — resuming normal position sizing.",
                    extra={"reason_code": "DRAWDOWN_GUARD_DEACTIVATED"},
                )

    # ──────────────────────────────────────────────
    # PART J: KILL-SWITCH
    # ──────────────────────────────────────────────

    async def update_daily_pnl(self, pnl: float) -> None:
        """
        Add closed trade PnL to daily total and check kill-switch threshold.
        Call on every trade close.
        """
        self.daily_closed_pnl += pnl
        daily_pnl_pct = (self.daily_closed_pnl / self.total_equity) * 100

        if daily_pnl_pct <= -self.kill_switch_daily_loss_pct and not self.kill_switch_active:
            self.kill_switch_active = True
            logger.critical(
                f"KILL SWITCH ACTIVATED — daily PnL: {daily_pnl_pct:.2f}% "
                f"(₹{self.daily_closed_pnl:,.0f})",
                extra={"reason_code": "KILL_SWITCH_ACTIVATED_DAILY_LOSS_LIMIT",
                       "daily_pnl_pct": daily_pnl_pct},
            )
            if self.event_bus:
                await self.event_bus.publish("on_kill_switch_activated", {
                    "reason": "Daily loss limit exceeded",
                    "daily_pnl": self.daily_closed_pnl,
                    "daily_pnl_pct": daily_pnl_pct,
                    "action": "New entries disabled until manual override",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason_code": "KILL_SWITCH_ACTIVATED_DAILY_LOSS_LIMIT",
                })

    def reset_daily_state(self) -> None:
        """Reset daily PnL counters at market close (called by scheduler)."""
        logger.info(
            f"Daily state reset. Final daily PnL: ₹{self.daily_closed_pnl:,.0f}",
            extra={"reason_code": "DAILY_RESET"},
        )
        self.daily_closed_pnl = 0.0
        self.kill_switch_active = False

    def manual_override_kill_switch(self) -> None:
        """Admin manual override to re-enable trading after kill-switch."""
        self.kill_switch_active = False
        logger.warning(
            "Kill-switch manually overridden by admin.",
            extra={"reason_code": "KILL_SWITCH_MANUAL_OVERRIDE"},
        )

    # ──────────────────────────────────────────────
    # POSITION MANAGEMENT
    # ──────────────────────────────────────────────

    def add_position(self, position: OpenPosition) -> None:
        """Record a new open position and deduct from available cash."""
        self.open_positions[position.symbol] = position
        self.available_cash -= position.qty * position.entry_price
        logger.info(
            f"Position opened: {position.symbol} | qty={position.qty} "
            f"@ {position.entry_price:.2f} | sector={position.sector}",
        )

    def remove_position(self, symbol: str, exit_price: float, exit_reason: str) -> float:
        """
        Close a position, calculate PnL, return to cash pool.
        Returns realized PnL.
        """
        pos = self.open_positions.pop(symbol, None)
        if not pos:
            return 0.0

        pnl = (exit_price - pos.entry_price) * pos.qty
        self.available_cash += pos.qty * exit_price
        self.total_equity += pnl

        self.record_trade_result(exit_reason, pnl)
        logger.info(
            f"Position closed: {symbol} | exit={exit_price:.2f} "
            f"| pnl=₹{pnl:,.2f} | reason={exit_reason}",
        )
        return pnl

    def update_sl(self, symbol: str, new_sl: float) -> None:
        """Update stop loss for an open position (breakeven/trail)."""
        if symbol in self.open_positions:
            self.open_positions[symbol].current_sl = new_sl

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────

    @staticmethod
    def _is_market_open() -> bool:
        """Check if current UTC time is within NSE market hours (09:15–15:30 IST)."""
        now_utc = datetime.now(timezone.utc).time()
        return MARKET_OPEN_UTC <= now_utc <= MARKET_CLOSE_UTC

    def get_unrealized_pnl(self, ltp_map: Dict[str, float]) -> float:
        """Calculate total unrealized PnL given a symbol→LTP map."""
        total = 0.0
        for sym, pos in self.open_positions.items():
            ltp = ltp_map.get(sym, pos.entry_price)
            total += (ltp - pos.entry_price) * pos.qty
        return total

    def get_snapshot(self) -> Dict[str, Any]:
        """Return portfolio state snapshot for reporting."""
        return {
            "equity": self.total_equity,
            "cash": self.available_cash,
            "open_positions": len(self.open_positions),
            "daily_closed_pnl": self.daily_closed_pnl,
            "kill_switch_active": self.kill_switch_active,
            "drawdown_guard_active": self.drawdown_guard_active,
            "consecutive_losses": self.consecutive_losses,
        }
