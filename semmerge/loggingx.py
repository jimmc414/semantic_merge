"""Logging configuration helpers for the semantic merge engine."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("semmerge")

_handler = logging.StreamHandler()
_formatter = logging.Formatter("%(levelname)s %(message)s")
_handler.setFormatter(_formatter)
logger.addHandler(_handler)

# Convert environment variable to proper logging level
_log_level_str = os.environ.get("SEMMERGE_LOG", "INFO").upper()
_log_level = getattr(logging, _log_level_str, logging.INFO)
logger.setLevel(_log_level)
