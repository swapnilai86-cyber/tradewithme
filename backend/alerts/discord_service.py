"""
alerts/discord_service.py
Rich Discord embed alerts for all trading events.
Implements Part O alert dispatching for all signal/exit/risk events.
"""
from __future__ import annotations

import aiohttp
import asyncio
import os
from datetime import datetime
from typing import Optional
from backend.logging_config import get_logger
from backend.database.database import AsyncSessionLocal
from backend.database.models import SystemAlert

logger = get_logger(__name__)

# Discord embed colours
COLOR_YELLOW = 0xFFD700   # Early Radar
COLOR_GREEN = 0x00C851    # Entry Trigger / TP Hit
COLOR_CYAN = 0x00BCD4     # Retest Re-entry
COLOR_RED = 0xFF4444      # SL Hit / Kill-switch
COLOR_ORANGE = 0xFF8800   # Time Exit / Breakeven
COLOR_PURPLE = 0x9C27B0   # Trail Stop
COLOR_GRAY = 0x9E9E9E     # Info / Daily Report
COLOR_BLUE = 0x2196F3     # Trade Executed


class DiscordService:
    """
    Subscribes to EventBus events and dispatches rich Discord embeds
    to configured webhook channels.
    """

    def __init__(self, event_bus, config: Optional[dict] = None):
        self.event_bus = event_bus
        self.webhooks = {
            "early_radar":    os.getenv("DISCORD_WEBHOOK_EARLY_RADAR", ""),
            "entry_trigger":  os.getenv("DISCORD_WEBHOOK_ENTRY_TRIGGER", ""),
            "exits":          os.getenv("DISCORD_WEBHOOK_EXITS", ""),
            "errors":         os.getenv("DISCORD_WEBHOOK_ERRORS", ""),
        }

        # Subscribe to all events
        self.event_bus.subscribe("on_early_radar_found",    self.handle_early_radar)
        self.event_bus.subscribe("on_entry_triggered",      self.handle_entry_trigger)
        self.event_bus.subscribe("on_retest_reentry",       self.handle_retest_reentry)
        self.event_bus.subscribe("on_trade_executed",       self.handle_trade_executed)
        self.event_bus.subscribe("on_trade_exited",         self.handle_trade_exited)
        self.event_bus.subscribe("on_kill_switch_activated",self.handle_kill_switch)
        self.event_bus.subscribe("on_breakeven_set",        self.handle_breakeven_set)
        self.event_bus.subscribe("on_trail_stop_updated",   self.handle_trail_stop_update)
        self.event_bus.subscribe("on_error",                self.handle_error)
        self.event_bus.subscribe("on_daily_report",         self.handle_daily_report)

    # ──────────────────────────────────────────────
    # WEBHOOK SENDER & DB WRITER
    # ──────────────────────────────────────────────

    async def _save_to_db(self, symbol: str, alert_type: str, message: str, price: float, data: dict) -> None:
        try:
            async with AsyncSessionLocal() as db:
                alert = SystemAlert(
                    symbol=symbol,
                    alert_type=alert_type,
                    price=price,
                    message=message,
                    data=data
                )
                db.add(alert)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save alert to DB: {e}")

    async def _send_webhook(self, url: str, payload: dict, retries: int = 3) -> None:
        """Send Discord webhook with retry and rate-limit handling."""
        if not url:
            logger.warning("Discord webhook URL not configured — skipping alert")
            return

        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 429:
                            retry_after = (await resp.json()).get("retry_after", 1)
                            logger.warning(f"Discord rate limited — retrying in {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue
                        if resp.status not in (200, 204):
                            text = await resp.text()
                            logger.error(f"Discord webhook error {resp.status}: {text}")
                        return
            except Exception as e:
                logger.error(f"Discord webhook attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2 ** attempt)

    def _footer(self, data: dict) -> dict:
        ts = data.get("timestamp", datetime.utcnow().isoformat())
        return {"text": f"⏱ {ts[:19].replace('T', ' ')} UTC  |  reason: {data.get('reason_code', '')}"}

    # ──────────────────────────────────────────────
    # EVENT HANDLERS
    # ──────────────────────────────────────────────

    async def handle_early_radar(self, data: dict) -> None:
        """🟡 Stage-A Early Radar alert."""
        symbol = data.get("symbol", "?")
        payload = {
            "embeds": [{
                "title": f"🟡 EARLY RADAR — {symbol}",
                "description": (
                    f"**{data.get('sector', 'Unknown')}** | Tight consolidation near resistance"
                ),
                "color": COLOR_YELLOW,
                "fields": [
                    {"name": "💰 Current Price",  "value": f"₹{data.get('price', 0):.2f}",          "inline": True},
                    {"name": "📊 Momentum (RSI)", "value": f"{data.get('rsi', 0):.1f}",             "inline": True},
                    {"name": "📦 Volume Surge",   "value": f"{data.get('vol_ratio', 0):.2f}x",       "inline": True},
                    {"name": "📐 Price Squeeze",  "value": f"{data.get('compression_pct', 0):.2f}%", "inline": True},
                    {"name": "📏 Dist to Breakout","value": f"{data.get('dist_to_high_pct', 0):.2f}%","inline": True},
                    {"name": "📈 Trend (MACD)",   "value": f"{data.get('macd_hist', 0):.4f}",        "inline": True},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["early_radar"], payload)
        await self._save_to_db(symbol, "EARLY_RADAR", payload["embeds"][0]["description"], data.get('price', 0), data)

    async def handle_entry_trigger(self, data: dict) -> None:
        """🟢 Stage-B Entry Trigger alert."""
        symbol = data.get("symbol", "?")
        entry = data.get("entry_price", 0)
        sl = data.get("sl", 0)
        tp = data.get("target", 0)
        payload = {
            "embeds": [{
                "title": f"🟢 ENTRY TRIGGER — {symbol}",
                "description": (
                    f"**{data.get('sector', 'Unknown')}** | Breakout confirmed with volume surge"
                ),
                "color": COLOR_GREEN,
                "fields": [
                    {"name": "💰 Entry Price",    "value": f"₹{entry:.2f}",                         "inline": True},
                    {"name": "🛑 Stop Loss",      "value": f"₹{sl:.2f}",                            "inline": True},
                    {"name": "🎯 Target",         "value": f"₹{tp:.2f}",                            "inline": True},
                    {"name": "📊 Momentum (RSI)", "value": f"{data.get('rsi', 0):.1f}",             "inline": True},
                    {"name": "📦 Volume Surge",   "value": f"{data.get('vol_ratio', 0):.2f}x",       "inline": True},
                    {"name": "📏 Breakout Str.",  "value": f"{data.get('dist_from_breakout_pct', 0):.2f}%", "inline": True},
                    {"name": "🔑 Res. Broken",    "value": f"₹{data.get('breakout_level', 0):.2f}", "inline": False},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["entry_trigger"], payload)
        await self._save_to_db(symbol, "ENTRY_TRIGGER", payload["embeds"][0]["description"], entry, data)

    async def handle_retest_reentry(self, data: dict) -> None:
        """🔵 Retest Re-entry alert (cyan)."""
        symbol = data.get("symbol", "?")
        payload = {
            "embeds": [{
                "title": f"🔵 RETEST RE-ENTRY — {symbol}",
                "description": (
                    f"**{data.get('sector', 'Unknown')}** | Breakout level held on retest"
                ),
                "color": COLOR_CYAN,
                "fields": [
                    {"name": "💰 Entry Price",   "value": f"₹{data.get('entry_price', 0):.2f}", "inline": True},
                    {"name": "🛑 Stop Loss",     "value": f"₹{data.get('sl', 0):.2f}",          "inline": True},
                    {"name": "🎯 Target",        "value": f"₹{data.get('target', 0):.2f}",      "inline": True},
                    {"name": "📊 Momentum (RSI)", "value": f"{data.get('rsi', 0):.1f}",          "inline": True},
                    {"name": "📦 Volume Surge",  "value": f"{data.get('vol_ratio', 0):.2f}x",    "inline": True},
                    {"name": "🔑 Res. Retested", "value": f"₹{data.get('breakout_level', 0):.2f}","inline": True},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["entry_trigger"], payload)
        await self._save_to_db(symbol, "RETEST_REENTRY", payload["embeds"][0]["description"], data.get('entry_price', 0), data)

    async def handle_trade_executed(self, data: dict) -> None:
        """🔵 Entry order filled confirmation."""
        symbol = data.get("symbol", "?")
        signal_p = data.get("signal_price", data.get("entry_price", 0))
        filled_p = data.get("entry_price", 0)
        slippage = abs(filled_p - signal_p)
        payload = {
            "embeds": [{
                "title": f"✅ ORDER FILLED — {symbol} [{data.get('entry_mode', 'single_shot').upper()}]",
                "description": f"**{data.get('sector', 'Unknown')}** | Position opened",
                "color": COLOR_BLUE,
                "fields": [
                    {"name": "📍 Filled @ ",     "value": f"₹{filled_p:.2f}",                     "inline": True},
                    {"name": "📡 Signal @ ",     "value": f"₹{signal_p:.2f}",                     "inline": True},
                    {"name": "📉 Slippage",      "value": f"₹{slippage:.2f}",                     "inline": True},
                    {"name": "🔢 Qty",           "value": str(data.get("qty", 0)),                 "inline": True},
                    {"name": "🛑 SL",            "value": f"₹{data.get('sl', 0):.2f}",            "inline": True},
                    {"name": "🎯 Target",        "value": f"₹{data.get('target', 0):.2f}",        "inline": True},
                    {"name": "⚖️ Cap. at Risk", "value": f"₹{data.get('risk_amount', 0):,.0f}",  "inline": True},
                    {"name": "🏆 Est. Reward",   "value": f"₹{data.get('reward_amount', 0):,.0f}","inline": True},
                    {"name": "📊 R:R Ratio",     "value": f"1:{data.get('rr_ratio', 0):.2f}",     "inline": True},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["entry_trigger"], payload)
        await self._save_to_db(symbol, "TRADE_EXECUTED", payload["embeds"][0]["description"], filled_p, data)

    async def handle_trade_exited(self, data: dict) -> None:
        """Exit alert — colour by reason."""
        symbol = data.get("symbol", "?")
        pnl = data.get("pnl", 0)
        pnl_pct = data.get("pnl_pct", 0)
        reason = data.get("exit_reason", "UNKNOWN")

        color_map = {
            "TP_HIT": COLOR_GREEN,
            "SL_HIT": COLOR_RED,
            "TIME_EXIT": COLOR_ORANGE,
            "RETEST_TIMEOUT": COLOR_GRAY,
        }
        color = color_map.get(reason, COLOR_GRAY)
        icon_map = {"TP_HIT": "🟢", "SL_HIT": "🔴", "TIME_EXIT": "⏰", "RETEST_TIMEOUT": "⚪"}
        icon = icon_map.get(reason, "⚪")
        pnl_str = f"{'▲' if pnl >= 0 else '▼'} ₹{abs(pnl):,.2f} ({pnl_pct:+.2f}%)"

        payload = {
            "embeds": [{
                "title": f"{icon} EXIT — {symbol} | {reason}",
                "description": f"**{data.get('sector', 'Unknown')}** | Trade closed",
                "color": color,
                "fields": [
                    {"name": "📍 Exit Price",  "value": f"₹{data.get('exit_price', 0):.2f}",   "inline": True},
                    {"name": "📡 Entry Price", "value": f"₹{data.get('entry_price', 0):.2f}",   "inline": True},
                    {"name": "💸 Profit / Loss","value": pnl_str,                                "inline": True},
                    {"name": "🔢 Qty",         "value": str(data.get("qty", 0)),                "inline": True},
                    {"name": "💰 Fees",        "value": f"₹{data.get('fees', 0):.2f}",         "inline": True},
                    {"name": "⏱ Time Held",   "value": f"{data.get('hold_duration_mins', 0):.0f} min","inline": True},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["exits"], payload)
        await self._save_to_db(symbol, reason, payload["embeds"][0]["description"], data.get('exit_price', 0), data)

    async def handle_kill_switch(self, data: dict) -> None:
        """🛑 CRITICAL: Kill switch activated."""
        pnl = data.get("daily_pnl", 0)
        pnl_pct = data.get("daily_pnl_pct", 0)
        payload = {
            "embeds": [{
                "title": "🛑 KILL SWITCH ACTIVATED",
                "description": "**Daily loss limit exceeded — new entries DISABLED**",
                "color": COLOR_RED,
                "fields": [
                    {"name": "📉 Daily PnL",  "value": f"₹{pnl:,.0f} ({pnl_pct:.2f}%)", "inline": False},
                    {"name": "⚠️ Action",     "value": data.get("action", "Manual override required"), "inline": False},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["errors"], payload)

    async def handle_breakeven_set(self, data: dict) -> None:
        """🟠 Breakeven SL set."""
        symbol = data.get("symbol", "?")
        payload = {
            "embeds": [{
                "title": f"🟠 BREAKEVEN SL — {symbol}",
                "color": COLOR_ORANGE,
                "fields": [
                    {"name": "📍 New SL",   "value": f"₹{data.get('new_sl', 0):.2f}",           "inline": True},
                    {"name": "📈 PnL @",    "value": f"+{data.get('pnl_pct_at_trigger', 0):.1f}%","inline": True},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["exits"], payload)

    async def handle_trail_stop_update(self, data: dict) -> None:
        """🟣 Trail stop updated."""
        symbol = data.get("symbol", "?")
        payload = {
            "embeds": [{
                "title": f"🟣 TRAIL STOP — {symbol}",
                "color": COLOR_PURPLE,
                "fields": [
                    {"name": "📍 New SL",  "value": f"₹{data.get('new_sl', 0):.2f}",  "inline": True},
                    {"name": "💰 LTP",     "value": f"₹{data.get('ltp', 0):.2f}",      "inline": True},
                    {"name": "📈 PnL",     "value": f"+{data.get('pnl_pct', 0):.1f}%", "inline": True},
                ],
                "footer": self._footer(data),
            }]
        }
        await self._send_webhook(self.webhooks["exits"], payload)

    async def handle_error(self, data: dict) -> None:
        """❌ System error alert."""
        payload = {
            "embeds": [{
                "title": f"❌ ERROR — {data.get('type', 'General')}",
                "color": COLOR_RED,
                "description": data.get("message", "Unknown error"),
                "footer": {"text": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")},
            }]
        }
        await self._send_webhook(self.webhooks["errors"], payload)

    async def handle_daily_report(self, data: dict) -> None:
        """📊 Daily EOD report embed."""
        stats = data.get("stats", {})
        pnl = stats.get("daily_pnl", 0)
        pnl_sign = "▲" if pnl >= 0 else "▼"
        color = COLOR_GREEN if pnl >= 0 else COLOR_RED

        fields = [
            {"name": "📡 Radar Signals",    "value": str(stats.get("radar_count", 0)),        "inline": True},
            {"name": "🟢 Entries Today",    "value": str(stats.get("entries_count", 0)),      "inline": True},
            {"name": "🔴 Exits Today",      "value": str(stats.get("exits_count", 0)),        "inline": True},
            {"name": "🏆 Wins",             "value": str(stats.get("wins", 0)),                "inline": True},
            {"name": "❌ Losses",           "value": str(stats.get("losses", 0)),              "inline": True},
            {"name": "📊 Win Rate",         "value": f"{stats.get('win_rate_pct', 0):.1f}%",  "inline": True},
            {"name": "💸 Daily PnL",        "value": f"{pnl_sign} ₹{abs(pnl):,.0f}",          "inline": True},
            {"name": "📂 Open Positions",   "value": str(stats.get("open_positions", 0)),     "inline": True},
            {"name": "💰 Unrealized PnL",   "value": f"₹{stats.get('unrealized_pnl', 0):,.0f}","inline": True},
        ]

        # Top winner / loser
        if stats.get("best_trade"):
            fields.append({"name": "🥇 Best Trade",  "value": stats["best_trade"],  "inline": True})
        if stats.get("worst_trade"):
            fields.append({"name": "🥴 Worst Trade", "value": stats["worst_trade"], "inline": True})

        payload = {
            "embeds": [{
                "title": f"📊 DAILY REPORT — {data.get('date', '')}",
                "description": "End-of-day trading summary",
                "color": color,
                "fields": fields,
                "footer": {"text": "Generated at 16:00 IST"},
            }]
        }
        await self._send_webhook(self.webhooks["errors"], payload)  # using errors channel as catch-all
