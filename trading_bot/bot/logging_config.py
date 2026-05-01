"""
bot/logging_config.py
~~~~~~~~~~~~~~~~~~~~~
Centralised logging configuration for the trading bot.

Call ``setup_logging()`` once at application startup (in cli.py) before any
other module emits log records.
"""

import logging
import os
from pathlib import Path

from rich.logging import RichHandler

LOGGER_NAME = "trading_bot"
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "trading_bot.log"

_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the root ``trading_bot`` logger with two handlers.

    Handlers
    --------
    1. **FileHandler** – writes to ``logs/trading_bot.log`` at DEBUG level so
       every request/response detail is persisted to disk.
    2. **RichHandler** (StreamHandler) – writes to the terminal at the
       requested *log_level* with coloured, human-friendly output.

    Side-effects
    ------------
    * Creates the ``logs/`` directory if it does not already exist.
    * Suppresses noisy ``httpx`` log records by setting that logger to WARNING.

    Parameters
    ----------
    log_level:
        Minimum level for terminal output.  Accepts any standard level name
        (``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``).
        Defaults to ``"INFO"``.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)  # capture everything; handlers filter

    # Avoid adding duplicate handlers when setup_logging is called more than once
    if logger.handlers:
        logger.handlers.clear()

    # ── File handler ──────────────────────────────────────────────────────────
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # ── Rich terminal handler ─────────────────────────────────────────────────
    rich_handler = RichHandler(
        level=numeric_level,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        show_path=False,
        markup=True,
    )
    logger.addHandler(rich_handler)

    # ── Suppress noisy third-party loggers ───────────────────────────────────
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
