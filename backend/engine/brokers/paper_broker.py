"""
backend/engine/brokers/paper_broker.py
----------------------------------------
PaperBroker: Simulated paper trading broker implementing the BrokerInterface.

Applies realistic random slippage and brokerage fees so that back-test /
paper-trade P&L figures closely mirror what a live trader would experience.
Implements Part H of the trading engine specification.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.engine.brokers.base import BrokerInterface
from backend.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Order model
# ---------------------------------------------------------------------------


class PaperOrder:
    """
    Lightweight representation of a single paper-trade order.

    Attributes
    ----------
    order_id : str
        Short UUID-based identifier (8 chars, upper-case).
    symbol : str
        NSE trading symbol.
    side : str
        ``"BUY"`` or ``"SELL"``.
    qty : int
        Requested quantity.
    order_type : str
        ``"MARKET"`` or ``"LIMIT"``.
    price : float
        Requested price (0.0 for pure market orders).
    status : str
        Lifecycle state: ``NEW`` → ``PLACED`` → ``FILLED`` | ``CANCELLED`` | ``REJECTED``.
    filled_qty : int
        Quantity actually filled.
    filled_price : float
        Average fill price after slippage.
    fees : float
        Brokerage fees charged.
    created_at : datetime
        UTC timestamp when the order was created.
    filled_at : Optional[datetime]
        UTC timestamp when the order was filled, or ``None`` if not yet filled.
    """

    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        price: float,
    ) -> None:
        self.order_id: str = order_id
        self.symbol: str = symbol
        self.side: str = side
        self.qty: int = qty
        self.order_type: str = order_type
        self.price: float = price
        self.status: str = "NEW"  # NEW → PLACED → FILLED | CANCELLED | REJECTED
        self.filled_qty: int = 0
        self.filled_price: float = 0.0
        self.fees: float = 0.0
        self.created_at: datetime = datetime.utcnow()
        self.filled_at: Optional[datetime] = None

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"PaperOrder(id={self.order_id}, {self.side} {self.qty} {self.symbol} "
            f"@ {self.filled_price:.2f}, status={self.status})"
        )


# ---------------------------------------------------------------------------
# Paper broker
# ---------------------------------------------------------------------------


class PaperBroker(BrokerInterface):
    """
    Simulated paper trading broker.

    Implements realistic slippage and brokerage fees so P&L figures reflect
    real-world trading friction.  All methods are ``async`` to be drop-in
    compatible with the live ``MStockBroker``.

    Configuration keys (read from ``config['paper_trading']``)
    ----------------------------------------------------------
    entry_slippage_max_pct : float
        Maximum slippage % on BUY orders (default: 0.5 %).
    exit_slippage_max_pct : float
        Maximum slippage % on SELL orders (default: 0.3 %).
    brokerage_pct : float
        Brokerage fee as a percentage of trade value (default: 0.03 %).
    initial_capital : float
        Starting cash balance in INR (default: 100 000).

    Part H of the trading engine specification.
    """

    def __init__(self, config: dict) -> None:
        paper_cfg: dict = config.get("paper_trading", {})

        self.entry_slippage_max_pct: float = paper_cfg.get(
            "entry_slippage_max_pct", 0.5
        )
        self.exit_slippage_max_pct: float = paper_cfg.get(
            "exit_slippage_max_pct", 0.3
        )
        self.brokerage_pct: float = paper_cfg.get("brokerage_pct", 0.03)
        self.cash: float = paper_cfg.get("initial_capital", 100_000.0)

        self.orders: Dict[str, PaperOrder] = {}
        self.is_authenticated: bool = True  # Paper broker is always ready

    # ------------------------------------------------------------------
    # BrokerInterface implementation
    # ------------------------------------------------------------------

    async def login(self, totp_code: str = "") -> bool:
        """
        Paper broker requires no authentication.

        Always returns ``True`` immediately.

        Parameters
        ----------
        totp_code : str
            Ignored – kept for interface compatibility.
        """
        logger.info("PaperBroker: No authentication needed (paper mode)")
        return True

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "MARKET",
        price: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Simulate order placement with realistic slippage and fee deduction.

        State transitions: ``NEW`` → ``PLACED`` → ``FILLED``

        Slippage model
        --------------
        * **BUY**: filled price is *above* the provided market price by a
          uniformly random fraction in ``[0, entry_slippage_max_pct]`` %.
        * **SELL**: filled price shifts by a uniformly random fraction in
          ``[0, exit_slippage_max_pct]`` % in either direction.

        Cash is updated immediately on fill:
        * BUY  → ``cash -= (trade_value + fees)``
        * SELL → ``cash += (trade_value - fees)``

        Parameters
        ----------
        symbol : str
            NSE trading symbol.
        side : str
            ``"BUY"`` or ``"SELL"``.
        qty : int
            Number of shares to trade.
        order_type : str
            ``"MARKET"`` (default) or ``"LIMIT"``.
        price : float
            Reference price used to compute slippage.  For MARKET orders pass
            the last traded price.  Pass ``0.0`` only in tests.

        Returns
        -------
        dict
            Keys: ``order_id``, ``status``, ``filled_qty``, ``filled_price``,
            ``fees``, ``symbol``, ``side``, ``is_paper``.
        """
        order_id = str(uuid.uuid4())[:8].upper()
        order = PaperOrder(order_id, symbol, side, qty, order_type, price)
        order.status = "PLACED"
        self.orders[order_id] = order

        # Determine market reference price
        market_price: float = price if price > 0 else 100.0  # fallback for tests

        # Apply slippage
        filled_price: float = round(self._apply_slippage(market_price, side), 2)

        # Calculate fees
        fees: float = self._calculate_fees(qty, filled_price)

        # Record fill
        order.filled_qty = qty
        order.filled_price = filled_price
        order.fees = fees
        order.status = "FILLED"
        order.filled_at = datetime.utcnow()

        # Update cash balance
        trade_value: float = qty * filled_price
        if side.upper() == "BUY":
            self.cash -= trade_value + fees
        else:
            self.cash += trade_value - fees

        logger.info(
            f"[PAPER] {side} {qty} {symbol} @ {filled_price:.2f} "
            f"(ref {price:.2f}), fees={fees:.2f}, cash={self.cash:.2f}",
            extra={"order_id": order_id, "reason": "PAPER_ORDER_FILLED"},
        )

        return {
            "order_id": order_id,
            "status": "FILLED",
            "filled_qty": qty,
            "filled_price": filled_price,
            "fees": fees,
            "symbol": symbol,
            "side": side,
            "is_paper": True,
        }

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending paper order.

        Only orders in ``NEW`` or ``PLACED`` state can be cancelled.

        Parameters
        ----------
        order_id : str
            The ``order_id`` returned by :meth:`place_order`.

        Returns
        -------
        bool
            ``True`` if the cancellation succeeded, ``False`` otherwise.
        """
        order = self.orders.get(order_id)
        if order and order.status in ("NEW", "PLACED"):
            order.status = "CANCELLED"
            logger.info(f"[PAPER] Order {order_id} cancelled")
            return True
        return False

    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Return an empty list.

        Positions are tracked by the ``PortfolioManager``, not the broker
        layer, so the paper broker does not maintain its own position book.
        """
        return []

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Return the current state of a paper order.

        Parameters
        ----------
        order_id : str
            The ``order_id`` returned by :meth:`place_order`.

        Returns
        -------
        dict
            Order details dict, or ``{"status": "NOT_FOUND"}`` when the
            order ID is unknown.
        """
        order = self.orders.get(order_id)
        if not order:
            return {"status": "NOT_FOUND"}

        return {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "filled_qty": order.filled_qty,
            "filled_price": order.filled_price,
            "status": order.status,
            "fees": order.fees,
        }

    async def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Not applicable for the paper broker.

        Returns an empty list for interface compatibility.
        """
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_slippage(self, price: float, side: str) -> float:
        """
        Apply realistic random slippage to *price*.

        BUY orders always receive a worse (higher) fill price.
        SELL orders can slip in either direction (market micro-structure noise).

        Parameters
        ----------
        price : float
            Reference market price.
        side : str
            ``"BUY"`` or ``"SELL"``.

        Returns
        -------
        float
            Adjusted fill price.
        """
        if side.upper() == "BUY":
            slippage_pct = random.uniform(0, self.entry_slippage_max_pct) / 100.0
            return price * (1.0 + slippage_pct)
        else:
            slippage_pct = random.uniform(0, self.exit_slippage_max_pct) / 100.0
            direction = random.choice([1, -1])  # exit can slip either way
            return price * (1.0 + direction * slippage_pct)

    def _calculate_fees(self, qty: int, filled_price: float) -> float:
        """
        Calculate brokerage fees for one side of a trade.

        Formula: ``qty × filled_price × (brokerage_pct / 100)``

        Default brokerage is 0.03 % per side (comparable to discount brokers).

        Parameters
        ----------
        qty : int
            Number of shares traded.
        filled_price : float
            Actual fill price (after slippage).

        Returns
        -------
        float
            Fee amount in INR, rounded to 2 decimal places.
        """
        brokerage = qty * filled_price * (self.brokerage_pct / 100.0)
        return round(brokerage, 2)
