"""Unit tests for the config loader."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from asterisk.config import load_config, AsteriskConfig


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nope.yaml")
        assert cfg.agent.max_steps == 50
        assert cfg.agent.headless is True
        assert cfg.llm.anthropic.model == "claude-sonnet-4-6"
        assert cfg.wiki.vault_path == "./wiki"
        assert cfg.browser.viewport_width == 1280

    def test_reads_agent_section(self, tmp_path: Path):
        p = _write_yaml(tmp_path / "c.yaml", {"agent": {"max_steps": 25, "headless": False}})
        cfg = load_config(p)
        assert cfg.agent.max_steps == 25
        assert cfg.agent.headless is False
        # unspecified fields keep defaults
        assert cfg.agent.token_budget == 100_000

    def test_reads_llm_section(self, tmp_path: Path):
        p = _write_yaml(tmp_path / "c.yaml", {
            "llm": {
                "anthropic": {"model": "claude-opus-4-7", "max_tokens": 8192},
                "openai": {"model": "gpt-4o-mini"},
            }
        })
        cfg = load_config(p)
        assert cfg.llm.anthropic.model == "claude-opus-4-7"
        assert cfg.llm.anthropic.max_tokens == 8192
        assert cfg.llm.openai.model == "gpt-4o-mini"
        # gemini keeps default
        assert cfg.llm.gemini.model == "gemini-1.5-pro"

    def test_reads_browser_section(self, tmp_path: Path):
        p = _write_yaml(tmp_path / "c.yaml", {
            "browser": {"viewport_width": 1920, "viewport_height": 1080, "slow_mo": 50}
        })
        cfg = load_config(p)
        assert cfg.browser.viewport_width == 1920
        assert cfg.browser.viewport_height == 1080
        assert cfg.browser.slow_mo == 50

    def test_reads_wiki_section(self, tmp_path: Path):
        p = _write_yaml(tmp_path / "c.yaml", {"wiki": {"vault_path": "/custom/vault"}})
        cfg = load_config(p)
        assert cfg.wiki.vault_path == "/custom/vault"

    def test_partial_yaml_merges_with_defaults(self, tmp_path: Path):
        p = _write_yaml(tmp_path / "c.yaml", {"agent": {"max_steps": 10}})
        cfg = load_config(p)
        assert cfg.agent.max_steps == 10
        assert cfg.browser.slow_mo == 0  # still default

    def test_returns_asterisk_config_type(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nope.yaml")
        assert isinstance(cfg, AsteriskConfig)

    def test_for_provider_lookup(self, tmp_path: Path):
        p = _write_yaml(tmp_path / "c.yaml", {
            "llm": {"openai": {"model": "gpt-4o"}}
        })
        cfg = load_config(p)
        assert cfg.llm.for_provider("openai").model == "gpt-4o"
        assert cfg.llm.for_provider("anthropic").model == "claude-sonnet-4-6"

    def test_empty_yaml_uses_defaults(self, tmp_path: Path):
        p = tmp_path / "c.yaml"
        p.write_text("", encoding="utf-8")
        cfg = load_config(p)
        assert cfg.agent.max_steps == 50

    def test_loads_real_config_yaml(self):
        cfg = load_config("config.yaml")
        assert cfg.agent.max_steps > 0
        assert cfg.llm.anthropic.model != ""
