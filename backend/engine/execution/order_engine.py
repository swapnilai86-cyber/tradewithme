"""
execution/order_engine.py
Implements Parts E, G, L of the trading engine specification:
  E — Entry modes: single_shot and pilot_add
  G — Exit logic: SL hit, TP hit, Time stop, Breakeven, Trail stop
  L — Time conversion: 480 bars = 20 trading sessions
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from backend.logging_config import get_logger
from backend.engine.risk.portfolio_manager import PortfolioManager, OpenPosition

logger = get_logger(__name__)

# Part L: 20 sessions × 360 min/session = 7200 min = 480 bars @ 15m
MAX_HOLD_MINUTES = 7200


class OrderEngine:
    """
    Handles trade entry (single shot / pilot+add) and exit (5 types).
    Implements Parts E, G, L.
    """

    def __init__(self, broker, portfolio_manager: PortfolioManager, event_bus, config: dict):
        self.broker = broker
        self.pm = portfolio_manager
        self.event_bus = event_bus
        self.config = config
        strategy = config.get("strategy", {})

        # Entry mode
        self.entry_mode: str = strategy.get("entry_mode", "single_shot")
        self.pilot_wait_bars: int = strategy.get("pilot_add_wait_bars", 10)

        # Exit features
        self.enable_breakeven: bool = strategy.get("enable_breakeven_stop", True)
        self.breakeven_trigger_pct: float = strategy.get("breakeven_trigger_pct", 2.5)
        self.enable_trail: bool = strategy.get("enable_trail_stop", True)
        self.trail_trigger_pct: float = strategy.get("trail_trigger_pct", 4.0)
        self.trail_distance_pct: float = strategy.get("trail_distance_pct", 1.5)

        # Max hold
        self.max_hold_minutes: int = config.get("strategy", {}).get("max_hold_minutes", MAX_HOLD_MINUTES)

        # Pilot tracking: symbol -> {pilot_qty, full_qty, pilot_price, bars_waited}
        self._pilot_state: Dict[str, dict] = {}

    # ──────────────────────────────────────────────
    # PART E: ENTRY
    # ──────────────────────────────────────────────

    async def execute_entry(self, signal_data: dict) -> None:
        """Route entry to single_shot or pilot_add mode."""
        symbol = signal_data["symbol"]
        entry_price = signal_data["entry_price"]
        sector = signal_data.get("sector", "Unknown")

        # Size position
        size = self.pm.calculate_position_size(symbol, entry_price)
        if size is None:
            return

        # Pre-entry validation (7 guards — Part F)
        passed, reason = self.pm.pre_entry_validate(
            symbol=symbol,
            sector=sector,
            risk_amount=size.risk_amount,
        )
        if not passed:
            logger.warning(
                f"{symbol}: entry rejected — {reason}",
                extra={"reason_code": reason},
            )
            return

        if self.entry_mode == "pilot_add":
            await self._execute_pilot_entry(signal_data, size, sector)
        else:
            await self._execute_single_shot(signal_data, size, sector)

    async def _execute_single_shot(self, signal_data: dict, size, sector: str) -> None:
        """Mode A: Place full qty as single market order."""
        symbol = signal_data["entry_price"]
        symbol_name = signal_data["symbol"]
        entry_price = signal_data["entry_price"]

        logger.info(f"[SINGLE_SHOT] Placing BUY {size.qty} {symbol_name} @ MARKET")
        resp = await self.broker.place_order(
            symbol=symbol_name,
            side="BUY",
            qty=size.qty,
            order_type="MARKET",
            price=entry_price,
        )

        if resp.get("status") == "FILLED" or resp.get("filled_qty", 0) > 0:
            filled_price = resp.get("filled_price", entry_price)
            fees = resp.get("fees", 0.0)

            # Recalculate SL/target using actual filled price
            sl_pct = self.config.get("strategy", {}).get("stop_loss_pct", 3.0)
            tgt_pct = self.config.get("strategy", {}).get("target_pct", 5.0)
            actual_sl = filled_price * (1 - sl_pct / 100)
            actual_target = filled_price * (1 + tgt_pct / 100)

            position = OpenPosition(
                symbol=symbol_name,
                qty=size.qty,
                entry_price=filled_price,
                sl_price=actual_sl,
                target_price=actual_target,
                risk_amount=size.risk_amount,
                sector=sector,
                entry_mode="single_shot",
                entry_time=datetime.now(timezone.utc),
                is_paper=not self.config.get("risk", {}).get("live_mode", False),
            )
            self.pm.add_position(position)

            logger.info(
                f"[ENTRY_FILLED] {symbol_name} | filled={filled_price:.2f} "
                f"(signal={entry_price:.2f}) | sl={actual_sl:.2f} | tp={actual_target:.2f} "
                f"| qty={size.qty} | fees={fees:.2f}",
                extra={"reason_code": "ENTRY_FILLED_SINGLE_SHOT"},
            )
            await self.event_bus.publish("on_trade_executed", {
                "symbol": symbol_name,
                "sector": sector,
                "qty": size.qty,
                "entry_price": filled_price,
                "signal_price": entry_price,
                "sl": actual_sl,
                "target": actual_target,
                "risk_amount": size.risk_amount,
                "reward_amount": size.reward_amount,
                "rr_ratio": size.risk_reward_ratio,
                "fees": fees,
                "entry_mode": "single_shot",
                "status": "OPEN",
                "reason_code": "ENTRY_FILLED_SINGLE_SHOT",
            })

    async def _execute_pilot_entry(self, signal_data: dict, size, sector: str) -> None:
        """Mode B: Place 50% pilot order, wait for retest, then add remaining 50%."""
        symbol_name = signal_data["symbol"]
        entry_price = signal_data["entry_price"]
        pilot_qty = math.floor(size.qty * 0.5)

        if pilot_qty <= 0:
            logger.warning(f"{symbol_name}: pilot qty too small ({pilot_qty}), switching to single shot")
            await self._execute_single_shot(signal_data, size, sector)
            return

        logger.info(f"[PILOT_ADD] Placing pilot BUY {pilot_qty} {symbol_name} @ MARKET")
        resp = await self.broker.place_order(
            symbol=symbol_name, side="BUY", qty=pilot_qty,
            order_type="MARKET", price=entry_price,
        )

        if resp.get("status") == "FILLED" or resp.get("filled_qty", 0) > 0:
            pilot_price = resp.get("filled_price", entry_price)
            sl_pct = self.config.get("strategy", {}).get("stop_loss_pct", 3.0)
            tgt_pct = self.config.get("strategy", {}).get("target_pct", 5.0)

            self._pilot_state[symbol_name] = {
                "full_qty": size.qty,
                "pilot_qty": pilot_qty,
                "pilot_price": pilot_price,
                "add_qty": size.qty - pilot_qty,
                "bars_waited": 0,
                "sector": sector,
                "sl_pct": sl_pct,
                "tgt_pct": tgt_pct,
            }

            # Open partial position
            position = OpenPosition(
                symbol=symbol_name,
                qty=pilot_qty,
                entry_price=pilot_price,
                sl_price=pilot_price * (1 - sl_pct / 100),
                target_price=pilot_price * (1 + tgt_pct / 100),
                risk_amount=size.risk_amount * 0.5,
                sector=sector,
                entry_mode="pilot_add",
                entry_time=datetime.now(timezone.utc),
                is_paper=not self.config.get("risk", {}).get("live_mode", False),
            )
            self.pm.add_position(position)
            logger.info(
                f"[PILOT_FILLED] {symbol_name} | pilot_qty={pilot_qty} @ {pilot_price:.2f}",
                extra={"reason_code": "ENTRY_FILLED_PILOT"},
            )

    async def execute_add_order(self, symbol: str) -> None:
        """Execute the 'add' leg of pilot_add on retest confirmation."""
        state = self._pilot_state.get(symbol)
        if not state:
            return

        add_qty = state["add_qty"]
        logger.info(f"[PILOT_ADD] Adding {add_qty} {symbol} on retest")
        pos = self.pm.open_positions.get(symbol)
        if not pos:
            return

        resp = await self.broker.place_order(
            symbol=symbol, side="BUY", qty=add_qty,
            order_type="MARKET", price=pos.entry_price,
        )
        if resp.get("status") == "FILLED":
            add_price = resp.get("filled_price", pos.entry_price)
            fees = resp.get("fees", 0.0)
            pilot_price = pos.entry_price
            pilot_qty = pos.qty

            # Weighted average entry
            avg_entry = (pilot_qty * pilot_price + add_qty * add_price) / (pilot_qty + add_qty)
            total_qty = pilot_qty + add_qty
            sl_pct = state["sl_pct"]
            tgt_pct = state["tgt_pct"]

            pos.entry_price = round(avg_entry, 2)
            pos.qty = total_qty
            pos.sl_price = round(avg_entry * (1 - sl_pct / 100), 2)
            pos.current_sl = pos.sl_price
            pos.target_price = round(avg_entry * (1 + tgt_pct / 100), 2)
            pos.entry_mode = "pilot_add_complete"

            del self._pilot_state[symbol]
            logger.info(
                f"[ADD_FILLED] {symbol} | total_qty={total_qty} | avg_entry={avg_entry:.2f}",
                extra={"reason_code": "ADD_ORDER_FILLED"},
            )

    async def _close_pilot_position(self, symbol: str) -> None:
        """Close pilot position if retest not confirmed within N bars."""
        pos = self.pm.open_positions.get(symbol)
        if not pos:
            del self._pilot_state[symbol]
            return

        logger.warning(
            f"[PILOT_TIMEOUT] Closing {symbol} pilot — retest not confirmed in "
            f"{self.pilot_wait_bars} bars",
            extra={"reason_code": "RETEST_TIMEOUT"},
        )
        await self.execute_exit(symbol, pos.entry_price, "RETEST_TIMEOUT")
        self._pilot_state.pop(symbol, None)

    async def on_retest_signal(self, symbol: str) -> None:
        """Called when re-entry signal fires — if pilot is active, execute add."""
        if symbol in self._pilot_state:
            await self.execute_add_order(symbol)

    async def tick_pilot_timers(self) -> None:
        """Increment bar counters for pilot positions; close if timeout exceeded."""
        expired = []
        for sym, state in self._pilot_state.items():
            state["bars_waited"] += 1
            if state["bars_waited"] >= self.pilot_wait_bars:
                expired.append(sym)
        for sym in expired:
            await self._close_pilot_position(sym)

    # ──────────────────────────────────────────────
    # PART G: EXIT LOGIC (5 types)
    # ──────────────────────────────────────────────

    async def check_exits(self, ltp_map: Dict[str, float]) -> None:
        """
        Check all open positions for exit conditions on each candle.
        Called with a symbol→LTP dict after every 15m candle is finalized.
        """
        to_exit: List[tuple] = []

        for symbol, pos in list(self.pm.open_positions.items()):
            ltp = ltp_map.get(symbol, pos.entry_price)
            pnl_pct = ((ltp - pos.entry_price) / pos.entry_price) * 100

            # TYPE 1: SL hit (hard stop — use current_sl which may be trailed/breakeven)
            if ltp <= pos.current_sl:
                to_exit.append((symbol, ltp, "SL_HIT"))
                continue

            # TYPE 2: Target hit
            if ltp >= pos.target_price:
                to_exit.append((symbol, ltp, "TP_HIT"))
                continue

            # TYPE 3: Time stop (Part L — 7200 minutes = 480 bars)
            hold_mins = (datetime.now(timezone.utc) - pos.entry_time).total_seconds() / 60
            if hold_mins >= self.max_hold_minutes:
                to_exit.append((symbol, ltp, "TIME_EXIT"))
                continue

            # TYPE 4: Breakeven at +2.5% (optional)
            if self.enable_breakeven and not pos.breakeven_activated:
                if pnl_pct >= self.breakeven_trigger_pct:
                    pos.current_sl = pos.entry_price
                    pos.breakeven_activated = True
                    logger.info(
                        f"{symbol}: breakeven SL set at {pos.entry_price:.2f} "
                        f"(+{pnl_pct:.1f}%)",
                        extra={"reason_code": "BREAKEVEN_SL_SET"},
                    )
                    await self.event_bus.publish("on_breakeven_set", {
                        "symbol": symbol,
                        "new_sl": pos.entry_price,
                        "pnl_pct_at_trigger": pnl_pct,
                        "reason_code": "BREAKEVEN_SL_SET",
                    })

            # TYPE 5: Trail stop at +4% (optional)
            if self.enable_trail and pnl_pct >= self.trail_trigger_pct:
                trail_sl = ltp * (1 - self.trail_distance_pct / 100)
                if trail_sl > pos.current_sl:
                    pos.current_sl = round(trail_sl, 2)
                    pos.trail_activated = True
                    logger.info(
                        f"{symbol}: trail stop updated to {pos.current_sl:.2f} "
                        f"(LTP={ltp:.2f}, +{pnl_pct:.1f}%)",
                        extra={"reason_code": "TRAIL_STOP_UPDATED"},
                    )
                    await self.event_bus.publish("on_trail_stop_updated", {
                        "symbol": symbol,
                        "new_sl": pos.current_sl,
                        "ltp": ltp,
                        "pnl_pct": pnl_pct,
                        "reason_code": "TRAIL_STOP_UPDATED",
                    })

        # Execute exits
        for symbol, exit_price, reason in to_exit:
            await self.execute_exit(symbol, exit_price, reason)

    async def execute_exit(self, symbol: str, exit_price: float, reason: str) -> None:
        """Place SELL market order and close the position."""
        pos = self.pm.open_positions.get(symbol)
        if not pos:
            return

        logger.info(f"Placing EXIT order: {symbol} | reason={reason} | price={exit_price:.2f}")
        resp = await self.broker.place_order(
            symbol=symbol,
            side="SELL",
            qty=pos.qty,
            order_type="MARKET",
            price=exit_price,
        )

        actual_exit = resp.get("filled_price", exit_price)
        fees = resp.get("fees", 0.0)
        pnl = (actual_exit - pos.entry_price) * pos.qty - fees
        pnl_pct = ((actual_exit - pos.entry_price) / pos.entry_price) * 100
        hold_mins = (datetime.now(timezone.utc) - pos.entry_time).total_seconds() / 60

        realized_pnl = self.pm.remove_position(symbol, actual_exit, reason)
        await self.pm.update_daily_pnl(pnl)

        logger.info(
            f"EXIT FILLED: {symbol} | exit={actual_exit:.2f} | entry={pos.entry_price:.2f} "
            f"| pnl=₹{pnl:,.2f} ({pnl_pct:+.2f}%) | reason={reason} "
            f"| hold={hold_mins:.0f}min",
            extra={"reason_code": f"EXIT_{reason}"},
        )

        await self.event_bus.publish("on_trade_exited", {
            "symbol": symbol,
            "sector": pos.sector,
            "entry_price": pos.entry_price,
            "exit_price": actual_exit,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "qty": pos.qty,
            "fees": fees,
            "exit_reason": reason,
            "hold_duration_mins": hold_mins,
            "entry_mode": pos.entry_mode,
            "reason_code": f"EXIT_{reason}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
