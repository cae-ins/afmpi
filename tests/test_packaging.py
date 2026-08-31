"""Consistency checks between packaging metadata and the runtime package (PLAN.md §14.12)."""

from __future__ import annotations

import re
from pathlib import Path

import afmpi

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pyproject_version() -> str:
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert match is not None, "pyproject.toml has no top-level version field"
    return match.group(1)


def test_version_matches_pyproject_toml() -> None:
    assert afmpi.__version__ == _pyproject_version()
