"""Application-wide logging configuration."""

import logging
import sys
from pathlib import Path
from typing import Optional


_configured = False


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """Configure application-wide logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path for file logging
        format_string: Optional custom format string

    Returns:
        Root logger for the application
    """
    global _configured

    if format_string is None:
        format_string = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    # Create formatter
    formatter = logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")

    # Get root logger for app
    root_logger = logging.getLogger("akquise")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers if reconfiguring
    if _configured:
        root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _configured = True
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module.

    Args:
        name: Module name (e.g., "orchestrator", "sourcing.bund")

    Returns:
        Logger instance
    """
    return logging.getLogger(f"akquise.{name}")
