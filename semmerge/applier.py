"""Apply semantic operations to a working tree."""
from __future__ import annotations

import pathlib
import re
import shutil
import tempfile
from typing import Iterable

from .loggingx import logger
from .ops import Op


def apply_ops(base_tree: pathlib.Path, ops: Iterable[Op]) -> pathlib.Path:
    """Apply *ops* onto a copy of *base_tree* and return the merged tree path."""

    base_tree = pathlib.Path(base_tree)
    out = pathlib.Path(tempfile.mkdtemp(prefix="semmerge_merged_"))
    shutil.copytree(base_tree, out, dirs_exist_ok=True)

    for op in ops:
        if op.type == "moveDecl":
            _apply_move_decl(out, op)
        elif op.type == "renameSymbol":
            _apply_rename_symbol(out, op)
        elif op.type == "modifyImport":
            _apply_modify_import(out, op)
        elif op.type == "moveFile":
            _apply_move_file(out, op)
        else:
            logger.debug("No applier hook for op %s", op.type)

    return out


def _apply_move_decl(root: pathlib.Path, op: Op) -> None:
    old_file = op.params.get("oldFile") or op.params.get("file")
    new_file = op.params.get("newFile") or op.params.get("file")
    if not old_file or not new_file:
        return
    src = root / _normalize_relpath(old_file)
    dst = root / _normalize_relpath(new_file)
    if src == dst:
        return
    if not src.exists():
        logger.debug("moveDecl source missing: %s", src)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)


def _apply_move_file(root: pathlib.Path, op: Op) -> None:
    old_path = op.params.get("oldPath")
    new_path = op.params.get("newPath")
    if not old_path or not new_path:
        return
    src = root / _normalize_relpath(old_path)
    dst = root / _normalize_relpath(new_path)
    if not src.exists():
        logger.debug("moveFile source missing: %s", src)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)


def _apply_rename_symbol(root: pathlib.Path, op: Op) -> None:
    file_path = op.params.get("file") or op.params.get("newFile")
    old_name = op.params.get("oldName")
    new_name = op.params.get("newName")
    if not file_path or not old_name or not new_name:
        return
    path = root / _normalize_relpath(file_path)
    if not path.exists():
        logger.debug("renameSymbol target missing: %s", path)
        return
    code = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"\b{re.escape(str(old_name))}\b")
    code = pattern.sub(str(new_name), code)
    path.write_text(code, encoding="utf-8")


def _apply_modify_import(root: pathlib.Path, op: Op) -> None:
    file_path = op.params.get("file")
    old_import = op.params.get("oldImport")
    new_import = op.params.get("newImport")
    if not file_path or old_import is None or new_import is None:
        return
    path = root / _normalize_relpath(file_path)
    if not path.exists():
        logger.debug("modifyImport target missing: %s", path)
        return
    code = path.read_text(encoding="utf-8")
    code = str(code).replace(str(old_import), str(new_import))
    path.write_text(code, encoding="utf-8")


def _normalize_relpath(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(path.anchor)
        except ValueError:
            path = pathlib.Path(path.name)
    return path
