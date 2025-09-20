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


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit("semmerge-driver requires %O %A %B arguments")

    base_file, ours_file, theirs_file = sys.argv[1:4]

    repo_root = pathlib.Path(run(["git", "rev-parse", "--show-toplevel"]))
    head = run(["git", "rev-parse", "HEAD"])
    merge_head = os.environ.get("GITHEAD_REF") or run(["git", "rev-parse", "MERGE_HEAD"])
    base_commit = run(["git", "merge-base", "HEAD", merge_head])

    lock = repo_root / ".git" / ".semmerge.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if not lock.exists():
        lock.write_text(merge_head)
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
