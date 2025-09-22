import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from semmerge import __main__ as cli


class DummyWorker:
    def __init__(self, close_calls: list[bool]) -> None:
        self._close_calls = close_calls

    def build_and_diff(self, base_tree, left_tree, right_tree):  # noqa: ANN001
        return ["left"], ["right"], {}

    def close(self) -> None:
        self._close_calls.append(True)


def test_semerge_propagates_exceptions_before_apply_ops(monkeypatch, tmp_path):
    sentinel = RuntimeError("compose failure")
    close_calls: list[bool] = []

    monkeypatch.setattr(cli, "TSWorker", lambda: DummyWorker(close_calls))

    def fake_checkout_tree_to_temp(rev: str) -> Path:
        path = tmp_path / rev
        path.mkdir(exist_ok=True)
        return path

    monkeypatch.setattr(cli, "checkout_tree_to_temp", fake_checkout_tree_to_temp)

    def raise_on_compose(*args, **kwargs):  # noqa: ANN002, ANN003
        raise sentinel

    monkeypatch.setattr(cli, "compose_oplogs", raise_on_compose)

    with pytest.raises(RuntimeError) as excinfo:
        cli.semmerge.callback("base", "a", "b", inplace=False, git=False)

    assert excinfo.value is sentinel
    assert close_calls == [True]
