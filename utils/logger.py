"""
Structured logging for Lead Hunter using loguru.
Provides colored console output and file-based log rotation.
"""

import sys
from pathlib import Path
from loguru import logger

from config.settings import settings

# Remove default handler
logger.remove()

# ─── Console handler (colored, concise) ───────────────────
logger.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
        "<level>{message}</level>"
    ),
    level="INFO",
    colorize=True,
)

# ─── File handler (detailed, with rotation) ───────────────
_log_dir = settings.project_root / "logs"
_log_dir.mkdir(exist_ok=True)

logger.add(
    _log_dir / "lead_hunter_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
)

# ─── Error file handler (errors only) ─────────────────────
logger.add(
    _log_dir / "errors_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
    level="ERROR",
    rotation="5 MB",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
)


def get_logger(name: str = "lead_hunter"):
    """Get a named logger instance."""
    return logger.bind(name=name)
