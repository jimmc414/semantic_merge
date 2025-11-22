#!/usr/bin/env python3
"""Git merge driver wrapper for the semantic merge engine."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys


def run(cmd: list[str], cwd: str | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        sys.exit(proc.returncode)
    return proc.stdout.strip()


def acquire_lock(lock_path: pathlib.Path, content: str, timeout: int = 30) -> bool:
    """Atomically acquire a lock file.

    Args:
        lock_path: Path to the lock file
        content: Content to write to the lock file
        timeout: Maximum time to wait for the lock in seconds

    Returns:
        True if lock was acquired, False otherwise
    """
    import time

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Use exclusive creation mode for atomic lock acquisition
            # This will fail if the file already exists
            with lock_path.open("x") as f:
                f.write(content)
            return True
        except FileExistsError:
            # Lock is held by another process, wait and retry
            time.sleep(0.1)
            # Check if lock is stale (older than 5 minutes)
            try:
                if time.time() - lock_path.stat().st_mtime > 300:
                    # Stale lock, try to remove it
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        pass
            except FileNotFoundError:
                pass

    return False


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit("semmerge-driver requires %O %A %B arguments")

    base_file, ours_file, theirs_file = sys.argv[1:4]

    repo_root = pathlib.Path(run(["git", "rev-parse", "--show-toplevel"]))
    head = run(["git", "rev-parse", "HEAD"])

    # Try to get MERGE_HEAD with error handling
    merge_head = os.environ.get("GITHEAD_REF")
    if not merge_head:
        try:
            merge_head = run(["git", "rev-parse", "MERGE_HEAD"])
        except SystemExit:
            # Not in a merge, this is an error
            sys.stderr.write("Error: Not in a merge state and GITHEAD_REF not set\n")
            sys.exit(1)

    base_commit = run(["git", "merge-base", "HEAD", merge_head])

    lock = repo_root / ".git" / ".semmerge.lock"

    # Atomically acquire lock
    if not acquire_lock(lock, merge_head):
        sys.stderr.write("Error: Could not acquire merge lock after timeout\n")
        sys.exit(1)

    try:
        code = subprocess.run(
            ["python3", "-m", "semmerge", "semmerge", base_commit, head, merge_head, "--inplace", "--git"],
            cwd=repo_root,
        ).returncode
        if code != 0:
            sys.exit(code)
    finally:
        lock.unlink(missing_ok=True)

    rel = pathlib.Path(os.path.relpath(ours_file, repo_root))
    resolved = repo_root / rel
    if resolved.exists():
        shutil.copyfile(resolved, ours_file)
    sys.exit(0)


if __name__ == "__main__":
    main()
