"""
bot/validators.py
~~~~~~~~~~~~~~~~~
Pydantic v2 input validation models for order parameters.

Import ``OrderInput`` and call ``OrderInput(**user_data)`` to validate CLI
arguments before they reach the order-placement logic.
"""

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class OrderInput(BaseModel):
    """Validated order input parameters.

    Attributes
    ----------
    symbol:
        Trading pair, e.g. ``"BTCUSDT"``.  Must end with ``USDT`` or ``BUSD``.
    side:
        Order direction — ``"BUY"`` or ``"SELL"``.
    order_type:
        Order kind — ``"MARKET"``, ``"LIMIT"``, or ``"STOP_LIMIT"``.
    quantity:
        Order size in base-asset units.  Must be strictly positive.
    price:
        Limit price.  Required (and must be > 0) when *order_type* is
        ``"LIMIT"`` or ``"STOP_LIMIT"``.
    stop_price:
        Trigger price for stop orders.  Required (and must be > 0) when
        *order_type* is ``"STOP_LIMIT"``.
    """

    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "STOP_LIMIT"]
    quantity: float
    price: float | None = None
    stop_price: float | None = None

    # ── Field-level validators ────────────────────────────────────────────────

    @field_validator("symbol", mode="before")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        """Strip whitespace, uppercase, and enforce USDT/BUSD suffix.

        Parameters
        ----------
        value:
            Raw symbol string from the user.

        Returns
        -------
        str
            Normalised uppercase symbol.

        Raises
        ------
        ValueError
            If the symbol is empty or does not end with ``USDT`` or ``BUSD``.
        """
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol must not be empty")
        if not (value.endswith("USDT") or value.endswith("BUSD")):
            raise ValueError(
                f"symbol '{value}' must end with 'USDT' or 'BUSD' "
                "(e.g. BTCUSDT, ETHUSDT)"
            )
        return value

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: float) -> float:
        """Ensure quantity is strictly positive.

        Parameters
        ----------
        value:
            Raw quantity value.

        Returns
        -------
        float
            Validated quantity.

        Raises
        ------
        ValueError
            If quantity is zero or negative.
        """
        if value <= 0:
            raise ValueError(f"quantity must be > 0, got {value}")
        return value

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, value: float | None) -> float | None:
        """Ensure price, when provided, is strictly positive.

        Parameters
        ----------
        value:
            Raw price value or ``None``.

        Returns
        -------
        float | None
            Validated price or ``None``.

        Raises
        ------
        ValueError
            If price is provided but is zero or negative.
        """
        if value is not None and value <= 0:
            raise ValueError(f"price must be > 0, got {value}")
        return value

    @field_validator("stop_price", mode="before")
    @classmethod
    def validate_stop_price(cls, value: float | None) -> float | None:
        """Ensure stop_price, when provided, is strictly positive.

        Parameters
        ----------
        value:
            Raw stop_price value or ``None``.

        Returns
        -------
        float | None
            Validated stop_price or ``None``.

        Raises
        ------
        ValueError
            If stop_price is provided but is zero or negative.
        """
        if value is not None and value <= 0:
            raise ValueError(f"stop_price must be > 0, got {value}")
        return value

    # ── Cross-field validators ────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_price_required_for_limit(self) -> "OrderInput":
        """Enforce that LIMIT orders always include a price.

        Returns
        -------
        OrderInput
            The validated model instance.

        Raises
        ------
        ValueError
            If *order_type* is ``"LIMIT"`` and *price* is ``None``.
        """
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("price is required for LIMIT orders")
        return self

    @model_validator(mode="after")
    def validate_stop_limit_fields(self) -> "OrderInput":
        """Enforce that STOP_LIMIT orders include both price and stop_price.

        Returns
        -------
        OrderInput
            The validated model instance.

        Raises
        ------
        ValueError
            If *order_type* is ``"STOP_LIMIT"`` and either *price* or
            *stop_price* is ``None``.
        """
        if self.order_type == "STOP_LIMIT":
            missing = []
            if self.price is None:
                missing.append("price")
            if self.stop_price is None:
                missing.append("stop_price")
            if missing:
                raise ValueError(
                    f"STOP_LIMIT orders require: {', '.join(missing)}"
                )
        return self
