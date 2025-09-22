"""Configuration loader for :mod:`semmerge`."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable
import importlib
import importlib.util
import pathlib
from types import ModuleType

tomllib: ModuleType
if importlib.util.find_spec("tomllib") is not None:  # pragma: no cover - depends on runtime Python version
    tomllib = importlib.import_module("tomllib")
else:  # pragma: no cover - exercised on Python < 3.11
    tomllib = importlib.import_module("tomli")


@dataclass
class CoreConfig:
    """Core engine settings."""

    deterministic_seed: str = "auto"
    memory_cap_mb: int = 4096
    formatter: str | None = None


@dataclass
class LanguageConfig:
    """Language specific configuration."""

    enabled: bool = False
    project_globs: list[str] = field(default_factory=list)
    formatter_cmd: list[str] | None = None


@dataclass
class CiConfig:
    """Continuous integration policy flags."""

    require_typecheck: bool = True
    require_tests: bool = False


@dataclass
class Config:
    """Complete configuration tree."""

    root: pathlib.Path
    core: CoreConfig = field(default_factory=CoreConfig)
    languages: Dict[str, LanguageConfig] = field(default_factory=dict)
    ci: CiConfig = field(default_factory=CiConfig)


def load_config(start: pathlib.Path | None = None) -> Config:
    """Load ``.semmerge.toml`` from *start* or its parents.

    If no configuration file is present a :class:`Config` with defaults is
    returned. The ``root`` attribute will reference the directory where the
    configuration file was found, or ``start``/``cwd`` when absent.
    """

    if start is None:
        start = pathlib.Path.cwd()
    cfg_path = _find_config(start)
    root = cfg_path.parent if cfg_path else start
    config = Config(root=root)
    if not cfg_path:
        return config

    with cfg_path.open("rb") as fh:
        data = tomllib.load(fh)

    core_data = data.get("core", {})
    config.core = CoreConfig(
        deterministic_seed=str(core_data.get("deterministic_seed", config.core.deterministic_seed)),
        memory_cap_mb=int(core_data.get("memory_cap_mb", config.core.memory_cap_mb)),
        formatter=core_data.get("formatter", config.core.formatter),
    )

    languages: Dict[str, LanguageConfig] = {}
    for lang, ldata in data.get("languages", {}).items():
        languages[lang] = LanguageConfig(
            enabled=bool(ldata.get("enabled", False)),
            project_globs=list(_as_str_seq(ldata.get("project_globs", []))),
            formatter_cmd=list(_as_str_seq(ldata.get("formatter_cmd", []))) or None,
        )
    config.languages = languages

    ci_data = data.get("ci", {})
    config.ci = CiConfig(
        require_typecheck=bool(ci_data.get("require_typecheck", config.ci.require_typecheck)),
        require_tests=bool(ci_data.get("require_tests", config.ci.require_tests)),
    )

    return config


def _find_config(start: pathlib.Path) -> pathlib.Path | None:
    """Return the path to ``.semmerge.toml`` searching upwards from ``start``."""

    for directory in [start, *start.parents]:
        candidate = directory / ".semmerge.toml"
        if candidate.is_file():
            return candidate
    return None


def _as_str_seq(value: Any) -> Iterable[str]:
    if isinstance(value, (list, tuple)):
        for item in value:
            if item is not None:
                yield str(item)
    elif value:
        yield str(value)
