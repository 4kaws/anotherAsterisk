"""Unit tests for ObservationExtractor."""
from __future__ import annotations

from pathlib import Path

from asterisk.wiki.observation_extractor import ObservationExtractor


class TestObservationExtractor:
    def test_no_observation_returns_none(self, vault: Path):
        ext = ObservationExtractor(vault)
        assert ext.extract_and_save({"action": {}, "wiki_update": {}, "status_update": {}}) is None

    def test_empty_observation_returns_none(self, vault: Path):
        ext = ObservationExtractor(vault)
        assert ext.extract_and_save({"observation": {}}) is None

    def test_empty_content_returns_none(self, vault: Path):
        ext = ObservationExtractor(vault)
        assert ext.extract_and_save({"observation": {"slug": "x", "title": "X", "content": ""}}) is None

    def test_saves_new_observation(self, vault: Path):
        ext = ObservationExtractor(vault)
        slug = ext.extract_and_save({
            "observation": {
                "slug": "login-selectors",
                "title": "Login selectors",
                "content": "id=email and id=password",
            }
        })
        assert slug == "login-selectors"
        obs_file = vault / "observations/login-selectors.md"
        assert obs_file.exists()
        assert "id=email" in obs_file.read_text()

    def test_appends_to_existing_observation(self, vault: Path):
        ext = ObservationExtractor(vault)
        ext.extract_and_save({
            "observation": {"slug": "checkout", "title": "Checkout", "content": "First fact."}
        })
        ext.extract_and_save({
            "observation": {"slug": "checkout", "title": "Checkout", "content": "Second fact."}
        })
        content = (vault / "observations/checkout.md").read_text()
        assert "First fact." in content
        assert "Second fact." in content
        assert "---" in content  # separator preserved

    def test_slug_derived_from_title_when_absent(self, vault: Path):
        ext = ObservationExtractor(vault)
        slug = ext.extract_and_save({
            "observation": {"title": "Login Page Selectors", "content": "id=email"}
        })
        assert slug == "login-page-selectors"
        assert (vault / f"observations/{slug}.md").exists()

    def test_slug_derived_from_content_when_no_title(self, vault: Path):
        ext = ObservationExtractor(vault)
        slug = ext.extract_and_save({
            "observation": {"content": "The checkout button is always blue"}
        })
        assert slug is not None
        assert (vault / f"observations/{slug}.md").exists()

    def test_non_dict_observation_returns_none(self, vault: Path):
        ext = ObservationExtractor(vault)
        assert ext.extract_and_save({"observation": "just a string"}) is None

    def test_title_used_in_heading(self, vault: Path):
        ext = ObservationExtractor(vault)
        ext.extract_and_save({
            "observation": {"slug": "my-obs", "title": "My Observation", "content": "detail"}
        })
        content = (vault / "observations/my-obs.md").read_text()
        assert "# My Observation" in content
