"""Unit tests for WikiWriter and StepSchema."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from asterisk.wiki.writer import WikiWriter, WikiWriteError, StepSchema


VALID_STEP = {
    "step": 1,
    "task": "buy milk",
    "action_taken": "clicked Add to Cart",
    "element": "#add-to-cart",
    "url": "https://store.example.com",
    "outcome": "success",
    "next_hint": "proceed to checkout",
    "related": [],
    "timestamp": "2024-01-01T00:00:00+00:00",
}


class TestStepSchema:
    def test_valid_outcomes(self):
        for outcome in ("success", "failure", "pending"):
            s = StepSchema(**{**VALID_STEP, "outcome": outcome})
            assert s.outcome == outcome

    def test_invalid_outcome_raises(self):
        with pytest.raises(Exception):
            StepSchema(**{**VALID_STEP, "outcome": "unknown"})

    def test_optional_element(self):
        data = {**VALID_STEP, "element": None}
        s = StepSchema(**data)
        assert s.element is None

    def test_related_defaults_empty(self):
        data = {k: v for k, v in VALID_STEP.items() if k != "related"}
        s = StepSchema(**data)
        assert s.related == []


class TestWikiWriter:
    def test_write_step_creates_file(self, vault: Path):
        w = WikiWriter(str(vault))
        path = w.write_step("buy-milk", 1, dict(VALID_STEP))
        assert path.exists()
        assert path.name == "step-001.md"

    def test_write_step_content(self, vault: Path):
        w = WikiWriter(str(vault))
        path = w.write_step("buy-milk", 1, dict(VALID_STEP))
        content = path.read_text()
        assert "Step 001" in content
        assert "buy milk" in content
        assert "success" in content
        # Raw JSON block is present and parseable
        assert "```json" in content
        json_start = content.index("```json") + 7
        json_end = content.index("```", json_start)
        parsed = json.loads(content[json_start:json_end])
        assert parsed["step"] == 1

    def test_write_step_invalid_data_raises(self, vault: Path):
        w = WikiWriter(str(vault))
        bad = {**VALID_STEP, "outcome": "exploded"}
        with pytest.raises(WikiWriteError):
            w.write_step("buy-milk", 1, bad)

    def test_write_step_auto_timestamp(self, vault: Path):
        w = WikiWriter(str(vault))
        data = {k: v for k, v in VALID_STEP.items() if k != "timestamp"}
        data["timestamp"] = ""
        path = w.write_step("buy-milk", 1, data)
        assert path.exists()

    def test_write_step_saves_screenshot(self, vault: Path):
        w = WikiWriter(str(vault))
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        w.write_step("buy-milk", 1, dict(VALID_STEP), screenshot_bytes=fake_png)
        png_path = vault / "steps/buy-milk/step-001.png"
        assert png_path.exists()
        assert png_path.read_bytes() == fake_png

    def test_write_step_with_related_links(self, vault: Path):
        w = WikiWriter(str(vault))
        data = {**VALID_STEP, "related": ["[[steps/buy-milk/step-000]]", "[[observations/login]]"]}
        path = w.write_step("buy-milk", 1, data)
        content = path.read_text()
        assert "[[steps/buy-milk/step-000]]" in content

    def test_update_status(self, vault: Path):
        w = WikiWriter(str(vault))
        w.update_status(
            task="buy milk",
            step=3,
            url="https://example.com/cart",
            progress="3/10",
            last_action="clicked add to cart",
            next_hint="proceed to checkout",
        )
        content = (vault / "status.md").read_text()
        assert "buy milk" in content
        assert "step**: 3" in content
        assert "3/10" in content

    def test_write_observation(self, vault: Path):
        w = WikiWriter(str(vault))
        path = w.write_observation("login-selectors", "# Login\n\nid=email and id=password")
        assert path.exists()
        assert path.parent.name == "observations"
        assert "id=email" in path.read_text()

    def test_update_index_adds_entry(self, vault: Path):
        w = WikiWriter(str(vault))
        w.update_index("buy-milk", "Buy milk from store", "active")
        content = (vault / "index.md").read_text()
        assert "buy-milk" in content
        assert "Buy milk from store" in content

    def test_update_index_idempotent(self, vault: Path):
        w = WikiWriter(str(vault))
        w.update_index("buy-milk", "Buy milk", "active")
        w.update_index("buy-milk", "Buy milk", "active")  # second call should be no-op
        content = (vault / "index.md").read_text()
        assert content.count("buy-milk") == 1

    def test_step_numbering_pads_to_three_digits(self, vault: Path):
        w = WikiWriter(str(vault))
        path = w.write_step("task", 7, dict(VALID_STEP))
        assert path.name == "step-007.md"
