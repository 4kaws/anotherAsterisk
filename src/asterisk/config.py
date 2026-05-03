"""Config loader — reads config.yaml and exposes typed settings."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore


@dataclass
class AgentConfig:
    max_steps: int = 50
    token_budget: int = 100_000
    screenshot_on_each_step: bool = True
    headless: bool = False
    mode: str = "browser"  # browser | desktop | hybrid


@dataclass
class LLMProviderConfig:
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096


@dataclass
class LLMConfig:
    anthropic: LLMProviderConfig = field(
        default_factory=lambda: LLMProviderConfig(model="claude-sonnet-4-6")
    )
    openai: LLMProviderConfig = field(
        default_factory=lambda: LLMProviderConfig(model="gpt-4o")
    )
    gemini: LLMProviderConfig = field(
        default_factory=lambda: LLMProviderConfig(model="gemini-1.5-pro")
    )

    def for_provider(self, provider: str | None = None) -> LLMProviderConfig:
        """Return the config for *provider* (or the active $LLM_PROVIDER)."""
        p = provider or os.environ.get("LLM_PROVIDER", "anthropic")
        return getattr(self, p, self.anthropic)


@dataclass
class WikiConfig:
    vault_path: str = "./wiki"
    always_load: list[str] = field(default_factory=lambda: ["index.md", "status.md"])


@dataclass
class BrowserConfig:
    viewport_width: int = 1280
    viewport_height: int = 800
    slow_mo: int = 0


@dataclass
class AsteriskConfig:
    agent: AgentConfig = field(default_factory=AgentConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    wiki: WikiConfig = field(default_factory=WikiConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)


def load_config(path: str | Path = "config.yaml") -> AsteriskConfig:
    """Load config from *path*, returning defaults for any missing fields.

    Falls back entirely to defaults if the file is absent or PyYAML is not installed.
    """
    config_path = Path(path)
    cfg = AsteriskConfig()

    if not config_path.exists() or _yaml is None:
        return cfg

    raw: dict = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    agent_raw = raw.get("agent", {})
    if agent_raw:
        cfg.agent = AgentConfig(
            max_steps=int(agent_raw.get("max_steps", cfg.agent.max_steps)),
            token_budget=int(agent_raw.get("token_budget", cfg.agent.token_budget)),
            screenshot_on_each_step=bool(
                agent_raw.get("screenshot_on_each_step", cfg.agent.screenshot_on_each_step)
            ),
            headless=bool(agent_raw.get("headless", cfg.agent.headless)),
            mode=str(agent_raw.get("mode", cfg.agent.mode)),
        )

    llm_raw = raw.get("llm", {})
    if llm_raw:
        def _provider(key: str, default: LLMProviderConfig) -> LLMProviderConfig:
            d = llm_raw.get(key, {})
            return LLMProviderConfig(
                model=d.get("model", default.model),
                max_tokens=int(d.get("max_tokens", default.max_tokens)),
            )

        cfg.llm = LLMConfig(
            anthropic=_provider("anthropic", cfg.llm.anthropic),
            openai=_provider("openai", cfg.llm.openai),
            gemini=_provider("gemini", cfg.llm.gemini),
        )

    wiki_raw = raw.get("wiki", {})
    if wiki_raw:
        cfg.wiki = WikiConfig(
            vault_path=wiki_raw.get("vault_path", cfg.wiki.vault_path),
            always_load=wiki_raw.get("always_load", cfg.wiki.always_load),
        )

    browser_raw = raw.get("browser", {})
    if browser_raw:
        cfg.browser = BrowserConfig(
            viewport_width=int(browser_raw.get("viewport_width", cfg.browser.viewport_width)),
            viewport_height=int(browser_raw.get("viewport_height", cfg.browser.viewport_height)),
            slow_mo=int(browser_raw.get("slow_mo", cfg.browser.slow_mo)),
        )

    return cfg
