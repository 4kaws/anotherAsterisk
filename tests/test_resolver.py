"""Unit tests for WikilinkResolver and extract_wikilinks."""
from __future__ import annotations

from pathlib import Path

import pytest

from asterisk.wiki.resolver import WikilinkResolver, extract_wikilinks


def _make_md(vault: Path, rel: str, content: str = "# test") -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestExtractWikilinks:
    def test_simple_link(self):
        assert extract_wikilinks("See [[foo/bar]]") == ["foo/bar"]

    def test_display_text_stripped(self):
        assert extract_wikilinks("[[foo/bar|Display]]") == ["foo/bar"]

    def test_multiple_links(self):
        result = extract_wikilinks("[[a]] and [[b/c]]")
        assert result == ["a", "b/c"]

    def test_no_links(self):
        assert extract_wikilinks("No links here.") == []

    def test_whitespace_trimmed(self):
        assert extract_wikilinks("[[ foo/bar ]]") == ["foo/bar"]


class TestWikilinkResolver:
    def test_exact_match(self, vault: Path):
        _make_md(vault, "steps/task/step-001.md")
        r = WikilinkResolver(vault)
        assert r.resolve("steps/task/step-001") == vault / "steps/task/step-001.md"

    def test_exact_match_with_extension(self, vault: Path):
        _make_md(vault, "observations/login.md")
        r = WikilinkResolver(vault)
        assert r.resolve("observations/login.md") == vault / "observations/login.md"

    def test_case_insensitive_match(self, vault: Path):
        _make_md(vault, "steps/Task/step-001.md")
        r = WikilinkResolver(vault)
        result = r.resolve("STEPS/TASK/STEP-001")
        assert result is not None
        assert result.name == "step-001.md"

    def test_basename_only_match(self, vault: Path):
        _make_md(vault, "steps/buy-milk/step-001.md")
        r = WikilinkResolver(vault)
        assert r.resolve("step-001") == vault / "steps/buy-milk/step-001.md"

    def test_unresolved_returns_none(self, vault: Path):
        r = WikilinkResolver(vault)
        assert r.resolve("nonexistent/page") is None

    def test_refresh_picks_up_new_files(self, vault: Path):
        r = WikilinkResolver(vault)
        assert r.resolve("fresh") is None

        _make_md(vault, "fresh.md")
        r.refresh()
        assert r.resolve("fresh") == vault / "fresh.md"

    def test_resolve_all_partial(self, vault: Path):
        _make_md(vault, "a.md")
        r = WikilinkResolver(vault)
        result = r.resolve_all(["a", "missing"])
        assert "a" in result
        assert "missing" not in result

    def test_ambiguous_basename_returns_first(self, vault: Path, caplog):
        _make_md(vault, "steps/task-a/step-001.md")
        _make_md(vault, "steps/task-b/step-001.md")
        r = WikilinkResolver(vault)
        with caplog.at_level("WARNING"):
            result = r.resolve("step-001")
        assert result is not None  # returns first match, doesn't crash
        assert "Ambiguous" in caplog.text
