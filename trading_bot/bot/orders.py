"""
bot/orders.py
~~~~~~~~~~~~~
High-level order placement logic built on top of ``BinanceClient``.

``OrderManager`` translates validated user intent into correctly-formed Binance
API parameter dicts, submits them, and returns structured ``OrderResult``
dataclass instances.

Dry-run mode
------------
Pass ``dry_run=True`` to ``OrderManager`` to skip all HTTP calls.  A realistic
simulated Binance response is generated locally so the full CLI flow — validation,
request panel, response panel, logging — runs exactly as it would against the
real API.
"""

import logging
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from bot.client import BinanceAPIError, BinanceClient

logger = logging.getLogger("trading_bot.orders")


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class OrderResult:
    """Structured representation of a Binance order response.

    Attributes
    ----------
    order_id:
        Unique numeric order identifier assigned by Binance.
    symbol:
        Trading pair, e.g. ``"BTCUSDT"``.
    side:
        ``"BUY"`` or ``"SELL"``.
    type:
        Order type string as returned by the API (e.g. ``"MARKET"``,
        ``"LIMIT"``, ``"STOP"``).
    status:
        Current order status (e.g. ``"NEW"``, ``"FILLED"``).
    orig_qty:
        Original requested quantity.
    executed_qty:
        Quantity that has been filled so far.
    avg_price:
        Average fill price (``0.0`` for unfilled orders).
    dry_run:
        ``True`` when this result was produced locally without an API call.
    raw:
        The complete, unmodified response dict (real or simulated).
    """

    order_id: int
    symbol: str
    side: str
    type: str
    status: str
    orig_qty: float
    executed_qty: float
    avg_price: float
    dry_run: bool
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_response(cls, data: dict[str, Any], *, dry_run: bool = False) -> "OrderResult":
        """Construct an ``OrderResult`` from a raw Binance API response dict.

        Parameters
        ----------
        data:
            Raw JSON response from ``POST /fapi/v1/order`` (real or simulated).
        dry_run:
            Whether this result was produced without a real API call.

        Returns
        -------
        OrderResult
            Populated dataclass instance.
        """
        return cls(
            order_id=int(data.get("orderId", 0)),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            type=data.get("type", ""),
            status=data.get("status", ""),
            orig_qty=float(data.get("origQty", 0.0)),
            executed_qty=float(data.get("executedQty", 0.0)),
            avg_price=float(data.get("avgPrice", 0.0)),
            dry_run=dry_run,
            raw=data,
        )


# ── Simulated response builder ────────────────────────────────────────────────

# Approximate mid-prices used to generate plausible simulated fill prices.
_MOCK_PRICES: dict[str, float] = {
    "BTCUSDT":  95000.0,
    "ETHUSDT":   3200.0,
    "BNBUSDT":    600.0,
    "SOLUSDT":    175.0,
    "XRPUSDT":      0.62,
    "DOGEUSDT":     0.18,
    "ADAUSDT":      0.48,
    "AVAXUSDT":    38.0,
    "LINKUSDT":    18.0,
    "LTCUSDT":     90.0,
}
_DEFAULT_MOCK_PRICE = 100.0


def _mock_price(symbol: str) -> float:
    """Return a plausible mid-price for *symbol* with a tiny random spread.

    Parameters
    ----------
    symbol:
        Trading pair, e.g. ``"BTCUSDT"``.

    Returns
    -------
    float
        Simulated market price with ±0.05 % jitter.
    """
    base = _MOCK_PRICES.get(symbol.upper(), _DEFAULT_MOCK_PRICE)
    jitter = base * random.uniform(-0.0005, 0.0005)
    return round(base + jitter, 2)


def _build_dry_run_response(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: float | None = None,
    stop_price: float | None = None,
) -> dict[str, Any]:
    """Build a realistic simulated Binance order response dict.

    The structure mirrors the real ``POST /fapi/v1/order`` JSON response so
    ``OrderResult.from_response()`` can parse it without any changes.

    Parameters
    ----------
    symbol:
        Trading pair.
    side:
        ``"BUY"`` or ``"SELL"``.
    order_type:
        ``"MARKET"``, ``"LIMIT"``, or ``"STOP"``.
    quantity:
        Order size.
    price:
        Limit price (``None`` for MARKET orders).
    stop_price:
        Stop trigger price (``None`` unless STOP order).

    Returns
    -------
    dict
        Simulated response matching the Binance API schema.
    """
    order_id = random.randint(4_000_000_000, 9_999_999_999)
    update_time = int(time.time() * 1000)
    client_order_id = f"dryrun-{order_id}"

    sim_price = _mock_price(symbol)

    if order_type == "MARKET":
        status = "FILLED"
        avg_price = str(sim_price)
        executed_qty = str(quantity)
        cum_quote = str(round(quantity * sim_price, 6))
        api_price = "0"
    elif order_type == "LIMIT":
        status = "NEW"
        avg_price = "0.00"
        executed_qty = "0"
        cum_quote = "0"
        api_price = str(price)
    else:  # STOP
        status = "NEW"
        avg_price = "0.00"
        executed_qty = "0"
        cum_quote = "0"
        api_price = str(price)

    return {
        "orderId": order_id,
        "symbol": symbol.upper(),
        "status": status,
        "clientOrderId": client_order_id,
        "price": api_price,
        "avgPrice": avg_price,
        "origQty": str(quantity),
        "executedQty": executed_qty,
        "cumQty": executed_qty,
        "cumQuote": cum_quote,
        "timeInForce": "GTC",
        "type": order_type,
        "reduceOnly": False,
        "closePosition": False,
        "side": side.upper(),
        "positionSide": "BOTH",
        "stopPrice": str(stop_price) if stop_price else "0",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": False,
        "origType": order_type,
        "updateTime": update_time,
        "_dryRun": True,
    }


# ── Order manager ─────────────────────────────────────────────────────────────


class OrderManager:
    """Orchestrates order placement via a ``BinanceClient`` instance.

    Parameters
    ----------
    client:
        An authenticated ``BinanceClient`` ready to make API calls.
        Ignored when *dry_run* is ``True``.
    dry_run:
        When ``True``, skip all HTTP calls and return a locally-generated
        simulated order response.  No credentials are required.
    """

    def __init__(self, client: BinanceClient, *, dry_run: bool = False) -> None:
        self._client = client
        self._dry_run = dry_run

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        """Place a MARKET or LIMIT order on Binance Futures Testnet.

        In dry-run mode no HTTP request is made; a simulated response is
        returned instead.

        Parameters
        ----------
        symbol:
            Trading pair (e.g. ``"BTCUSDT"``).
        side:
            ``"BUY"`` or ``"SELL"``.
        order_type:
            ``"MARKET"`` or ``"LIMIT"``.
        quantity:
            Order size in base-asset units.
        price:
            Limit price.  Required for LIMIT orders; ignored for MARKET orders.

        Returns
        -------
        OrderResult
            Structured order response (real or simulated).

        Raises
        ------
        BinanceAPIError
            Propagated from the client on API or network failures (live mode only).
        ValueError
            If a LIMIT order is requested without a price.
        """
        if order_type.upper() == "LIMIT" and price is None:
            raise ValueError("price is required for LIMIT orders")

        logger.info(
            "%sPlacing %s %s order | symbol=%s | qty=%s | price=%s",
            "[DRY-RUN] " if self._dry_run else "",
            side.upper(),
            order_type.upper(),
            symbol.upper(),
            quantity,
            price if price is not None else "N/A (MARKET)",
        )

        if self._dry_run:
            response = _build_dry_run_response(
                symbol=symbol,
                side=side,
                order_type=order_type.upper(),
                quantity=quantity,
                price=price,
            )
            logger.debug("[DRY-RUN] Simulated response: %s", response)
        else:
            params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": quantity,
            }
            if order_type.upper() == "LIMIT":
                params["price"] = price
                params["timeInForce"] = "GTC"

            try:
                response = self._client.place_order(params)
            except BinanceAPIError:
                logger.debug(
                    "Order placement failed (traceback below)\n%s",
                    traceback.format_exc(),
                )
                raise

        result = OrderResult.from_response(response, dry_run=self._dry_run)
        logger.info(
            "%sOrder accepted | id=%s | status=%s | executed_qty=%s | avg_price=%s",
            "[DRY-RUN] " if self._dry_run else "",
            result.order_id,
            result.status,
            result.executed_qty,
            result.avg_price,
        )
        return result

    def place_stop_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        limit_price: float,
    ) -> OrderResult:
        """Place a STOP (stop-limit) order on Binance Futures Testnet.

        Binance Futures uses order type ``STOP`` for stop-limit orders.  The
        order triggers when the market reaches *stop_price* and then submits a
        limit order at *limit_price*.

        In dry-run mode no HTTP request is made; a simulated response is
        returned instead.

        Parameters
        ----------
        symbol:
            Trading pair (e.g. ``"BTCUSDT"``).
        side:
            ``"BUY"`` or ``"SELL"``.
        quantity:
            Order size in base-asset units.
        stop_price:
            Price at which the stop is triggered.
        limit_price:
            Limit price for the order once triggered.

        Returns
        -------
        OrderResult
            Structured order response (real or simulated).

        Raises
        ------
        BinanceAPIError
            Propagated from the client on API or network failures (live mode only).
        """
        logger.info(
            "%sPlacing %s STOP_LIMIT order | symbol=%s | qty=%s | stop=%s | limit=%s",
            "[DRY-RUN] " if self._dry_run else "",
            side.upper(),
            symbol.upper(),
            quantity,
            stop_price,
            limit_price,
        )

        if self._dry_run:
            response = _build_dry_run_response(
                symbol=symbol,
                side=side,
                order_type="STOP",
                quantity=quantity,
                price=limit_price,
                stop_price=stop_price,
            )
            logger.debug("[DRY-RUN] Simulated response: %s", response)
        else:
            params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": "STOP",
                "quantity": quantity,
                "stopPrice": stop_price,
                "price": limit_price,
                "timeInForce": "GTC",
            }
            try:
                response = self._client.place_order(params)
            except BinanceAPIError:
                logger.debug(
                    "Stop-limit order placement failed (traceback below)\n%s",
                    traceback.format_exc(),
                )
                raise

        result = OrderResult.from_response(response, dry_run=self._dry_run)
        logger.info(
            "%sStop-limit order accepted | id=%s | status=%s | stop=%s | limit=%s",
            "[DRY-RUN] " if self._dry_run else "",
            result.order_id,
            result.status,
            stop_price,
            limit_price,
        )
        return result
