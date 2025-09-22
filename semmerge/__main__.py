"""Command line interface for the semantic merge engine."""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
from typing import Iterable, Sequence

import click

from .applier import apply_ops
from .compose import compose_oplogs
from .emitter import emit_files
from .git_api import checkout_tree_to_temp, resolve_rev
from .lang.ts.bridge import TSWorker
from .loggingx import logger
from .notes import notes_put
from .ops import OpLog
from .verify import typecheck_ts


@click.group()
def main() -> None:
    """Semantic merge entry point."""


@main.command(help="Semantic diff: print op log between two revisions")
@click.argument("rev1")
@click.argument("rev2")
@click.option("--json-out", is_flag=True, default=False, help="Emit JSON instead of a pretty listing")
def semdiff(rev1: str, rev2: str, json_out: bool) -> None:
    worker = TSWorker()
    merged_tree: pathlib.Path | None = None
    base_tree = checkout_tree_to_temp(rev1)
    right_tree = checkout_tree_to_temp(rev2)
    try:
        ops = worker.diff(base_tree, right_tree)
    finally:
        worker.close()
        _cleanup_temp_dirs([base_tree, right_tree])
    if json_out:
        click.echo(json.dumps([op.to_dict() for op in ops], indent=2))
    else:
        for op in ops:
            click.echo(op.pretty())


@main.command(help="Semantic merge base A B into working tree")
@click.argument("base")
@click.argument("a")
@click.argument("b")
@click.option("--inplace", is_flag=True, help="Write the merge result into the current working tree")
@click.option("--git", is_flag=True, help="Flag set when invoked via git merge driver")
def semmerge(base: str, a: str, b: str, inplace: bool, git: bool) -> None:  # noqa: ARG001 - CLI signature
    logger.info("Starting semantic merge base=%s A=%s B=%s", base, a, b)
    worker = TSWorker()
    base_tree = checkout_tree_to_temp(base)
    left_tree = checkout_tree_to_temp(a)
    right_tree = checkout_tree_to_temp(b)
    merged_tree: pathlib.Path | None = None

    try:
        op_log_left, op_log_right, _symbol_maps = worker.build_and_diff(base_tree, left_tree, right_tree)
        composed_ops, conflicts = compose_oplogs(op_log_left, op_log_right)

        if conflicts:
            _write_conflict_reports(conflicts)
            sys.exit(1)

        merged_tree = apply_ops(base_tree, composed_ops)
        emit_files(merged_tree)
        ok, diagnostics = typecheck_ts(merged_tree)
        if not ok:
            _report_type_errors(diagnostics)
            sys.exit(2)

        if inplace:
            _copy_tree_into_cwd(merged_tree)

        notes_put(resolve_rev(a), OpLog(op_log_left))
        notes_put(resolve_rev(b), OpLog(op_log_right))
        logger.info("Merge complete")
    finally:
        worker.close()
        _cleanup_temp_dirs([base_tree, left_tree, right_tree])
        if merged_tree is not None and not inplace:
            _cleanup_temp_dirs([merged_tree])


def _copy_tree_into_cwd(tmp_path: pathlib.Path) -> None:
    tmp_path = pathlib.Path(tmp_path)
    cwd = pathlib.Path.cwd()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            target = cwd / path.relative_to(tmp_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _write_conflict_reports(conflicts: Sequence[object]) -> None:
    out = pathlib.Path(".semmerge-conflicts.json")
    payload = [conflict.to_dict() if hasattr(conflict, "to_dict") else conflict for conflict in conflicts]
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _report_type_errors(diagnostics: Iterable[str]) -> None:
    for line in diagnostics:
        click.echo(line, err=True)


def _cleanup_temp_dirs(paths: Iterable[pathlib.Path]) -> None:
    for path in paths:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass
        except OSError:
            # Ignore best-effort cleanup failures.
            pass


if __name__ == "__main__":  # pragma: no cover
    main()
