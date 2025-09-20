"""Very small RGA-style list CRDT implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Key:
    anchor: str
    t: int
    author: str
    opid: str


@dataclass
class Elem:
    key: Key
    value: str
    tombstone: bool = False


class RGA:
    """A minimal replicated growable array variant used for ordering."""

    def __init__(self) -> None:
        self.list: List[Elem] = []

    def insert(self, key: Key, value: str) -> None:
        idx = self._find_insert_index(key)
        self.list.insert(idx, Elem(key, value))

    def move(self, value: str, key: Key) -> None:
        for i, elem in enumerate(self.list):
            if not elem.tombstone and elem.value == value:
                self.list.pop(i)
                break
        self.insert(key, value)

    def delete(self, value: str) -> None:
        for elem in self.list:
            if elem.value == value:
                elem.tombstone = True

    def materialize(self) -> List[str]:
        return [elem.value for elem in self.list if not elem.tombstone]

    def _find_insert_index(self, key: Key) -> int:
        for i, elem in enumerate(self.list):
            if (key.anchor, key.t, key.author, key.opid) < (
                elem.key.anchor,
                elem.key.t,
                elem.key.author,
                elem.key.opid,
            ):
                return i
        return len(self.list)
