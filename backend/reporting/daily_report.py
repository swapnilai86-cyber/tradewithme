"""
reporting/daily_report.py
End-of-day trading report generator (Part O).
Generates a comprehensive summary at 16:00 IST and posts to Discord + saves JSON.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from backend.logging_config import get_logger

logger = get_logger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


class DailyReporter:
    """
    Generates and dispatches the end-of-day trading summary report.
    Implements Part O of the trading engine specification.
    """

    def __init__(self, event_bus, portfolio_manager, reports_dir: str = "reports"):
        self.event_bus = event_bus
        self.pm = portfolio_manager
        self.reports_dir = reports_dir
        os.makedirs(reports_dir, exist_ok=True)

        # Intraday accumulators (reset each day)
        self.radar_signals: List[dict] = []
        self.entries_today: List[dict] = []
        self.exits_today: List[dict] = []
        self.rejected_entries: List[dict] = []
        self.errors_today: List[dict] = []

        # Subscribe to events to accumulate daily data
        self.event_bus.subscribe("on_early_radar_found",    self._record_radar)
        self.event_bus.subscribe("on_entry_triggered",      self._record_entry_signal)
        self.event_bus.subscribe("on_trade_executed",       self._record_entry)
        self.event_bus.subscribe("on_trade_exited",         self._record_exit)
        self.event_bus.subscribe("on_error",                self._record_error)

    # ──────────────────────────────────────────────
    # ACCUMULATORS
    # ──────────────────────────────────────────────

    async def _record_radar(self, data: dict) -> None:
        self.radar_signals.append(data)

    async def _record_entry_signal(self, data: dict) -> None:
        # Signals that resulted in entries will also have on_trade_executed
        pass

    async def _record_entry(self, data: dict) -> None:
        self.entries_today.append(data)

    async def _record_exit(self, data: dict) -> None:
        self.exits_today.append(data)

    async def _record_error(self, data: dict) -> None:
        self.errors_today.append(data)

    # ──────────────────────────────────────────────
    # REPORT GENERATION
    # ──────────────────────────────────────────────

    async def generate_report(self) -> dict:
        """
        Generate full daily report.
        Called at 16:00 IST by the scheduler in core.py.
        """
        ist_now = datetime.now(timezone.utc) + IST_OFFSET
        date_str = ist_now.strftime("%Y-%m-%d")

        logger.info(f"Generating daily report for {date_str}...")

        # Calculate stats
        wins = [e for e in self.exits_today if e.get("pnl", 0) > 0]
        losses = [e for e in self.exits_today if e.get("pnl", 0) <= 0]
        total_exits = len(self.exits_today)
        win_rate = (len(wins) / total_exits * 100) if total_exits > 0 else 0.0
        daily_pnl = sum(e.get("pnl", 0) for e in self.exits_today)
        best_trade = max(self.exits_today, key=lambda e: e.get("pnl", 0), default=None)
        worst_trade = min(self.exits_today, key=lambda e: e.get("pnl", 0), default=None)

        # Sector breakdown of exits
        sector_pnl: Dict[str, float] = {}
        for exit_rec in self.exits_today:
            sec = exit_rec.get("sector", "Unknown")
            sector_pnl[sec] = sector_pnl.get(sec, 0) + exit_rec.get("pnl", 0)

        # Open positions
        open_pos_list = [
            {
                "symbol": sym,
                "qty": pos.qty,
                "entry_price": pos.entry_price,
                "current_sl": pos.current_sl,
                "target": pos.target_price,
                "sector": pos.sector,
            }
            for sym, pos in self.pm.open_positions.items()
        ]

        # Radar → Entry conversion
        radar_symbols = {r.get("symbol") for r in self.radar_signals}
        entry_symbols = {e.get("symbol") for e in self.entries_today}
        converted_from_radar = radar_symbols & entry_symbols

        report = {
            "date": date_str,
            "generated_at": ist_now.isoformat(),
            "radar_candidates": {
                "count": len(self.radar_signals),
                "symbols": list(radar_symbols),
                "converted_to_entry": list(converted_from_radar),
                "not_converted": list(radar_symbols - converted_from_radar),
            },
            "entries": {
                "count": len(self.entries_today),
                "details": self.entries_today,
            },
            "exits": {
                "count": total_exits,
                "wins": len(wins),
                "losses": len(losses),
                "details": self.exits_today,
            },
            "open_positions": {
                "count": len(open_pos_list),
                "details": open_pos_list,
            },
            "statistics": {
                "daily_pnl": round(daily_pnl, 2),
                "daily_pnl_pct": round((daily_pnl / self.pm.total_equity) * 100, 2),
                "win_rate_pct": round(win_rate, 1),
                "wins": len(wins),
                "losses": len(losses),
                "radar_count": len(self.radar_signals),
                "entries_count": len(self.entries_today),
                "exits_count": total_exits,
                "open_positions": len(open_pos_list),
                "best_trade": (
                    f"{best_trade['symbol']} ₹{best_trade['pnl']:,.0f} (+{best_trade.get('pnl_pct',0):.1f}%)"
                    if best_trade else None
                ),
                "worst_trade": (
                    f"{worst_trade['symbol']} ₹{worst_trade['pnl']:,.0f} ({worst_trade.get('pnl_pct',0):.1f}%)"
                    if worst_trade else None
                ),
                "sector_pnl": {k: round(v, 2) for k, v in sorted(sector_pnl.items(), key=lambda x: -abs(x[1]))},
                "portfolio_snapshot": self.pm.get_snapshot(),
            },
            "alerts_and_errors": {
                "kill_switch_activated": self.pm.kill_switch_active,
                "error_count": len(self.errors_today),
                "errors": self.errors_today[:10],  # cap at 10
                "rejected_entries": self.rejected_entries[:20],
            },
        }

        # Save to file
        filepath = os.path.join(self.reports_dir, f"daily_report_{date_str}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Daily report saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save daily report: {e}")

        # Dispatch to Discord
        await self.event_bus.publish("on_daily_report", {
            "date": date_str,
            "stats": report["statistics"],
        })

        # Reset daily accumulators for next day
        self._reset()

        logger.info(
            f"Daily report dispatched | PnL=₹{daily_pnl:,.0f} | "
            f"Entries={len(self.entries_today)} | Exits={total_exits} | Win%={win_rate:.1f}",
            extra={"reason_code": "DAILY_REPORT_GENERATED"},
        )
        return report

    def _reset(self) -> None:
        """Reset all intraday accumulators for next trading day."""
        self.radar_signals.clear()
        self.entries_today.clear()
        self.exits_today.clear()
        self.rejected_entries.clear()
        self.errors_today.clear()
        self.pm.reset_daily_state()
