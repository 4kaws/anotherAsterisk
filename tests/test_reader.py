"""Unit tests for WikiReader."""
from __future__ import annotations

import textwrap
from pathlib import Path

from asterisk.wiki.reader import WikiReader


def _write(vault: Path, rel: str, content: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


STEP_CONTENT = textwrap.dedent("""\
    # Step 001 — buy milk

    **Outcome**: success

    ## Related

    - [[observations/checkout-flow]]
    - [[steps/buy-milk/step-000]]

    ## Raw Data

    ```json
    {"step": 1, "task": "buy milk", "outcome": "success"}
    ```
""")


class TestWikiReader:
    def test_always_loads_status_and_index(self, vault: Path):
        r = WikiReader(str(vault))
        ctx = r.load_context("buy-milk", 0)
        assert "status.md" in ctx
        assert "index.md" in ctx

    def test_step_zero_loads_only_anchor_files(self, vault: Path):
        r = WikiReader(str(vault))
        ctx = r.load_context("buy-milk", 0)
        assert len(ctx) == 2  # just status.md and index.md

    def test_loads_previous_step_file(self, vault: Path):
        _write(vault, "steps/buy-milk/step-001.md", STEP_CONTENT)
        r = WikiReader(str(vault))
        ctx = r.load_context("buy-milk", 1)
        assert "steps/buy-milk/step-001.md" in ctx

    def test_follows_related_wikilinks(self, vault: Path):
        _write(vault, "steps/buy-milk/step-001.md", STEP_CONTENT)
        _write(vault, "observations/checkout-flow.md", "# Checkout flow\n\nPay with card.")
        r = WikiReader(str(vault))
        ctx = r.load_context("buy-milk", 1)
        assert "observations/checkout-flow.md" in ctx
        assert "Pay with card" in ctx["observations/checkout-flow.md"]

    def test_missing_step_file_does_not_crash(self, vault: Path):
        r = WikiReader(str(vault))
        ctx = r.load_context("nonexistent-task", 5)
        assert "status.md" in ctx  # anchor files still loaded

    def test_broken_wikilink_does_not_crash(self, vault: Path):
        step = "## Related\n\n- [[observations/ghost]]\n"
        _write(vault, "steps/t/step-001.md", step)
        r = WikiReader(str(vault))
        ctx = r.load_context("t", 1)
        assert "observations/ghost.md" not in ctx  # not loaded, but no crash

    def test_load_observation_by_slug(self, vault: Path):
        _write(vault, "observations/login-page.md", "# Login\n\nid=email")
        r = WikiReader(str(vault))
        content = r.load_observation("login-page")
        assert content is not None
        assert "id=email" in content

    def test_load_observation_missing_returns_none(self, vault: Path):
        r = WikiReader(str(vault))
        assert r.load_observation("ghost") is None

    def test_no_duplicate_loading(self, vault: Path):
        obs_content = "# Obs\n\nSome reusable fact."
        _write(vault, "observations/obs.md", obs_content)
        step = "## Related\n\n- [[observations/obs]]\n- [[observations/obs]]\n"
        _write(vault, "steps/t/step-001.md", step)
        r = WikiReader(str(vault))
        ctx = r.load_context("t", 1)
        # Appears exactly once even though linked twice
        assert list(ctx.keys()).count("observations/obs.md") == 1
