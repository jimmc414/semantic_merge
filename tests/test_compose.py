import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from semmerge.compose import compose_oplogs
from semmerge.ops import Op, Target


def test_compose_oplogs_handles_move_decl_without_errors():
    move_op = Op.new(
        op_type="moveDecl",
        target=Target(symbolId="symbol-123", addressId="old-address"),
        params={"newAddress": "new-address"},
    )

    composed_ops, conflicts = compose_oplogs([move_op], [])

    assert conflicts == []
    assert len(composed_ops) == 1
    composed_move = composed_ops[0]
    assert composed_move.type == "moveDecl"
    assert composed_move.target.symbolId == "symbol-123"
    assert composed_move.target.addressId == "new-address"
    assert composed_move.params["newAddress"] == "new-address"
