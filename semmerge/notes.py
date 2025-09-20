"""Helpers for storing op logs inside Git notes."""
from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

from .ops import OpLog


def notes_put(commit: str, oplog: OpLog, namespace: str = "semmerge") -> None:
    """Store *oplog* as a Git note attached to *commit*."""

    fd, tmp_path = tempfile.mkstemp(prefix="semmerge_notes_")
    os.close(fd)
    tmp_file = pathlib.Path(tmp_path)
    try:
        tmp_file.write_text(oplog.to_json(), encoding="utf-8")
        subprocess.run(
            [
                "git",
                "notes",
                "--ref",
                namespace,
                "add",
                "-f",
                "-F",
                str(tmp_file),
                commit,
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        # Notes are optional, swallow errors to avoid failing merges unnecessarily.
        pass
    finally:
        tmp_file.unlink(missing_ok=True)
