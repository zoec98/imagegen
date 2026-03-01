"""Logging helpers shared across components."""

from __future__ import annotations

import logging
import os
import sys


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s %(levelname)s %(name)s:%(filename)s:%(lineno)d: %(message)s",
    )
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[handler],
        force=True,
    )
    httpx_level = logging.WARNING if os.getenv("PYTEST_CURRENT_TEST") else logging.DEBUG
    logging.getLogger("httpx").setLevel(httpx_level)

    # Suppress noisy 200 OK lines for static asset requests.
    class _QuietAssetFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            if "/assets/" in msg and '" 200' in msg:
                return False
            return True

    logging.getLogger("werkzeug").addFilter(_QuietAssetFilter())
