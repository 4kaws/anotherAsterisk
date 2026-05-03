"""Shared test fixtures."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    """A minimal but valid wiki vault in a temp directory."""
    (vault := tmp_path / "wiki").mkdir()

    (vault / "status.md").write_text(textwrap.dedent("""\
        # Status
        - **task**: test
        - **step**: 0
        - **url**: about:blank
    """), encoding="utf-8")

    (vault / "index.md").write_text(textwrap.dedent("""\
        # Index

        | Slug | Description | Status |
        |------|-------------|--------|
        | _(none yet)_ | | |
    """), encoding="utf-8")

    return vault
