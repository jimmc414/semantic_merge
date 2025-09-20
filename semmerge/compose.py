"""Composition of semantic operation logs."""
from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Tuple

from .conflict import Conflict, conflict_divergent_rename
from .ops import Op, Target


def compose_oplogs(delta_a: List[Op], delta_b: List[Op]) -> Tuple[List[Op], List[Conflict]]:
    """Compose two lists of operations into a single deterministic sequence."""

    precedence = _precedence()

    def sort_key(op: Op) -> tuple[int, str, str]:
        timestamp = str(op.provenance.get("timestamp", "1970-01-01T00:00:00Z"))
        return (precedence.get(op.type, 99), timestamp, op.id)

    ops_a = sorted(delta_a, key=sort_key)
    ops_b = sorted(delta_b, key=sort_key)

    out: List[Op] = []
    conflicts: List[Conflict] = []

    idx_a = idx_b = 0
    rename_chain: Dict[str, str] = {}
    move_chain: Dict[str, str] = {}

    def materialize(op: Op) -> None:
        cloned = _clone_op(op)
        symbol_id = cloned.target.symbolId
        if symbol_id in move_chain:
            new_addr = move_chain[symbol_id]
            if cloned.type == "moveDecl":
                cloned.params["newAddress"] = new_addr
            cloned.target = Target(symbol_id=symbol_id, addressId=new_addr)
        if symbol_id in rename_chain and cloned.type != "renameSymbol":
            cloned.params = {**cloned.params, "renameContext": rename_chain[symbol_id]}
        out.append(cloned)

    while idx_a < len(ops_a) or idx_b < len(ops_b):
        use_a = False
        if idx_a < len(ops_a):
            if idx_b >= len(ops_b) or sort_key(ops_a[idx_a]) <= sort_key(ops_b[idx_b]):
                use_a = True

        if use_a:
            op_a = ops_a[idx_a]
            op_b = ops_b[idx_b] if idx_b < len(ops_b) else None
            if (
                op_a.type == "renameSymbol"
                and op_b is not None
                and op_b.type == "renameSymbol"
                and op_a.target.symbolId == op_b.target.symbolId
            ):
                if op_a.params.get("newName") != op_b.params.get("newName"):
                    conflicts.append(conflict_divergent_rename(op_a, op_b))
                    idx_a += 1
                    idx_b += 1
                    continue
            if op_a.type == "renameSymbol":
                rename_chain[op_a.target.symbolId] = str(op_a.params.get("newName"))
            if op_a.type == "moveDecl":
                move_chain[op_a.target.symbolId] = str(op_a.params.get("newAddress"))
            materialize(op_a)
            idx_a += 1
        else:
            op_b = ops_b[idx_b]
            op_a = ops_a[idx_a] if idx_a < len(ops_a) else None
            if (
                op_b.type == "renameSymbol"
                and op_a is not None
                and op_a.type == "renameSymbol"
                and op_a.target.symbolId == op_b.target.symbolId
            ):
                if op_a.params.get("newName") != op_b.params.get("newName"):
                    conflicts.append(conflict_divergent_rename(op_a, op_b))
                    idx_a += 1
                    idx_b += 1
                    continue
            if op_b.type == "renameSymbol":
                rename_chain[op_b.target.symbolId] = str(op_b.params.get("newName"))
            if op_b.type == "moveDecl":
                move_chain[op_b.target.symbolId] = str(op_b.params.get("newAddress"))
            materialize(op_b)
            idx_b += 1

    return out, conflicts


def _clone_op(op: Op) -> Op:
    return Op(
        id=op.id,
        schemaVersion=op.schemaVersion,
        type=op.type,
        target=Target(symbolId=op.target.symbolId, addressId=op.target.addressId),
        params=deepcopy(op.params),
        guards=deepcopy(op.guards),
        effects=deepcopy(op.effects),
        provenance=deepcopy(op.provenance),
    )


def _precedence() -> Dict[str, int]:
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
        "modifyNamespace": 70,
    }
