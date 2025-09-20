"""Formatting utilities for the merged tree."""
from __future__ import annotations

import pathlib
import subprocess

from .loggingx import logger


def emit_files(tree_path: pathlib.Path) -> None:
    """Format files in *tree_path* using Prettier when available."""

    tree_path = pathlib.Path(tree_path)
    try:
        subprocess.run(
            ["npx", "prettier", "--write", "."],
            cwd=tree_path,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.debug("Prettier not available; skipping formatting")
    except subprocess.CalledProcessError as exc:
        logger.warning("Prettier exited with code %s", exc.returncode)
