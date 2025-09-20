"""Git helper utilities."""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
from typing import Iterable


def run_git(args: Iterable[str]) -> str:
    """Run ``git`` with ``args`` and return its stdout."""

    proc = subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE, text=True)
    return proc.stdout.strip()


def resolve_rev(rev: str) -> str:
    """Resolve *rev* to a full commit hash."""

    return run_git(["rev-parse", rev])


def checkout_tree_to_temp(rev: str) -> pathlib.Path:
    """Checkout ``rev`` into a temporary directory and return its path."""

    resolved = resolve_rev(rev)
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="semmerge_tree_"))
    archive_path = tmpdir / "tree.tar"
    with archive_path.open("wb") as fh:
        subprocess.run(["git", "archive", resolved], check=True, stdout=fh)
    subprocess.run(["tar", "-xf", str(archive_path)], cwd=tmpdir, check=True)
    archive_path.unlink(missing_ok=True)
    return tmpdir


def changed_files_between(rev1: str, rev2: str) -> list[str]:
    """Return the set of files that differ between two revisions."""

    out = run_git(["diff", "--name-only", f"{rev1}..{rev2}"])
    return [line for line in out.splitlines() if line]
