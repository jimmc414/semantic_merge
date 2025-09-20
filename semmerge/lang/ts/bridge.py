"""Bridge between Python and the TypeScript worker."""
from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Dict, Iterable, List, Tuple

from ...loggingx import logger
from ...ops import Op


class TSWorker:
    """Wrapper around the Node.js TypeScript worker."""

    def __init__(self) -> None:
        self._root = pathlib.Path(__file__).resolve().parents[3]
        self._proc: subprocess.Popen[str] | None = None
        self._msg_id = 0

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
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.close()
        except Exception:
            pass

    # Internal helpers -------------------------------------------------

    def _snapshot(self, path: pathlib.Path) -> Dict[str, object]:
        path = pathlib.Path(path)
        files = []
        for file in self._iter_ts_files(path):
            rel = file.relative_to(path)
            files.append({"path": rel.as_posix(), "content": file.read_text(encoding="utf-8")})
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
        if self._proc and self._proc.poll() is None:
            return self._proc
        worker_path = self._root / "workers" / "ts" / "dist" / "index.js"
        if not worker_path.exists():
            raise RuntimeError(
                "TypeScript worker not built. Run `npm --prefix workers/ts install` and "
                "`npm --prefix workers/ts run build` first."
            )
        logger.debug("Starting TypeScript worker at %s", worker_path)
        self._proc = subprocess.Popen(
            ["node", str(worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=self._root,
        )
        self._msg_id = 0
        return self._proc
