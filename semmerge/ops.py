"""Operation definitions used by the semantic merge engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Mapping
import uuid

import orjson

OpType = Literal[
    "renameSymbol",
    "moveDecl",
    "addDecl",
    "deleteDecl",
    "changeSignature",
    "reorderParams",
    "addParam",
    "removeParam",
    "extractMethod",
    "inlineMethod",
    "updateCall",
    "editStmtBlock",
    "modifyImport",
    "reorderImports",
    "moveFile",
    "renameFile",
    "modifyNamespace",
]


@dataclass
class Target:
    """Target declaration for an operation."""

    symbolId: str
    addressId: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {"symbolId": self.symbolId, "addressId": self.addressId}


@dataclass
class Op:
    """Semantic change captured as an operation."""

    id: str
    schemaVersion: int
    type: OpType
    target: Target
    params: Dict[str, Any]
    guards: Dict[str, Any]
    effects: Dict[str, Any]
    provenance: Dict[str, Any]

    @staticmethod
    def new(
        op_type: OpType,
        target: Target,
        params: Dict[str, Any] | None = None,
        guards: Dict[str, Any] | None = None,
        effects: Dict[str, Any] | None = None,
        provenance: Dict[str, Any] | None = None,
    ) -> "Op":
        """Create a new :class:`Op` with sensible defaults."""

        return Op(
            id=str(uuid.uuid4()),
            schemaVersion=1,
            type=op_type,
            target=target,
            params=params or {},
            guards=guards or {},
            effects=effects or {},
            provenance=provenance or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "schemaVersion": self.schemaVersion,
            "type": self.type,
            "target": self.target.to_dict(),
            "params": self.params,
            "guards": self.guards,
            "effects": self.effects,
            "provenance": self.provenance,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Op":
        return Op(
            id=str(data["id"]),
            schemaVersion=int(data.get("schemaVersion", 1)),
            type=data["type"],
            target=Target(**data["target"]),
            params=dict(data.get("params", {})),
            guards=dict(data.get("guards", {})),
            effects=dict(data.get("effects", {})),
            provenance=dict(data.get("provenance", {})),
        )

    def pretty(self) -> str:
        return f"{self.type} {self.target.symbolId} {self.params}"


@dataclass
class OpLog:
    """Collection of operations."""

    ops: List[Op] = field(default_factory=list)

    def to_json(self) -> str:
        return orjson.dumps([o.to_dict() for o in self.ops]).decode()

    @staticmethod
    def from_json(data: str) -> "OpLog":
        payload = orjson.loads(data)
        return OpLog([Op.from_dict(item) for item in payload])

    def extend(self, ops: Iterable[Op]) -> None:
        self.ops.extend(ops)
