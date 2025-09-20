"""Logging configuration helpers for the semantic merge engine."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("semmerge")

_handler = logging.StreamHandler()
_formatter = logging.Formatter("%(levelname)s %(message)s")
_handler.setFormatter(_formatter)
logger.addHandler(_handler)
logger.setLevel(os.environ.get("SEMMERGE_LOG", "INFO"))
