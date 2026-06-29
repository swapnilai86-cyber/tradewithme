"""
engine/core.py
Central TradingEngineCore orchestrator.
Wires all components: broker, scanner, risk, execution, alerts, reporting.
Routes to PaperBroker or LiveBroker based on config.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta, time as dt_time
from typing import Optional

from backend.logging_config import get_logger
from backend.events.event_bus import EventBus
from backend.engine.signals.scanner import SignalScanner
from backend.engine.risk.portfolio_manager import PortfolioManager
from backend.engine.execution.order_engine import OrderEngine
from backend.engine.brokers.mstock.adapter import MStockAdapter
from backend.engine.brokers.mstock.instruments import NiftyInstruments
from backend.engine.data_ingestion.polling_scanner import PollingScanner
from backend.alerts.discord_service import DiscordService
from backend.reporting.daily_report import DailyReporter
from backend.engine.execution.db_recorder import DBTradeRecorder

logger = get_logger(__name__)

# IST offset and market hours
IST_OFFSET = timedelta(hours=5, minutes=30)
REPORT_TIME_IST = dt_time(16, 0)   # 16:00 IST = 10:30 UTC


class TradingEngineCore:
    """
    Central orchestrator for the Nifty 500 swing trading engine.
    Components:
      - MStockAdapter / PaperBroker (based on live_mode config)
      - NiftyInstruments (token + sector map)
      - SignalScanner (Stage-A/B/C evaluation)
      - PortfolioManager (sizing, risk, kill-switch)
      - OrderEngine (entry/exit execution)
      - PollingScanner (2-min scheduled scan loop)
      - DiscordService (rich embeds for all events)
      - DailyReporter (16:00 IST EOD report)
    """

    def __init__(self, config: dict):
        self.config = config
        self.is_running: bool = False
        self._main_task: Optional[asyncio.Task] = None
        self._report_task: Optional[asyncio.Task] = None

        # Core infrastructure
        self.event_bus = EventBus()

        # Broker — always start with MStockAdapter (holds auth state)
        self.broker = MStockAdapter()

        # Choose execution broker based on live_mode
        live_mode = config.get("risk", {}).get("live_mode", False)
        if live_mode:
            self.execution_broker = self.broker
            logger.warning("⚡ LIVE MODE ENABLED — real orders will be placed!", extra={"reason_code": "LIVE_MODE"})
        else:
            from backend.engine.brokers.paper_broker import PaperBroker
            self.execution_broker = PaperBroker(config)
            logger.info("📄 PAPER MODE — simulated trading active", extra={"reason_code": "PAPER_MODE"})

        # Portfolio manager (sizing + risk guards)
        self.portfolio_manager = PortfolioManager(config)
        self.portfolio_manager.event_bus = self.event_bus  # wire kill-switch alerts

        # Signal scanner
        self.signal_scanner = SignalScanner(self.event_bus, config)

        # Order engine (entry/exit)
        self.order_engine = OrderEngine(
            broker=self.execution_broker,
            portfolio_manager=self.portfolio_manager,
            event_bus=self.event_bus,
            config=config,
        )

        # Instrument registry (Nifty 500 tokens + sectors)
        self.instruments = NiftyInstruments()

        # Polling scanner (2-min loop)
        self.polling_scanner = PollingScanner(
            mconnect_obj=None,  # set after broker auth
            signal_scanner=self.signal_scanner,
            instruments=self.instruments,
            order_engine=self.order_engine,
            config=config,
        )

        # Wire scanner entry signals to order engine
        self.event_bus.subscribe("on_entry_triggered", self.order_engine.execute_entry)
        self.event_bus.subscribe("on_retest_reentry",  self.order_engine.execute_entry)

        # Discord alerts
        self.discord_service = DiscordService(self.event_bus, config)

        # Database trade recorder
        self.db_recorder = DBTradeRecorder(self.event_bus)

        # Daily reporter
        self.daily_reporter = DailyReporter(
            event_bus=self.event_bus,
            portfolio_manager=self.portfolio_manager,
            reports_dir=config.get("reporting", {}).get("reports_dir", "reports"),
        )

    # ──────────────────────────────────────────────
    # LIFECYCLE
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the engine in disconnected state, or auto-connect if session is cached."""
        if self.is_running:
            return
        self.is_running = True
        logger.info("Trading Engine Core started. Checking for cached session...", extra={"reason_code": "ENGINE_STARTED"})

        # Try to restore session
        if await self.broker.auto_login():
            logger.info("Auto-login successful! Starting instruments sync...", extra={"reason_code": "AUTO_LOGIN_TRIGGER"})
            mconnect = self.broker.auth.mconnect_obj
            await self.instruments.sync(mconnect)
            
            # Start polling scanner
            self.polling_scanner.mconnect = mconnect
            await self.polling_scanner.start()
            self._report_task = asyncio.create_task(self._daily_report_loop())
        else:
            from datetime import datetime, timezone, timedelta, time as dt_time
            ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
            ist_time = ist_now.time()
            if not (dt_time(9, 15) <= ist_time <= dt_time(15, 30)):
                logger.info("Market is closed and session invalid. Entering OFFLINE MODE (using local CSVs).")
                self.polling_scanner.offline_mode = True
                await self.instruments.sync(None)
                await self.polling_scanner.start()
                self._report_task = asyncio.create_task(self._daily_report_loop())
            else:
                logger.info(
                    "No valid cached session found. Waiting for broker connection (TOTP)...",
                    extra={"reason_code": "ENGINE_WAITING_AUTH"},
                )

    async def connect_broker(self, totp_code: str) -> bool:
        """
        Authenticate with m.Stock using the provided TOTP.
        Triggers instrument sync and polling scanner startup on success.
        Called from the Admin Panel UI via POST /api/admin/totp.
        """
        logger.info("Initializing broker connection with provided TOTP...")
        try:
            success = await self.broker.login(totp_code)
            if not success:
                return False

            logger.info("Broker authenticated ✓")

            # Sync Nifty 500 instrument tokens
            mconnect = self.broker.auth.mconnect_obj
            await self.instruments.sync(mconnect)

            # Give polling scanner access to authenticated mconnect
            self.polling_scanner.mconnect = mconnect
            self.polling_scanner.offline_mode = False

            # Start scanning loop
            await self.polling_scanner.start()

            # Start daily report scheduler
            self._report_task = asyncio.create_task(self._daily_report_loop())

            logger.info(
                "Trading engine fully operational — scanning Nifty 500 every "
                f"{self.config.get('strategy', {}).get('scan_interval_seconds', 120)}s",
                extra={"reason_code": "ENGINE_FULLY_OPERATIONAL"},
            )
            return True

        except Exception as e:
            logger.error(f"Failed to authenticate broker: {e}", exc_info=True)
            return False

    async def stop(self) -> None:
        """Gracefully stop all engine components."""
        logger.info("Stopping Trading Engine Core...")
        self.is_running = False

        await self.polling_scanner.stop()

        if self._report_task:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass

        logger.info("Trading Engine stopped.", extra={"reason_code": "ENGINE_STOPPED"})

    # ──────────────────────────────────────────────
    # DAILY REPORT SCHEDULER
    # ──────────────────────────────────────────────

    async def _daily_report_loop(self) -> None:
        """
        Loop that wakes up at 16:00 IST daily and triggers the EOD report.
        Uses asyncio.sleep to avoid blocking.
        """
        while self.is_running:
            try:
                seconds_until_report = self._seconds_until_report_time()
                logger.debug(f"Daily report scheduler sleeping {seconds_until_report:.0f}s")
                await asyncio.sleep(seconds_until_report)

                if not self.is_running:
                    break

                logger.info("Triggering daily report at 16:00 IST")
                await self.daily_reporter.generate_report()

                # Sleep 60s to avoid double-firing on the same minute
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Daily report scheduler error: {e}", exc_info=True)
                await asyncio.sleep(300)  # retry in 5 min on error

    @staticmethod
    def _seconds_until_report_time() -> float:
        """Calculate seconds until 16:00 IST."""
        now_utc = datetime.now(timezone.utc)
        ist_now = now_utc + IST_OFFSET
        report_today_ist = ist_now.replace(hour=16, minute=0, second=0, microsecond=0)

        if ist_now >= report_today_ist:
            # Already past 16:00 today — schedule for tomorrow
            from datetime import timedelta as td
            report_today_ist += td(days=1)

        delta = report_today_ist - ist_now
        return max(delta.total_seconds(), 1)

    # ──────────────────────────────────────────────
    # ADMIN HELPERS
    # ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return current engine status for the Admin Panel API."""
        return {
            "is_running": self.is_running,
            "broker_connected": self.broker.auth.is_authenticated,
            "polling_active": self.polling_scanner._running,
            "live_mode": self.config.get("risk", {}).get("live_mode", False),
            "portfolio": self.portfolio_manager.get_snapshot(),
            "nifty500_synced": len(self.instruments.nifty500_symbols),
            "token_map_size": len(self.instruments.token_map),
        }
