"""Observation extractor — persists reusable LLM findings to wiki/observations/."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .writer import WikiWriter

logger = logging.getLogger(__name__)

# Slugify: lowercase, replace non-alphanumeric runs with hyphens
_SLUG_RE = re.compile(r"[^\w]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:60] or "observation"


class ObservationExtractor:
    """
    Checks every LLM response for an optional `observation` block and, when
    present, writes it to `wiki/observations/<slug>.md`.

    Expected shape inside the LLM JSON response (all fields optional):
    {
      "observation": {
        "slug": "login-page-selectors",        // optional — derived from title if absent
        "title": "Login page field IDs",        // optional
        "content": "The login page always has id=email and id=password."
      }
    }

    The writer deduplicates by slug: if the file already exists the new content
    is appended under a separator so older observations aren't lost.
    """

    def __init__(self, vault_path: str | Path) -> None:
        self._writer = WikiWriter(str(vault_path))
        self._vault = Path(vault_path).resolve()

    def extract_and_save(self, parsed_response: dict) -> str | None:
        """
        Inspect *parsed_response* for an `observation` block.
        If found and non-empty, persist it and return the slug.
        Returns None if nothing was extracted.
        """
        obs = parsed_response.get("observation")
        if not obs or not isinstance(obs, dict):
            return None

        content = obs.get("content", "").strip()
        if not content:
            return None

        title = obs.get("title", "").strip()
        slug = obs.get("slug", "").strip()

        if not slug:
            slug = _slugify(title) if title else _slugify(content[:40])

        # Build the markdown for this observation
        heading = f"# {title}" if title else f"# Observation: {slug}"
        obs_md = f"{heading}\n\n{content}\n"

        obs_file = self._vault / "observations" / f"{slug}.md"

        if obs_file.exists():
            # Append so we keep the history of updates
            existing = obs_file.read_text(encoding="utf-8")
            obs_md = existing.rstrip() + "\n\n---\n\n" + obs_md
            obs_file.write_text(obs_md, encoding="utf-8")
            logger.info("Observation updated: observations/%s.md", slug)
        else:
            self._writer.write_observation(slug, obs_md)
            logger.info("New observation saved: observations/%s.md", slug)

        return slug
