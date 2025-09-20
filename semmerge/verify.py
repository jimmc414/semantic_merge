"""Verification routines for merged outputs."""
from __future__ import annotations

import pathlib
import subprocess
from typing import List, Tuple

from .loggingx import logger


def typecheck_ts(tree_path: pathlib.Path) -> Tuple[bool, List[str]]:
    """Run ``tsc --noEmit`` for the project rooted at ``tree_path``.

    When the TypeScript compiler is not installed the function returns success
    and an empty diagnostics list, matching the fallback behaviour described in
    the requirements.
    """

    tree_path = pathlib.Path(tree_path)
    try:
        proc = subprocess.run(
            ["npx", "tsc", "-p", ".", "--noEmit"],
            cwd=tree_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        logger.debug("TypeScript compiler not available; skipping type-check")
        return True, []
    output = proc.stdout.splitlines()
    return proc.returncode == 0, output
