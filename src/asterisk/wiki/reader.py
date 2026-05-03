"""Wiki reader — assembles the context payload for each LLM call."""
from __future__ import annotations

import logging
from pathlib import Path

from .resolver import WikilinkResolver, extract_wikilinks

logger = logging.getLogger(__name__)

# Always included regardless of step content
_ALWAYS_LOAD = ("status.md", "index.md")


class WikiReader:
    """
    Load wiki pages for a single agent step.

    Uses WikilinkResolver for all wikilink resolution so that case-insensitive
    and basename-only lookups work correctly.
    """

    def __init__(self, vault_path: str = "./wiki") -> None:
        self._vault = Path(vault_path).resolve()
        self._resolver = WikilinkResolver(self._vault)

    def load_context(
        self,
        task_slug: str,
        step_number: int,
    ) -> dict[str, str]:
        """
        Return {relative_path: content} for the current step.

        Always includes: status.md, index.md
        Conditionally includes:
          - The current step file (step_number - 1, i.e. the last completed step)
          - All pages referenced by [[wikilinks]] in that step file (one hop only)

        Missing files are silently skipped — broken links never crash the agent.
        """
        context: dict[str, str] = {}

        # Refresh the resolver index so newly-written step files are visible
        self._resolver.refresh()

        # Always-loaded anchor files
        for name in _ALWAYS_LOAD:
            self._load_by_rel(name, context)

        # Previous step file (context for the upcoming step)
        if step_number > 0:
            step_rel = f"steps/{task_slug}/step-{step_number:03d}.md"
            step_content = self._load_by_rel(step_rel, context)

            # Load pages referenced in the step's `related` wikilinks (one hop)
            if step_content:
                for link in extract_wikilinks(step_content):
                    self._load_by_link(link, context)

        return context

    def load_observation(self, slug: str) -> str | None:
        """Load a single observation file by slug. Returns content or None."""
        context: dict[str, str] = {}
        self._resolver.refresh()
        self._load_by_rel(f"observations/{slug}.md", context)
        return context.get(f"observations/{slug}.md")

    # ------------------------------------------------------------------ helpers

    def _load_by_rel(self, relative_path: str, context: dict[str, str]) -> str | None:
        """Load a vault file by its relative path string."""
        if relative_path in context:
            return context[relative_path]
        full_path = self._vault / relative_path
        if not full_path.exists():
            logger.debug("Wiki file not found (skipping): %s", relative_path)
            return None
        content = full_path.read_text(encoding="utf-8")
        context[relative_path] = content
        return content

    def _load_by_link(self, link: str, context: dict[str, str]) -> str | None:
        """Resolve a wikilink target and load the file."""
        abs_path = self._resolver.resolve(link)
        if abs_path is None:
            logger.debug("Unresolved wikilink (skipping): [[%s]]", link)
            return None
        rel = str(abs_path.relative_to(self._vault))
        return self._load_by_rel(rel, context)
