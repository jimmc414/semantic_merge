"""Git helper utilities."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
from typing import Iterable


def run_git(args: Iterable[str]) -> str:
    """Run ``git`` with ``args`` and return its stdout.

    Raises:
        RuntimeError: If git is not installed or the command fails.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError(
            "Git is not installed or not found in PATH. "
            "Please install git to use semantic merge."
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise RuntimeError(
            f"Git command failed: {' '.join(['git', *args])}\n"
            f"Exit code: {exc.returncode}\n"
            f"Error: {stderr}"
        )


def resolve_rev(rev: str) -> str:
    """Resolve *rev* to a full commit hash."""

    return run_git(["rev-parse", rev])


def checkout_tree_to_temp(rev: str) -> pathlib.Path:
    """Checkout ``rev`` into a temporary directory and return its path.

    Raises:
        RuntimeError: If git archive or tar extraction fails.
    """
    resolved = resolve_rev(rev)
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="semmerge_tree_"))
    archive_path = tmpdir / "tree.tar"

    try:
        with archive_path.open("wb") as fh:
            proc = subprocess.run(
                ["git", "archive", resolved],
                check=True,
                stdout=fh,
                stderr=subprocess.PIPE,
                text=False,
            )

        # Extract the archive
        try:
            subprocess.run(
                ["tar", "-xf", str(archive_path)],
                cwd=tmpdir,
                check=True,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "tar command not found. Please install tar to use semantic merge."
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            raise RuntimeError(f"Failed to extract archive: {stderr}")

        archive_path.unlink(missing_ok=True)
        return tmpdir

    except Exception:
        # Clean up the temporary directory on any error
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


def changed_files_between(rev1: str, rev2: str) -> list[str]:
    """Return the set of files that differ between two revisions."""

    out = run_git(["diff", "--name-only", f"{rev1}..{rev2}"])
    return [line for line in out.splitlines() if line]
