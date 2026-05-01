"""
cli.py
~~~~~~
Typer-based CLI entry point for the Binance Futures Testnet trading bot.

Commands
--------
place-order   Place a MARKET, LIMIT, or STOP_LIMIT order.
server-time   Fetch and display the current Binance server time.

Global flags
------------
--verbose / -v    Switch terminal log output to DEBUG level.
--dry-run         Simulate orders locally — no API keys required, no network
                  calls made.  Useful for testing the full CLI flow offline.

Usage
-----
    python cli.py --help
    python cli.py --dry-run place-order --symbol BTCUSDT --side BUY --order-type MARKET --qty 0.001
    python cli.py --dry-run server-time
    python cli.py server-time
"""

import os
import time
from datetime import datetime, timezone
from typing import Optional

import typer
from dotenv import load_dotenv
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bot.client import BinanceAPIError, BinanceClient
from bot.logging_config import setup_logging
from bot.orders import OrderManager, OrderResult
from bot.validators import OrderInput

# Load .env before anything else so os.environ is populated
load_dotenv()

app = typer.Typer(
    name="trading-bot",
    help="Binance Futures Testnet trading bot — place orders from the CLI.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)

# ── Global state (set by app callback, read by commands) ──────────────────────
_verbose: bool = False
_dry_run: bool = False


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Simulate locally — no API keys or network required.",
    ),
) -> None:
    """Binance Futures Testnet trading bot."""
    global _verbose, _dry_run
    _verbose = verbose
    _dry_run = dry_run


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_client() -> BinanceClient | None:
    """Build a ``BinanceClient`` from environment variables.

    In dry-run mode this function returns ``None`` — no client is needed.

    Returns
    -------
    BinanceClient | None
        Authenticated client, or ``None`` in dry-run mode.

    Raises
    ------
    typer.Exit
        With code 1 if credentials are missing in live mode.
    """
    setup_logging("DEBUG" if _verbose else "INFO")

    if _dry_run:
        return None

    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()

    if not api_key or api_key == "your_testnet_api_key_here":
        err_console.print(
            "[bold red]❌  BINANCE_API_KEY is not set.[/bold red]\n"
            "Copy [cyan].env.example[/cyan] to [cyan].env[/cyan] and fill in your testnet credentials.\n"
            "[dim]Tip: use [bold]--dry-run[/bold] to simulate without any keys.[/dim]"
        )
        raise typer.Exit(code=1)

    if not api_secret or api_secret == "your_testnet_api_secret_here":
        err_console.print(
            "[bold red]❌  BINANCE_API_SECRET is not set.[/bold red]\n"
            "Copy [cyan].env.example[/cyan] to [cyan].env[/cyan] and fill in your testnet credentials.\n"
            "[dim]Tip: use [bold]--dry-run[/bold] to simulate without any keys.[/dim]"
        )
        raise typer.Exit(code=1)

    return BinanceClient(api_key=api_key, api_secret=api_secret)


def _print_order_request_panel(order_input: OrderInput) -> None:
    """Render a Rich panel summarising the order about to be submitted.

    Parameters
    ----------
    order_input:
        Validated order input model.
    """
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()

    table.add_row("Symbol:", order_input.symbol)
    side_colour = "green" if order_input.side == "BUY" else "red"
    table.add_row("Side:", f"[{side_colour}]{order_input.side}[/{side_colour}]")
    table.add_row("Type:", order_input.order_type)
    table.add_row("Quantity:", str(order_input.quantity))

    if order_input.price is not None:
        table.add_row("Price:", str(order_input.price))
    if order_input.stop_price is not None:
        table.add_row("Stop Price:", str(order_input.stop_price))

    if _dry_run:
        table.add_row("Mode:", "[bold yellow]DRY-RUN (simulated)[/bold yellow]")

    title = (
        "[bold yellow]📋 Order Request Summary [DRY-RUN][/bold yellow]"
        if _dry_run
        else "[bold yellow]📋 Order Request Summary[/bold yellow]"
    )
    console.print(Panel(table, title=title, expand=False))


def _print_order_response_panel(result: OrderResult) -> None:
    """Render a Rich panel with the order response details.

    Parameters
    ----------
    result:
        Populated ``OrderResult`` dataclass from the API or simulation.
    """
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()

    table.add_row("Order ID:", str(result.order_id))
    table.add_row("Status:", f"[bold green]{result.status}[/bold green]")
    table.add_row("Symbol:", result.symbol)
    side_colour = "green" if result.side == "BUY" else "red"
    table.add_row("Side:", f"[{side_colour}]{result.side}[/{side_colour}]")
    table.add_row("Type:", result.type)
    table.add_row("Original Qty:", str(result.orig_qty))
    table.add_row("Executed Qty:", str(result.executed_qty))
    avg = str(result.avg_price) if result.avg_price else "—"
    table.add_row("Avg Price:", avg)

    if result.dry_run:
        table.add_row("Mode:", "[bold yellow]DRY-RUN (simulated)[/bold yellow]")

    title = (
        "[bold yellow]📊 Order Response [DRY-RUN][/bold yellow]"
        if result.dry_run
        else "[bold green]📊 Order Response[/bold green]"
    )
    console.print(Panel(table, title=title, expand=False))


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command("place-order")
def place_order(
    symbol: str = typer.Option(..., help="Trading pair, e.g. BTCUSDT"),
    side: str = typer.Option(..., help="BUY or SELL"),
    order_type: str = typer.Option(..., "--order-type", help="MARKET, LIMIT, or STOP_LIMIT"),
    qty: float = typer.Option(..., help="Order quantity in base asset"),
    price: Optional[float] = typer.Option(None, help="Limit price (required for LIMIT / STOP_LIMIT)"),
    stop_price: Optional[float] = typer.Option(None, "--stop-price", help="Stop trigger price (required for STOP_LIMIT)"),
) -> None:
    """Place a MARKET, LIMIT, or STOP_LIMIT order on Binance Futures Testnet."""

    # ── 1. Validate inputs ────────────────────────────────────────────────────
    try:
        order_input = OrderInput(
            symbol=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=qty,
            price=price,
            stop_price=stop_price,
        )
    except ValidationError as exc:
        err_console.print("[bold red]❌  Validation error:[/bold red]")
        for error in exc.errors():
            field_name = " → ".join(str(loc) for loc in error["loc"]) if error["loc"] else "input"
            err_console.print(f"  • [yellow]{field_name}[/yellow]: {error['msg']}")
        raise typer.Exit(code=1)

    # ── 2. Print request summary ──────────────────────────────────────────────
    _print_order_request_panel(order_input)

    # ── 3. Build client (None in dry-run) and manager ─────────────────────────
    client = _get_client()

    try:
        # Pass a sentinel client in dry-run — OrderManager won't call it
        manager = OrderManager(
            client=client or BinanceClient.__new__(BinanceClient),
            dry_run=_dry_run,
        )

        # ── 4. Place the order ────────────────────────────────────────────────
        if order_input.order_type == "STOP_LIMIT":
            result = manager.place_stop_limit_order(
                symbol=order_input.symbol,
                side=order_input.side,
                quantity=order_input.quantity,
                stop_price=order_input.stop_price,  # type: ignore[arg-type]
                limit_price=order_input.price,       # type: ignore[arg-type]
            )
        else:
            result = manager.place_order(
                symbol=order_input.symbol,
                side=order_input.side,
                order_type=order_input.order_type,
                quantity=order_input.quantity,
                price=order_input.price,
            )

        # ── 5. Print response ─────────────────────────────────────────────────
        _print_order_response_panel(result)
        suffix = " [dim](simulated — no real order was placed)[/dim]" if _dry_run else ""
        console.print(f"[bold green]✅  Order placed successfully![/bold green]{suffix}")
        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except BinanceAPIError as exc:
        err_console.print(f"[bold red]❌  Order failed:[/bold red] {exc.message}")
        raise typer.Exit(code=1)
    except Exception as exc:
        err_console.print(f"[bold red]❌  Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    finally:
        if client is not None:
            client.close()


@app.command("server-time")
def server_time() -> None:
    """Fetch and display the current Binance Futures Testnet server time.

    In dry-run mode the local system clock is used instead.
    """
    client = _get_client()

    try:
        if _dry_run:
            server_ts_ms = int(time.time() * 1000)
            source = "[bold yellow]local clock (DRY-RUN)[/bold yellow]"
        else:
            data = client.get_server_time()  # type: ignore[union-attr]
            server_ts_ms = data["serverTime"]
            source = "Binance Testnet"

        dt = datetime.fromtimestamp(server_ts_ms / 1000, tz=timezone.utc)
        formatted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column()
        table.add_row("Server Time:", formatted)
        table.add_row("Unix (ms):", str(server_ts_ms))
        table.add_row("Source:", source)

        title = (
            "[bold yellow]🕐 Server Time [DRY-RUN][/bold yellow]"
            if _dry_run
            else "[bold blue]🕐 Binance Server Time[/bold blue]"
        )
        console.print(Panel(table, title=title, expand=False))

    except typer.Exit:
        raise
    except BinanceAPIError as exc:
        err_console.print(f"[bold red]❌  Failed to fetch server time:[/bold red] {exc.message}")
        raise typer.Exit(code=1)
    except Exception as exc:
        err_console.print(f"[bold red]❌  Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    finally:
        if client is not None:
            client.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
