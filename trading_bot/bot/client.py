"""
bot/client.py
~~~~~~~~~~~~~
Low-level Binance Futures Testnet REST client.

All HTTP communication goes through this module.  Every outgoing request and
every incoming response is logged at DEBUG level so the file log contains a
complete audit trail without cluttering the terminal.
"""

import hashlib
import hmac
import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("trading_bot.client")

BASE_URL = "https://testnet.binancefuture.com"
_TIMEOUT = 10.0  # seconds


# ── Custom exception ──────────────────────────────────────────────────────────


class BinanceAPIError(Exception):
    """Raised when the Binance API returns a non-2xx HTTP response.

    Attributes
    ----------
    status_code:
        HTTP status code returned by the server.
    error_code:
        Binance application-level error code (``-XXXX`` integer), or ``None``
        if the response body could not be parsed.
    message:
        Human-readable error description from the API.
    """

    def __init__(self, status_code: int, error_code: int | None, message: str) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(
            f"Binance API error {status_code} "
            f"(code={error_code}): {message}"
        )


# ── Client ────────────────────────────────────────────────────────────────────


class BinanceClient:
    """Authenticated HTTP client for the Binance USDT-M Futures Testnet.

    Parameters
    ----------
    api_key:
        Testnet API key loaded from the environment.
    api_secret:
        Testnet API secret loaded from the environment.

    Notes
    -----
    * Uses ``httpx`` (not ``python-binance``) for all HTTP calls.
    * Every signed request appends ``timestamp`` and ``signature`` query
      parameters as required by the Binance REST API.
    * A 10-second timeout is applied to every request.
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=_TIMEOUT,
            headers={
                "X-MBX-APIKEY": self._api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Append ``timestamp`` and HMAC-SHA256 ``signature`` to *params*.

        Parameters
        ----------
        params:
            Existing query / body parameters (mutated in-place and returned).

        Returns
        -------
        dict
            The same *params* dict with ``timestamp`` and ``signature`` added.
        """
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse an ``httpx.Response`` and raise on errors.

        Parameters
        ----------
        response:
            The raw HTTP response object.

        Returns
        -------
        dict
            Parsed JSON body on success.

        Raises
        ------
        BinanceAPIError
            If the HTTP status code is not in the 2xx range.
        """
        logger.debug(
            "Response | status=%s | body=%s",
            response.status_code,
            response.text[:2000],  # truncate very large bodies in logs
        )

        if response.is_success:
            return response.json()

        # Attempt to extract Binance-specific error fields
        error_code: int | None = None
        message = response.text
        try:
            body = response.json()
            error_code = body.get("code")
            message = body.get("msg", message)
        except Exception:
            pass

        raise BinanceAPIError(
            status_code=response.status_code,
            error_code=error_code,
            message=message,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> dict[str, Any]:
        """Execute a signed or unsigned GET request.

        Parameters
        ----------
        path:
            API endpoint path (e.g. ``"/fapi/v1/time"``).
        params:
            Optional query parameters.
        signed:
            Whether to append timestamp + signature.

        Returns
        -------
        dict
            Parsed JSON response body.
        """
        params = params or {}
        if signed:
            params = self._sign(params)

        logger.debug("GET %s | params=%s", path, params)

        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise BinanceAPIError(0, None, f"Request timed out after {_TIMEOUT}s: {exc}") from exc
        except httpx.NetworkError as exc:
            raise BinanceAPIError(0, None, f"Network error: {exc}") from exc

        return self._handle_response(response)

    def _post(self, path: str, params: dict[str, Any], signed: bool = True) -> dict[str, Any]:
        """Execute a signed POST request.

        Parameters
        ----------
        path:
            API endpoint path (e.g. ``"/fapi/v1/order"``).
        params:
            Form body parameters.
        signed:
            Whether to append timestamp + signature (default ``True``).

        Returns
        -------
        dict
            Parsed JSON response body.
        """
        if signed:
            params = self._sign(params)

        logger.debug("POST %s | params=%s", path, params)

        try:
            response = self._client.post(path, data=params)
        except httpx.TimeoutException as exc:
            raise BinanceAPIError(0, None, f"Request timed out after {_TIMEOUT}s: {exc}") from exc
        except httpx.NetworkError as exc:
            raise BinanceAPIError(0, None, f"Network error: {exc}") from exc

        return self._handle_response(response)

    # ── Public API methods ────────────────────────────────────────────────────

    def get_server_time(self) -> dict[str, Any]:
        """Fetch the current Binance server time.

        Returns
        -------
        dict
            ``{"serverTime": <unix_ms>}``
        """
        return self._get("/fapi/v1/time")

    def get_exchange_info(self, symbol: str) -> dict[str, Any]:
        """Fetch exchange trading rules and symbol information.

        Parameters
        ----------
        symbol:
            Trading pair symbol, e.g. ``"BTCUSDT"``.

        Returns
        -------
        dict
            Full exchange info response filtered to the requested symbol.
        """
        return self._get("/fapi/v1/exchangeInfo", params={"symbol": symbol.upper()})

    def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Submit a new order to the Binance Futures Testnet.

        Parameters
        ----------
        params:
            Order parameters as required by the Binance API (``symbol``,
            ``side``, ``type``, ``quantity``, etc.).  Do **not** include
            ``timestamp`` or ``signature`` — they are added automatically.

        Returns
        -------
        dict
            Full order response from the API.

        Raises
        ------
        BinanceAPIError
            On any non-2xx response or network/timeout failure.
        """
        return self._post("/fapi/v1/order", params=params)

    def close(self) -> None:
        """Close the underlying ``httpx`` client and release connections."""
        self._client.close()

    # ── Context manager support ───────────────────────────────────────────────

    def __enter__(self) -> "BinanceClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
