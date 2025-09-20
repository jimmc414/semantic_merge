"""Conflict modelling helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .ops import Op


@dataclass
class Conflict:
    id: str
    category: str
    symbolId: str
    addressIds: Dict[str, Any]
    opA: Dict[str, Any]
    opB: Dict[str, Any]
    minimalSlice: Dict[str, Any]
    suggestions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "symbolId": self.symbolId,
            "addressIds": self.addressIds,
            "opA": self.opA,
            "opB": self.opB,
            "minimalSlice": self.minimalSlice,
            "suggestions": self.suggestions,
        }


def conflict_divergent_rename(op_a: Op, op_b: Op) -> Conflict:
    """Create a DivergentRename conflict payload."""

    return Conflict(
        id=f"conf-{op_a.id[:8]}-{op_b.id[:8]}",
        category="DivergentRename",
        symbolId=op_a.target.symbolId,
        addressIds={"A": op_a.target.addressId, "B": op_b.target.addressId, "base": None},
        opA=op_a.to_dict(),
        opB=op_b.to_dict(),
        minimalSlice={"path": "", "start": 0, "end": 0, "code": ""},
        suggestions=[
            {"id": "keepA", "label": f"Rename to {op_a.params.get('newName')}", "ops": [op_a.id]},
            {"id": "keepB", "label": f"Rename to {op_b.params.get('newName')}", "ops": [op_b.id]},
        ],
    )
