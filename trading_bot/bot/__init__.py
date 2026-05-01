"""
trading_bot.bot
~~~~~~~~~~~~~~~
Core package for the Binance Futures Testnet trading bot.

Exports the primary public API so callers can do:
    from bot import BinanceClient, OrderManager, OrderInput, BinanceAPIError
"""

from bot.client import BinanceClient, BinanceAPIError
from bot.orders import OrderManager, OrderResult
from bot.validators import OrderInput

__all__ = [
    "BinanceClient",
    "BinanceAPIError",
    "OrderManager",
    "OrderResult",
    "OrderInput",
]
