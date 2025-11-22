"""Bridge between Python and the TypeScript worker."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
from typing import Dict, Iterable, List, Tuple

from ...loggingx import logger
from ...ops import Op


class TSWorker:
    """Wrapper around the Node.js TypeScript worker."""

    def __init__(self, worker_path: pathlib.Path | None = None) -> None:
        """Initialize the TypeScript worker.

        Args:
            worker_path: Optional custom path to the worker index.js file.
                        If not provided, will search in common locations.
        """
        self._worker_path = worker_path or self._find_worker_path()
        self._proc: subprocess.Popen[str] | None = None
        self._msg_id = 0

    def _find_worker_path(self) -> pathlib.Path:
        """Find the TypeScript worker in common installation locations."""
        # Try relative to this file (development mode)
        dev_root = pathlib.Path(__file__).resolve().parents[3]
        dev_path = dev_root / "workers" / "ts" / "dist" / "index.js"
        if dev_path.exists():
            return dev_path

        # Try environment variable override
        env_path = os.environ.get("SEMMERGE_WORKER_PATH")
        if env_path:
            worker_path = pathlib.Path(env_path)
            if worker_path.exists():
                return worker_path

        # Try package data location (when installed via pip)
        try:
            import importlib.resources
            # For Python 3.9+
            if hasattr(importlib.resources, 'files'):
                pkg_path = importlib.resources.files('semmerge') / '..' / 'workers' / 'ts' / 'dist' / 'index.js'
                if hasattr(pkg_path, 'exists') and pkg_path.exists():  # type: ignore
                    return pathlib.Path(str(pkg_path))
        except Exception:
            pass

        # If all else fails, return the dev path and let the error be raised later
        return dev_path

    def build_and_diff(
        self,
        base_tree: pathlib.Path,
        left_tree: pathlib.Path,
        right_tree: pathlib.Path,
    ) -> Tuple[List[Op], List[Op], Dict[str, object]]:
        result = self._rpc(
            "buildAndDiff",
            {
                "base": self._snapshot(base_tree),
                "left": self._snapshot(left_tree),
                "right": self._snapshot(right_tree),
                "config": {},
            },
        )
        return (
            [Op.from_dict(item) for item in result.get("opLogLeft", [])],
            [Op.from_dict(item) for item in result.get("opLogRight", [])],
            result.get("symbolMaps", {}),
        )

    def diff(self, base_tree: pathlib.Path, right_tree: pathlib.Path) -> List[Op]:
        result = self._rpc(
            "diff",
            {"base": self._snapshot(base_tree), "right": self._snapshot(right_tree)},
        )
        return [Op.from_dict(item) for item in result.get("opLogRight", [])]

    def close(self) -> None:
        """Close the worker process gracefully."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logger.warning("Worker did not terminate gracefully, killing it")
                try:
                    self._proc.kill()
                    self._proc.wait(timeout=1)
                except Exception as exc:
                    logger.error("Failed to kill worker process: %s", exc)
        self._proc = None

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.close()
        except Exception:
            pass

    # Internal helpers -------------------------------------------------

    def _snapshot(self, path: pathlib.Path) -> Dict[str, object]:
        """Create a snapshot of all TypeScript files in the given path.

        Raises:
            UnicodeDecodeError: If a file cannot be decoded as UTF-8.
            OSError: If a file cannot be read.
        """
        path = pathlib.Path(path)
        files = []
        for file in self._iter_ts_files(path):
            rel = file.relative_to(path)
            try:
                content = file.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                logger.warning("Skipping file %s: cannot decode as UTF-8", file)
                # Try with error handling
                try:
                    content = file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    # Skip files we can't read
                    continue
            except OSError as exc:
                logger.warning("Skipping file %s: %s", file, exc)
                continue
            files.append({"path": rel.as_posix(), "content": content})
        return {"files": files, "project": None}

    def _iter_ts_files(self, root: pathlib.Path) -> Iterable[pathlib.Path]:
        exts = {".ts", ".tsx", ".js", ".jsx"}
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in exts:
                yield path

    def _rpc(self, method: str, params: Dict[str, object]) -> Dict[str, object]:
        proc = self._ensure_proc()
        self._msg_id += 1
        message = json.dumps({"jsonrpc": "2.0", "id": self._msg_id, "method": method, "params": params})
        assert proc.stdin and proc.stdout
        proc.stdin.write(message + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("TypeScript worker exited unexpectedly")
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if "error" in payload:
                err = payload["error"]
                raise RuntimeError(f"Worker error {err}")
            return payload.get("result", {})

    def _ensure_proc(self) -> subprocess.Popen[str]:
        """Ensure the worker process is running.

        Raises:
            RuntimeError: If the worker cannot be found or started.
        """
        if self._proc and self._proc.poll() is None:
            return self._proc

        if not self._worker_path.exists():
            raise RuntimeError(
                f"TypeScript worker not found at {self._worker_path}.\n"
                "Please ensure:\n"
                "1. The worker is built: npm --prefix workers/ts install && npm --prefix workers/ts run build\n"
                "2. Or set SEMMERGE_WORKER_PATH environment variable to the worker location"
            )

        logger.debug("Starting TypeScript worker at %s", self._worker_path)

        try:
            self._proc = subprocess.Popen(
                ["node", str(self._worker_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self._worker_path.parent.parent.parent,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Node.js is not installed or not found in PATH. "
                "Please install Node.js to use semantic merge."
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to start TypeScript worker: {exc}")

        self._msg_id = 0
        return self._proc
