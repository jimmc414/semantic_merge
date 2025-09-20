"""Typed structures for communicating with the TypeScript worker."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProgramSnapshot:
    files: List[Dict[str, str]]
    project: Optional[str] = None


@dataclass
class BuildAndDiffResult:
    opLogLeft: List[Dict[str, Any]]
    opLogRight: List[Dict[str, Any]]
    symbolMaps: Dict[str, Any]
    diagnostics: List[Dict[str, Any]]
