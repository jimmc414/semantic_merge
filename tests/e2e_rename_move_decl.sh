#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

python -m pip install -e "$PROJECT_ROOT" >/dev/null

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

BASE_DIR="$TMP_DIR/base"
export BASE_DIR
mkdir -p "$BASE_DIR/src"

cat > "$BASE_DIR/src/util.ts" <<'TS'
export function foo(x: number) {
  return x + 1;
}
TS

python <<'PY'
import os
import pathlib
import shutil
import sys

from semmerge.applier import apply_ops
from semmerge.compose import compose_oplogs
from semmerge.ops import Op, Target

base_dir = pathlib.Path(os.environ["BASE_DIR"])

rename_op = Op.new(
    op_type="renameSymbol",
    target=Target(symbolId="symbol-foo", addressId="addr-old"),
    params={"oldName": "foo", "newName": "bar", "file": "src/util.ts"},
)

move_op = Op.new(
    op_type="moveDecl",
    target=Target(symbolId="symbol-foo", addressId="addr-old"),
    params={
        "oldAddress": "addr-old",
        "newAddress": "addr-new",
        "oldFile": "src/util.ts",
        "newFile": "lib/util.ts",
    },
)

composed, conflicts = compose_oplogs([rename_op], [move_op])
if conflicts:
    print("Unexpected conflicts during compose", file=sys.stderr)
    sys.exit(1)

rename_ops = [op for op in composed if op.type == "renameSymbol"]
if not rename_ops:
    print("Composed operations missing renameSymbol", file=sys.stderr)
    sys.exit(1)

rename_params = rename_ops[0].params
expected_path = "lib/util.ts"
if rename_params.get("file") != expected_path and rename_params.get("newFile") != expected_path:
    print("renameSymbol params do not reference moved file", file=sys.stderr)
    sys.exit(1)

merged_tree = apply_ops(base_dir, composed)
try:
    result_path = merged_tree / expected_path
    if not result_path.exists():
        print(f"Expected {expected_path} to exist after applying ops", file=sys.stderr)
        sys.exit(1)
    contents = result_path.read_text(encoding="utf-8")
    if "function bar" not in contents:
        print("Renamed identifier not found in merged file", file=sys.stderr)
        sys.exit(1)
finally:
    shutil.rmtree(merged_tree, ignore_errors=True)

print("Rename+move composition succeeded")
PY
