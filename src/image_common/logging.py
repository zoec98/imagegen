"""Logging helpers shared across components."""

from __future__ import annotations

import logging
import os
import sys


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s %(levelname)s %(name)s:%(filename)s:%(lineno)d: %(message)s",
    )
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
