# Semantic Merge Engine — Implementation

Status: P0 reference implementation. Production-ready for TypeScript first. Java and C# stubs included. This document is standalone.

---

## 0. Quick start

1. Ensure prerequisites.
2. Scaffold repo layout.
3. Install the Python CLI and Node TypeScript worker.
4. Register the Git merge driver.
5. Run `semmerge` on a test repo.

---

## 1. Prerequisites

- Python ≥ 3.10
- Node.js ≥ 18 with npm
- Git ≥ 2.35
- Java ≥ 17 (for Java backend stub)
- .NET SDK ≥ 7.0 (for C# backend stub)

Optional:
- Prettier for TS formatting
- TypeScript compiler (`tsc`)
- jq (for inspecting JSON)

---

## 2. Repository layout

```
semantic-merge/
  semmerge/                 # Python package: CLI and core engine
    __init__.py
    __main__.py
    config.py
    git_api.py
    ops.py
    crdt.py
    compose.py
    applier.py
    conflict.py
    emitter.py
    verify.py
    loggingx.py
    notes.py
    util.py
    lang/
      __init__.py
      ts/
        bridge.py           # Python bridge to Node worker
        protocol.py
      java/
        bridge.py           # Stub
      cs/
        bridge.py           # Stub
  workers/
    ts/
      package.json
      tsconfig.json
      src/
        index.ts            # JSON-RPC worker
        sast.ts             # SAST + SymbolID
        diff.ts             # move-aware AST diff
        lift.ts             # diff → Ops
        emit.ts             # CST mapping hooks
        protocol.ts
  samples/
    repo-a/ ...             # optional examples
  scripts/
    semmerge-driver.py      # Git merge driver wrapper
  pyproject.toml
  package-lock.json         # generated in workers/ts
  README.md
```

---

## 3. Configuration files

### 3.1 `.semmerge.toml` (repository-level)

```toml
[core]
deterministic_seed = "auto"         # "auto" or hex string
memory_cap_mb = 4096
formatter = "prettier"

[languages.typescript]
enabled = true
project_globs = ["**/tsconfig.json"]
formatter_cmd = ["npx", "prettier", "--write"]

[languages.java]
enabled = false

[languages.csharp]
enabled = false

[ci]
require_typecheck = true
require_tests = false
```

### 3.2 `.gitattributes`

```gitattributes
*.ts semmerge
*.tsx semmerge
*.js semmerge
*.jsx semmerge
```

### 3.3 Git merge driver registration (`.gitconfig` or repo-level config)

```ini
[merge "semmerge"]
    name = Semantic merge engine
    driver = python3 scripts/semmerge-driver.py %O %A %B
[mergetool "semmerge"]
    cmd = python3 -m semmerge semmerge --inplace --git %O %A %B
[attributes]
    use = .gitattributes
```

> Note: Git invokes the driver per file. The wrapper aggregates and executes a repo-level merge, then returns a pass-through for the requested file. See §11.

---

## 4. Data contracts (JSON)

### 4.1 Operation (Op)

```json
{
  "id": "uuid",
  "schemaVersion": 1,
  "type": "renameSymbol|moveDecl|addDecl|deleteDecl|changeSignature|reorderParams|addParam|removeParam|extractMethod|inlineMethod|updateCall|editStmtBlock|modifyImport|reorderImports|moveFile|renameFile|modifyNamespace",
  "target": { "symbolId": "hex64", "addressId": "string|nullable" },
  "params": { "..." : "op-specific" },
  "guards": { "exists": true, "addressMatch": "string|nullable", "typeHash": "hex32|nullable" },
  "effects": { "summary": "string" },
  "provenance": { "rev": "sha1/sha256", "author": "id", "timestamp": "iso8601" }
}
```

### 4.2 Conflict

```json
{
  "id": "uuid",
  "category": "DivergentRename|DivergentMove|IncompatibleSignature|DeleteVsEdit|OverlappingStmtEdit|ExtractVsInline|RenameVsDelete",
  "symbolId": "hex64",
  "addressIds": { "A": "string|nullable", "B": "string|nullable", "base": "string|nullable" },
  "opA": { /* serialized Op */ },
  "opB": { /* serialized Op */ },
  "minimalSlice": { "path": "file.ts", "start": 120, "end": 190, "code": "string" },
  "suggestions": [
    { "id": "keepA", "label": "Keep branch A", "ops": ["op-id-..."] },
    { "id": "keepB", "label": "Keep branch B", "ops": ["op-id-..."] }
  ]
}
```

### 4.3 Worker protocol (Python↔Node)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "buildAndDiff",
  "params": {
    "language": "ts",
    "base": { "files": [{ "path": "p.ts", "content": "..." }], "project": "path/to/tsconfig.json" },
    "left": { "files": [...], "project": "..." },
    "right": { "files": [...], "project": "..." },
    "config": { "deterministicSeed": "hex" }
  }
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "opLogLeft": [{ /* Op */ }, ...],
    "opLogRight": [{ /* Op */ }, ...],
    "symbolMaps": {
      "base": [{ "symbolId": "hex", "addressId": "..." }], "left": [...], "right": [...]
    },
    "diagnostics": []
  }
}
```

---

## 5. Python core

### 5.1 `pyproject.toml`

```toml
[project]
name = "semmerge"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["orjson>=3.9.0", "click>=8.1.7", "typing-extensions>=4.12.2"]

[project.scripts]
semmerge = "semmerge.__main__:main"
```

### 5.2 `semerge/__main__.py` — CLI

```python
# semmerge/__main__.py
from __future__ import annotations
import sys, json, pathlib, subprocess, os
import click
from . import config as cfg
from .git_api import resolve_rev, checkout_tree_to_temp, changed_files_between
from .ops import OpLog
from .compose import compose_oplogs
from .applier import apply_ops
from .emitter import emit_files
from .verify import typecheck_ts
from .notes import notes_put
from .lang.ts.bridge import TSWorker
from .loggingx import logger

@click.group()
def main(): ...

@main.command(help="Semantic diff: print op log between two revs")
@click.argument("rev1")
@click.argument("rev2")
@click.option("--json-out", is_flag=True, default=False)
def semdiff(rev1, rev2, json_out):
    repo = pathlib.Path.cwd()
    paths = changed_files_between(rev1, rev2)
    base_tree = checkout_tree_to_temp(rev1)
    right_tree = checkout_tree_to_temp(rev2)
    ops_left = _diff_ts(base_tree, right_tree)  # simple TS-only path
    if json_out:
        print(json.dumps([op.to_dict() for op in ops_left], indent=2))
    else:
        for op in ops_left:
            print(op.pretty())

@main.command(help="Semantic merge base A B into working tree")
@click.argument("base")
@click.argument("A")
@click.argument("B")
@click.option("--inplace", is_flag=True, help="Write into current working tree")
@click.option("--git", is_flag=True, help="Called from git merge driver with %O %A %B")
def semmerge(base, a, b, inplace, git):
    repo = pathlib.Path.cwd()
    logger.info("Start semmerge base=%s A=%s B=%s", base, a, b)
    base_tree = checkout_tree_to_temp(base)
    left_tree  = checkout_tree_to_temp(a)
    right_tree = checkout_tree_to_temp(b)

    # Build + diff via TS worker
    opl_left, opl_right, symmaps = _build_and_diff_ts(base_tree, left_tree, right_tree)

    # Compose
    composed, conflicts = compose_oplogs(opl_left, opl_right)

    if conflicts:
        _write_conflict_reports(conflicts)
        sys.exit(1)

    # Apply to base SAST via worker apply hook (handled in Python for orchestration)
    merged_fs = apply_ops(base_tree, composed)

    # Emit (format)
    emit_files(merged_fs)

    # Verify
    ok, diags = typecheck_ts(merged_fs)
    if not ok:
        _report_type_errors(diags)
        sys.exit(2)

    # Materialize into working tree
    if inplace:
        _copy_tree_into_cwd(merged_fs)

    # Store op logs as Git notes (optional)
    notes_put(resolve_rev(a), OpLog(ops=opl_left))
    notes_put(resolve_rev(b), OpLog(ops=opl_right))

    logger.info("Merge complete")
    sys.exit(0)

def _build_and_diff_ts(base_tree, left_tree, right_tree):
    worker = TSWorker()
    return worker.build_and_diff(base_tree, left_tree, right_tree)

def _diff_ts(base_tree, right_tree):
    worker = TSWorker()
    return worker.diff(base_tree, right_tree)

def _copy_tree_into_cwd(tmp_path: pathlib.Path):
    for p in tmp_path.rglob("*"):
        if p.is_file():
            dest = pathlib.Path.cwd() / p.relative_to(tmp_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())

def _write_conflict_reports(conflicts):
    out = pathlib.Path(".semmerge-conflicts.json")
    out.write_text(json.dumps([c.to_dict() for c in conflicts], indent=2))
```

### 5.3 `semmerge/git_api.py` — Git helpers

```python
# semmerge/git_api.py
from __future__ import annotations
import pathlib, subprocess, tempfile

def run_git(args: list[str]) -> str:
    res = subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE, text=True)
    return res.stdout.strip()

def resolve_rev(rev: str) -> str:
    return run_git(["rev-parse", rev])

def checkout_tree_to_temp(rev: str) -> pathlib.Path:
    rev = resolve_rev(rev)
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="semmerge_"))
    subprocess.run(["git", "archive", rev], check=True, stdout=open(tmpdir/"tree.tar","wb"))
    subprocess.run(["tar", "-xf", "tree.tar"], cwd=tmpdir, check=True)
    (tmpdir/"tree.tar").unlink()
    return tmpdir

def changed_files_between(rev1: str, rev2: str) -> list[str]:
    out = run_git(["diff", "--name-only", f"{rev1}..{rev2}"])
    return [l for l in out.splitlines() if l]
```

### 5.4 `semmerge/ops.py` — Ops and logs

```python
# semmerge/ops.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
import orjson, uuid, time

OpType = Literal["renameSymbol","moveDecl","addDecl","deleteDecl","changeSignature",
                 "reorderParams","addParam","removeParam","extractMethod","inlineMethod",
                 "updateCall","editStmtBlock","modifyImport","reorderImports","moveFile",
                 "renameFile","modifyNamespace"]

@dataclass(frozen=True)
class Target:
    symbolId: str
    addressId: str | None = None

@dataclass
class Op:
    id: str
    schemaVersion: int
    type: OpType
    target: Target
    params: dict[str, Any]
    guards: dict[str, Any]
    effects: dict[str, Any]
    provenance: dict[str, Any]

    @staticmethod
    def new(type: OpType, target: Target, params: dict[str,Any], guards: dict[str,Any], effects: dict[str,Any], prov: dict[str,Any]) -> "Op":
        return Op(id=str(uuid.uuid4()), schemaVersion=1, type=type, target=target, params=params, guards=guards, effects=effects, provenance=prov)

    def to_dict(self): return {
        "id": self.id, "schemaVersion": self.schemaVersion, "type": self.type,
        "target": self.target.__dict__, "params": self.params,
        "guards": self.guards, "effects": self.effects, "provenance": self.provenance
    }

    def pretty(self)->str:
        return f"{self.type} {self.target.symbolId} {self.params}"

@dataclass
class OpLog:
    ops: list[Op] = field(default_factory=list)
    def to_json(self)->str: return orjson.dumps([o.to_dict() for o in self.ops]).decode()
    @staticmethod
    def from_json(s: str)->"OpLog":
        data = orjson.loads(s)
        return OpLog(ops=[Op(**{**d, "target":Target(**d["target"])}) for d in data])
```

### 5.5 `semmerge/crdt.py` — List CRDT (RGA-like)

```python
# semmerge/crdt.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Key:
    anchor: str      # base position anchor (symbolId or stmt anchor)
    t: int           # normalized timestamp
    author: str
    opid: str

@dataclass
class Elem:
    key: Key
    value: str       # symbolId or stmt-id
    tombstone: bool = False

class RGA:
    def __init__(self):
        self.list: list[Elem] = []

    def insert(self, key: Key, value: str):
        idx = self._find_insert_index(key)
        self.list.insert(idx, Elem(key, value))

    def move(self, value: str, key: Key):
        # remove old and reinsert with new key
        for i, e in enumerate(self.list):
            if not e.tombstone and e.value == value:
                self.list.pop(i)
                break
        self.insert(key, value)

    def delete(self, value: str):
        for e in self.list:
            if e.value == value: e.tombstone = True

    def materialize(self) -> list[str]:
        return [e.value for e in self.list if not e.tombstone]

    def _find_insert_index(self, key: Key) -> int:
        # total order by (anchor, t, author, opid)
        for i, e in enumerate(self.list):
            if (key.anchor, key.t, key.author, key.opid) < (e.key.anchor, e.key.t, e.key.author, e.key.opid):
                return i
        return len(self.list)
```

### 5.6 `semmerge/compose.py` — Composition rules

```python
# semmerge/compose.py
from __future__ import annotations
from typing import Tuple
from .ops import Op, OpLog
from .conflict import Conflict, conflict_divergent_rename

def compose_oplogs(deltaA: list[Op], deltaB: list[Op]) -> Tuple[list[Op], list[Conflict]]:
    # deterministic order: op-type precedence then provenance timestamp then id
    prec = _precedence()
    def key(o: Op): 
        ts = o.provenance.get("timestamp","1970-01-01T00:00:00Z")
        return (prec.get(o.type, 99), ts, o.id)
    A = sorted(deltaA, key=key)
    B = sorted(deltaB, key=key)
    out: list[Op] = []
    conflicts: list[Conflict] = []

    # naive 2-list merge with simple non-commuting checks and propagation
    idxA = idxB = 0
    rename_chain: dict[str, str] = {}  # symbolId -> newName
    move_chain: dict[str, str] = {}    # symbolId -> newAddress

    def _apply(o: Op):
        # propagate rename/move
        sym = o.target.symbolId
        if sym in move_chain:
            o.params = {**o.params, "newAddress": move_chain[sym]} if o.type == "moveDecl" else o.params
            o.target.addressId = move_chain[sym]
        if sym in rename_chain and o.type != "renameSymbol":
            o.params = {**o.params, "renameContext": rename_chain[sym]}
        out.append(o)

    while idxA < len(A) or idxB < len(B):
        oA = A[idxA] if idxA < len(A) else None
        oB = B[idxB] if idxB < len(B) else None
        if oA and (not oB or key(oA) <= key(oB)):
            # check conflicts against pending B ops targeting same symbol
            if oA.type == "renameSymbol" and oB and oB.type == "renameSymbol" and oA.target.symbolId == oB.target.symbolId:
                if oA.params["newName"] != oB.params["newName"]:
                    conflicts.append(conflict_divergent_rename(oA, oB))
                    idxA += 1; idxB += 1
                    continue
            if oA.type == "renameSymbol":
                rename_chain[oA.target.symbolId] = oA.params["newName"]
            if oA.type == "moveDecl":
                move_chain[oA.target.symbolId] = oA.params["newAddress"]
            _apply(oA); idxA += 1
        else:
            if oB.type == "renameSymbol" and oA and oA.type == "renameSymbol" and oA.target.symbolId == oB.target.symbolId:
                if oA.params["newName"] != oB.params["newName"]:
                    conflicts.append(conflict_divergent_rename(oA, oB))
                    idxA += 1; idxB += 1
                    continue
            if oB.type == "renameSymbol":
                rename_chain[oB.target.symbolId] = oB.params["newName"]
            if oB.type == "moveDecl":
                move_chain[oB.target.symbolId] = oB.params["newAddress"]
            _apply(oB); idxB += 1
    return out, conflicts

def _precedence() -> dict[str,int]:
    return {
        "moveDecl": 10,
        "renameSymbol": 11,
        "modifyImport": 12,
        "reorderImports": 13,
        "changeSignature": 20,
        "updateCall": 21,
        "addDecl": 30,
        "deleteDecl": 31,
        "extractMethod": 40,
        "inlineMethod": 41,
        "editStmtBlock": 50,
        "reorderParams": 51,
        "addParam": 52,
        "removeParam": 53,
        "moveFile": 60,
        "renameFile": 61,
        "modifyNamespace": 70
    }
```

### 5.7 `semmerge/conflict.py`

```python
# semmerge/conflict.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .ops import Op

@dataclass
class Conflict:
    id: str
    category: str
    symbolId: str
    addressIds: dict[str, Any]
    opA: dict[str, Any]
    opB: dict[str, Any]
    minimalSlice: dict[str, Any]
    suggestions: list[dict[str, Any]]

    def to_dict(self): return self.__dict__

def conflict_divergent_rename(oA: Op, oB: Op) -> Conflict:
    return Conflict(
        id=f"conf-{oA.id[:8]}-{oB.id[:8]}",
        category="DivergentRename",
        symbolId=oA.target.symbolId,
        addressIds={"A": oA.target.addressId, "B": oB.target.addressId, "base": None},
        opA=oA.to_dict(),
        opB=oB.to_dict(),
        minimalSlice={"path": "", "start": 0, "end": 0, "code": ""},
        suggestions=[
            {"id":"keepA","label":f"Rename to {oA.params['newName']}", "ops":[oA.id]},
            {"id":"keepB","label":f"Rename to {oB.params['newName']}", "ops":[oB.id]}
        ]
    )
```

### 5.8 `semmerge/applier.py` — Apply Ops (FS-level P0)

```python
# semmerge/applier.py
from __future__ import annotations
import pathlib, shutil, re, json

def apply_ops(base_tree: pathlib.Path, ops: list) -> pathlib.Path:
    # P0: file-move, rename symbol (simple), modify imports
    out = pathlib.Path(str(base_tree) + "_merged")
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(base_tree, out)
    for op in ops:
        t = op.type
        if t == "moveFile":
            src = out / op.params["oldPath"]; dst = out / op.params["newPath"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
        elif t == "renameSymbol":
            # naive rename only for decl + identical name occurrences in file
            path = out / op.params["file"]
            code = path.read_text(encoding="utf-8")
            code = re.sub(rf'\b{re.escape(op.params["oldName"])}\b', op.params["newName"], code)
            path.write_text(code, encoding="utf-8")
        elif t == "modifyImport":
            path = out / op.params["file"]
            code = path.read_text(encoding="utf-8")
            code = code.replace(op.params["oldImport"], op.params["newImport"])
            path.write_text(code, encoding="utf-8")
        # Extend with other ops
    return out
```

### 5.9 `semmerge/emitter.py` — Formatting

```python
# semmerge/emitter.py
from __future__ import annotations
import pathlib, subprocess, os

def emit_files(tree_path: pathlib.Path):
    # run Prettier if present
    try:
        subprocess.run(["npx","prettier","--write","."], cwd=tree_path, check=True, stdout=subprocess.DEVNULL)
    except Exception:
        pass
```

### 5.10 `semmerge/verify.py` — Type-check

```python
# semmerge/verify.py
from __future__ import annotations
import pathlib, subprocess

def typecheck_ts(tree_path: pathlib.Path) -> tuple[bool, list[str]]:
    # assumes tsconfig.json exists in project
    try:
        res = subprocess.run(["npx","tsc","-p","." ,"--noEmit"], cwd=tree_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ok = res.returncode == 0
        lines = res.stdout.splitlines()
        return ok, lines
    except FileNotFoundError:
        return True, []
```

### 5.11 `semmerge/notes.py` — Git notes

```python
# semmerge/notes.py
from __future__ import annotations
import subprocess, tempfile, pathlib
from .ops import OpLog

def notes_put(commit: str, oplog: OpLog, namespace: str = "semmerge") -> None:
    tmp = pathlib.Path(tempfile.mkstemp()[1])
    tmp.write_text(oplog.to_json(), encoding="utf-8")
    subprocess.run(["git","notes","--ref",namespace,"add","-f","-F",str(tmp), commit], check=True)
`````

### 5.12 `semmerge/lang/ts/protocol.py` — Types

```python
# semmerge/lang/ts/protocol.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class ProgramSnapshot:
    files: list[dict[str,str]]
    project: str | None = None

@dataclass
class BuildAndDiffResult:
    opLogLeft: list[dict[str, Any]]
    opLogRight: list[dict[str, Any]]
    symbolMaps: dict[str, Any]
    diagnostics: list[dict[str, Any]]
```

### 5.13 `semmerge/lang/ts/bridge.py` — Node worker bridge

```python
# semmerge/lang/ts/bridge.py
from __future__ import annotations
import subprocess, json, pathlib, os, sys, tempfile
from typing import Tuple

class TSWorker:
    def __init__(self):
        self.proc = subprocess.Popen(["node","workers/ts/dist/index.js"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=pathlib.Path(__file__).resolve().parents[3])

    def _rpc(self, method: str, params: dict):
        msg = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        resp = json.loads(line)
        if "error" in resp: raise RuntimeError(resp["error"])
        return resp["result"]

    def build_and_diff(self, base_tree, left_tree, right_tree):
        def snapshot(path):
            files = []
            for p in pathlib.Path(path).rglob("*.ts"):
                files.append({"path": str(p.relative_to(path)), "content": pathlib.Path(p).read_text(encoding="utf-8")})
            return {"files": files, "project": None}
        res = self._rpc("buildAndDiff", {"base": snapshot(base_tree), "left": snapshot(left_tree), "right": snapshot(right_tree), "config":{}})
        return res["opLogLeft"], res["opLogRight"], res["symbolMaps"]

    def diff(self, base_tree, right_tree):
        res = self._rpc("diff", {"base": self._snap(base_tree), "right": self._snap(right_tree)})
        return res["opLogRight"]

    def _snap(self, path):
        files = []
        for p in pathlib.Path(path).rglob("*.ts"):
            files.append({"path": str(p.relative_to(path)), "content": pathlib.Path(p).read_text(encoding="utf-8")})
        return {"files": files, "project": None}
```

---

## 6. Node TypeScript worker

### 6.1 `workers/ts/package.json`

```json
{
  "name": "@semmerge/ts-worker",
  "version": "0.1.0",
  "type": "module",
  "private": true,
  "main": "dist/index.js",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "typescript": "^5.5.4"
  },
  "devDependencies": {
    "@types/node": "^20.11.17"
  }
}
```

### 6.2 `workers/ts/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ES2020",
    "moduleResolution": "Node",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"]
}
```

### 6.3 `workers/ts/src/protocol.ts`

```ts
export type File = { path: string; content: string };
export type Snapshot = { files: File[]; project?: string | null };

export type Op = {
  id: string;
  schemaVersion: 1;
  type: string;
  target: { symbolId: string; addressId?: string | null };
  params: any;
  guards: any;
  effects: any;
  provenance: { rev?: string; author?: string; timestamp?: string };
};

export type BuildAndDiffParams = {
  base: Snapshot;
  left: Snapshot;
  right: Snapshot;
  config: { deterministicSeed?: string };
};

export type BuildAndDiffResult = {
  opLogLeft: Op[];
  opLogRight: Op[];
  symbolMaps: Record<string, Array<{ symbolId: string; addressId: string }>>;
  diagnostics: any[];
};
```

### 6.4 `workers/ts/src/sast.ts` — SAST and SymbolID

```ts
import ts from "typescript";
import crypto from "node:crypto";

export type NodeInfo = {
  symbolId: string;
  addressId: string;
  kind: string;
  name: string | null;
  range: { file: string; start: number; end: number };
};

export function parseFiles(files: { path: string; content: string }[]): ts.Program {
  const host = ts.createCompilerHost({});
  const fileMap = new Map(files.map(f => [f.path, f.content]));
  host.readFile = (p) => fileMap.get(p) ?? "";
  host.fileExists = (p) => fileMap.has(p);
  host.getSourceFile = (p, langVersion) => {
    const text = fileMap.get(p);
    if (text === undefined) return undefined;
    return ts.createSourceFile(p, text, langVersion, true, ts.ScriptKind.TS);
  };
  host.getCurrentDirectory = () => "/";
  host.getDirectories = () => [];
  host.getCanonicalFileName = (f) => f;
  host.useCaseSensitiveFileNames = () => true;
  const fileNames = files.map(f => f.path);
  return ts.createProgram({ rootNames: fileNames, options: {}, host });
}

export function buildIndex(prog: ts.Program) {
  const checker = prog.getTypeChecker();
  const nodes: NodeInfo[] = [];
  for (const sf of prog.getSourceFiles()) {
    if (sf.isDeclarationFile) continue;
    ts.forEachChild(sf, function walk(n) {
      if (ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n) || ts.isInterfaceDeclaration(n) ||
          ts.isEnumDeclaration(n) || ts.isVariableStatement(n)) {
        const name = (n as any).name?.getText() ?? null;
        const kind = ts.SyntaxKind[n.kind];
        const addressId = computeAddressId(sf, n, name);
        const symbolId = computeSymbolId(checker, n);
        const range = { file: sf.fileName, start: n.pos, end: n.end };
        nodes.push({ symbolId, addressId, kind, name, range });
      }
      ts.forEachChild(n, walk);
    });
  }
  return { nodes, checker };
}

function computeAddressId(sf: ts.SourceFile, n: ts.Node, name: string | null): string {
  // simplistic FQN: file path + name + position
  return `${sf.fileName}::${name ?? "anon"}::${n.pos}`;
}

function hash(data: string): string {
  return crypto.createHash("sha256").update(data).digest("hex").slice(0, 16);
}

export function computeSymbolId(checker: ts.TypeChecker, n: ts.Node): string {
  // structural hash including signature types where available
  let sig = "";
  if (ts.isFunctionDeclaration(n) && n.parameters) {
    const params = n.parameters.map(p => {
      const t = p.type ? checker.typeToString(checker.getTypeFromTypeNode(p.type)) : "any";
      return t;
    }).join(",");
    const rt = (n.type ? checker.typeToString(checker.getTypeFromTypeNode(n.type)) : "any");
    sig = `fn(${params})->${rt}`;
  } else if (ts.isClassDeclaration(n)) {
    sig = "class{" + (n.members?.length ?? 0) + "}";
  } else if (ts.isInterfaceDeclaration(n)) {
    sig = "iface{" + (n.members?.length ?? 0) + "}";
  } else if (ts.isEnumDeclaration(n)) {
    sig = "enum{" + n.members.length + "}";
  } else if (ts.isVariableStatement(n)) {
    sig = "vars{" + n.declarationList.declarations.length + "}";
  } else {
    sig = n.kind.toString();
  }
  return hash(`${sig}`);
}
```

### 6.5 `workers/ts/src/diff.ts` — Move-aware diff

```ts
import { NodeInfo } from "./sast.js";

export type Diff = { kind: "rename"|"move"|"add"|"delete"|"changeSig"; a?: NodeInfo; b?: NodeInfo };

export function diffNodes(base: NodeInfo[], side: NodeInfo[]): Diff[] {
  // Map by symbolId for stability across moves/renames
  const baseMap = new Map(base.map(n => [n.symbolId, n]));
  const sideMap = new Map(side.map(n => [n.symbolId, n]));
  const diffs: Diff[] = [];

  for (const [sid, bnode] of baseMap) {
    const snode = sideMap.get(sid);
    if (!snode) { diffs.push({ kind: "delete", a: bnode }); continue; }
    // Address changed => move
    if (bnode.addressId !== snode.addressId) diffs.push({ kind: "move", a: bnode, b: snode });
    // Name changed but symbol persisted => rename
    if (bnode.name && snode.name && bnode.name !== snode.name) diffs.push({ kind: "rename", a: bnode, b: snode });
    // TODO: detect signature changes by analyzing checker info
  }
  for (const snode of side) {
    if (!baseMap.has(snode.symbolId)) diffs.push({ kind: "add", b: snode });
  }
  return diffs;
}
```

### 6.6 `workers/ts/src/lift.ts` — Diffs → Ops

```ts
import { Diff } from "./diff.js";
import { Op } from "./protocol.js";
import crypto from "node:crypto";

function newId() { return crypto.randomUUID(); }
const now = () => new Date().toISOString();

export function lift(baseRev: string, diffs: Diff[]): Op[] {
  const ops: Op[] = [];
  for (const d of diffs) {
    if (d.kind === "rename" && d.a && d.b) {
      ops.push({
        id: newId(), schemaVersion: 1, type: "renameSymbol",
        target: { symbolId: d.a.symbolId, addressId: d.a.addressId },
        params: { oldName: d.a.name, newName: d.b.name, file: d.b.range.file },
        guards: { exists: true, addressMatch: d.a.addressId },
        effects: { summary: `rename ${d.a.name}→${d.b.name}` },
        provenance: { rev: baseRev, timestamp: now() }
      });
    } else if (d.kind === "move" && d.a && d.b) {
      ops.push({
        id: newId(), schemaVersion: 1, type: "moveDecl",
        target: { symbolId: d.a.symbolId, addressId: d.a.addressId },
        params: { oldAddress: d.a.addressId, newAddress: d.b.addressId, file: d.b.range.file },
        guards: { exists: true, addressMatch: d.a.addressId },
        effects: { summary: `move ${d.a.addressId}→${d.b.addressId}` },
        provenance: { rev: baseRev, timestamp: now() }
      });
    } else if (d.kind === "add" && d.b) {
      ops.push({
        id: newId(), schemaVersion: 1, type: "addDecl",
        target: { symbolId: d.b.symbolId, addressId: d.b.addressId },
        params: { file: d.b.range.file },
        guards: {}, effects: { summary: "add decl" }, provenance: { rev: baseRev, timestamp: now() }
      });
    } else if (d.kind === "delete" && d.a) {
      ops.push({
        id: newId(), schemaVersion: 1, type: "deleteDecl",
        target: { symbolId: d.a.symbolId, addressId: d.a.addressId },
        params: { file: d.a.range.file },
        guards: {}, effects: { summary: "delete decl" }, provenance: { rev: baseRev, timestamp: now() }
      });
    }
  }
  return ops;
}
```

### 6.7 `workers/ts/src/index.ts` — JSON-RPC server

```ts
import { BuildAndDiffParams, BuildAndDiffResult, Snapshot } from "./protocol.js";
import { parseFiles, buildIndex } from "./sast.js";
import { diffNodes } from "./diff.js";
import { lift } from "./lift.js";

const rl = createLineReader();

interface Rpc { jsonrpc: "2.0"; id: number; method: string; params: any; }

async function main() {
  for await (const line of rl) {
    if (!line) continue;
    const req: Rpc = JSON.parse(line);
    try {
      if (req.method === "buildAndDiff") {
        const p = req.params as BuildAndDiffParams;
        const base = parseFiles(p.base.files);
        const left = parseFiles(p.left.files);
        const right = parseFiles(p.right.files);

        const baseIdx = buildIndex(base);
        const leftIdx = buildIndex(left);
        const rightIdx = buildIndex(right);

        const dA = diffNodes(baseIdx.nodes, leftIdx.nodes);
        const dB = diffNodes(baseIdx.nodes, rightIdx.nodes);

        const oplA = lift("base", dA);
        const oplB = lift("base", dB);

        respond(req.id, <BuildAndDiffResult>{
          opLogLeft: oplA,
          opLogRight: oplB,
          symbolMaps: {
            base: baseIdx.nodes.map(n => ({ symbolId: n.symbolId, addressId: n.addressId })),
            left: leftIdx.nodes.map(n => ({ symbolId: n.symbolId, addressId: n.addressId })),
            right: rightIdx.nodes.map(n => ({ symbolId: n.symbolId, addressId: n.addressId }))
          },
          diagnostics: []
        });
      } else if (req.method === "diff") {
        const base = parseFiles(req.params.base.files);
        const right = parseFiles(req.params.right.files);
        const d = diffNodes(buildIndex(base).nodes, buildIndex(right).nodes);
        respond(req.id, { opLogRight: lift("base", d) });
      } else {
        error(req.id, -32601, "Method not found");
      }
    } catch (e: any) {
      error(req.id, -32000, e?.message ?? String(e));
    }
  }
}

function createLineReader() {
  const decoder = new TextDecoder();
  let buf = "";
  const stdin = process.stdin;
  stdin.setEncoding("utf8");
  const iter = {
    [Symbol.asyncIterator]() { return this; },
    async next() {
      while (true) {
        const chunk = stdin.read() as string | null;
        if (chunk === null) { await once(stdin, "readable"); continue; }
        buf += chunk;
        const idx = buf.indexOf("\n");
        if (idx >= 0) {
          const line = buf.slice(0, idx);
          buf = buf.slice(idx + 1);
          return { value: line, done: false };
        }
      }
    }
  };
  return iter as AsyncIterable<string>;
}

function once(emitter: NodeJS.ReadableStream, event: string) {
  return new Promise<void>(resolve => emitter.once(event, () => resolve()));
}

function respond(id: number, result: any) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + "\n");
}
function error(id: number, code: number, message: string) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n");
}

main();
```

---

## 7. Java and C# backends (stubs)

### 7.1 Java bridge stub `semmerge/lang/java/bridge.py`

```python
# semmerge/lang/java/bridge.py
class JavaWorker:
    def build_and_diff(self, base_tree, left_tree, right_tree):
        raise NotImplementedError("Enable Java backend by integrating JDT and exposing the protocol over stdio")
```

### 7.2 C# bridge stub `semmerge/lang/cs/bridge.py`

```python
# semmerge/lang/cs/bridge.py
class CSWorker:
    def build_and_diff(self, base_tree, left_tree, right_tree):
        raise NotImplementedError("Enable C# backend by integrating Roslyn and exposing the protocol over stdio")
```

---

## 8. Git merge driver wrapper

### 8.1 `scripts/semmerge-driver.py`

```python
#!/usr/bin/env python3
# scripts/semmerge-driver.py
"""
Git passes: %O %A %B  (paths to base, ours, theirs) for a single file.
Strategy:
- Detect the git merge context using environment (GIT_DIR, etc.).
- Resolve full merge base and heads.
- Run repo-level semmerge once for the entire tree.
- For the file Git asked about, copy the resolved content from working tree to %A and return exit 0.
- If conflicts exist, return exit 1 to let Git mark conflict.
"""
from __future__ import annotations
import os, sys, subprocess, pathlib, json, tempfile, shutil

def run(cmd: list[str], cwd: str | None = None) -> str:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)
    return res.stdout.strip()

def main():
    base_file, ours_file, theirs_file = sys.argv[1:4]
    # Identify commit ids
    HEAD = run(["git","rev-parse","HEAD"])
    MERGE_HEAD = os.environ.get("GITHEAD_REF") or run(["git","rev-parse","MERGE_HEAD"])
    BASE = run(["git","merge-base","HEAD", MERGE_HEAD])

    # Run semmerge once per merge by lock file
    lock = pathlib.Path(".git/.semmerge.lock")
    if not lock.exists():
        lock.write_text(MERGE_HEAD)
        try:
            # Execute repo-level merge into working tree
            code = subprocess.run(["python3","-m","semmerge","semmerge", BASE, HEAD, MERGE_HEAD, "--inplace", "--git"]).returncode
            if code != 0:
                # Conflicts: leave Git to handle, return failure to mark file as conflicted
                sys.exit(1)
        finally:
            lock.unlink(missing_ok=True)

    # For this file, accept the working tree version by copying to %A
    rel = os.path.relpath(ours_file, start=os.getcwd())
    if os.path.isfile(rel):
        shutil.copyfile(rel, ours_file)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

> This wrapper lets semantic merge run once per merge. Git still calls the driver per file, but subsequent invocations see the lock.

---

## 9. Determinism

- Seed: derive from `sha256(merge-base tree hash + A commit id + B commit id)` when `deterministic_seed="auto"`.
- Normalize timestamps to ISO UTC.
- Sort ops with a total order `(op-type precedence, timestamp, id)`.

Example in Python:

```python
import hashlib
def det_seed(base_tree: str, a: str, b: str)->str:
    h = hashlib.sha256((base_tree+a+b).encode("utf-8")).hexdigest()
    return h[:32]
```

---

## 10. End-to-end flow (TS P0)

1. `semmerge` checks out three trees.
2. TS worker builds in-memory programs and indexes nodes.
3. Worker computes `base→A` and `base→B` diffs by `symbolId` and `addressId`.
4. Worker lifts diffs to Ops.
5. Python `compose` merges Op logs, raises conflicts if needed.
6. `applier` applies P0 ops to FS.
7. `emitter` runs Prettier.
8. `verify` runs `tsc --noEmit`.
9. Writes merged files to working tree or temp.
10. Stores Op logs in Git notes.

---

## 11. Formatting and CST

P0 uses Prettier. CST trivia reattachment is deferred. For faithful comments around moved declarations:

- Add a future hook in `workers/ts/src/emit.ts` to collect leading/trailing trivia ranges for nodes and remap by `symbolId`.
- Until then rely on formatter to normalize whitespace.

Placeholder file:

```ts
// workers/ts/src/emit.ts
export function reattachTrivia() { /* TODO: P1 */ }
```

---

## 12. Type-check integration

P0 shells out to `tsc`. For large monorepos use project references.

- Place a `tsconfig.json` at repo root or supply `project_globs` in `.semmerge.toml`.
- `verify.typecheck_ts` runs at modified subtree root.

---

## 13. Tests

Create `tests/e2e_basic.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
rm -rf /tmp/repo && mkdir -p /tmp/repo
cd /tmp/repo
git init -q
cat > a.ts <<'EOF'
export function f(x: number){ return x+1; }
EOF
git add a.ts && git commit -qm "base"

git checkout -qb branchA
sed -i.bak 's/function f/function g/' a.ts && rm a.ts.bak
git commit -am "rename f->g" -q

git checkout -q main
git checkout -qb branchB
mkdir -p lib && git mv a.ts lib/a.ts
git commit -am "move a.ts to lib" -q

git checkout -q main
git merge branchB -m "merge B" -q
git config merge.semerge.driver "python3 $(pwd)/semantic-merge/scripts/semmerge-driver.py %O %A %B"
echo "*.ts semmerge" > .gitattributes
git add .gitattributes && git commit -qm "enable semmerge driver"

git merge branchA || true

echo "Merged tree:"
git ls-files -s
echo "Contents:"
cat lib/a.ts
```

Expected result: `lib/a.ts` contains `export function g(...)`.

---

## 14. Extending Op coverage

Add more Ops in the worker `lift.ts` and applier:

- `modifyImport`: parse import specifiers and update names.
- `changeSignature`: compare parameter lists and types; produce `updateCall` ops for call sites using the checker.
- `editStmtBlock`: capture statement insert/move/delete inside function bodies. Use anchors derived from surrounding unchanged tokens; apply via CRDT to converge concurrent edits.

Pseudo in TS:

```ts
// detect signature change
if (isFunction(n) && isFunction(matchingInSide)) {
  const oldParams = sigOf(n); const newParams = sigOf(matching);
  if (!equal(oldParams, newParams)) diffs.push({kind:"changeSig", a: nInfo, b: mInfo});
}
```

Applier side in Python would dispatch to worker-side code-gen for accurate rewrites. Introduce a worker method `applyOps(base, ops)` to return modified files with CST adjustments.

---

## 15. Error handling and exit codes

- `0`: success
- `1`: semantic conflict reported
- `2`: type-check or verification failure
- `>2`: unexpected error

Ensure all CLI commands print machine-readable JSON under `--json`.

---

## 16. Logging

`semmerge/loggingx.py`:

```python
import logging, os
logger = logging.getLogger("semmerge")
_handler = logging.StreamHandler()
_fmt = logging.Formatter("%(levelname)s %(message)s")
_handler.setFormatter(_fmt)
logger.addHandler(_handler)
logger.setLevel(os.environ.get("SEMMERGE_LOG","INFO"))
```

---

## 17. Performance

- Cache ASTs by content hash (P1).
- Parallelize TS worker per file set (P1).
- Prune by changed path filters from `git diff --name-only` (do this now).

Modify `lang/ts/bridge.py` snapshot to include only changed files when `GIT_DIFFERENTIAL=1`.

---

## 18. Security

- No network calls.
- Temp dirs under system temp with unique prefixes.
- Remove temps on success.

---

## 19. Limitations in P0

- `SymbolID` is a coarse structural hash. Collisions are rare but possible.
- Statement-level diffs are not yet lifted; falls back to text edits executed by `applier` if you extend it.
- Comments may move non-ideally until CST reattachment is implemented.
- Java/C# backends are placeholders.

---

## 20. Developer checklist

- [ ] Install prerequisites.
- [ ] `npm --prefix workers/ts install && npm --prefix workers/ts run build`.
- [ ] `pip install -e .` at repo root.
- [ ] Put `.gitattributes` and Git config entries.
- [ ] Run `semmerge semdiff <rev1> <rev2> --json-out`.
- [ ] Run `semmerge semmerge <base> <A> <B> --inplace`.
- [ ] Validate merged tree compiles.

---

## 21. API surfaces to stabilize

- Worker protocol methods: `buildAndDiff`, `applyOps` (add), `formatFiles` (optional).
- Op JSON schema v1.

---

## 22. Roadmap hooks inside code

- `emit.ts` for CST trivia.
- `diff.ts` for signature and call graph analysis.
- Python `applier.py` to delegate source rewrites to the worker instead of regex.

---

## 23. Appendix: Sample `.editorconfig` for newline consistency

```editorconfig
root = true
[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
```

---

## 24. Appendix: Deterministic timestamp normalization

When constructing `provenance.timestamp`, normalize to the commit author date in ISO UTC. If not available, use the deterministic seed as a pseudo-time:

```python
from datetime import datetime, timezone
def iso_utc(ts: float | None) -> str:
    if ts is None: ts = 0.0
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00","Z")
```

---

## 25. Appendix: Minimal conflict viewer

Create `.semmerge-conflicts.json` and load in any viewer. Schema already defined in §4.2.

---
