"""Wikilink resolver — maps [[link]] strings to vault file paths."""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Matches [[path]] or [[path|display text]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")


def extract_wikilinks(text: str) -> list[str]:
    """Return raw link targets from all [[wikilinks]] found in *text*."""
    return [m.strip() for m in _WIKILINK_RE.findall(text)]


class WikilinkResolver:
    """
    Resolves Obsidian-style [[wikilinks]] to absolute paths inside a vault.

    Resolution order for a link "foo/bar":
      1. Exact match: <vault>/foo/bar.md (or foo/bar if already ends in .md)
      2. Case-insensitive match across the whole vault index
      3. Basename-only match (Obsidian "shortest path" behaviour)

    The vault index is built lazily on first use and can be refreshed via
    `refresh()` when new files are written during a run.
    """

    def __init__(self, vault_path: str | Path) -> None:
        self._vault = Path(vault_path).resolve()
        self._index: dict[str, Path] | None = None  # lower-case rel path → abs path

    def refresh(self) -> None:
        """Rebuild the in-memory index from the current vault contents."""
        self._index = {}
        for path in self._vault.rglob("*.md"):
            rel = path.relative_to(self._vault)
            self._index[str(rel).lower()] = path

    def _ensure_index(self) -> dict[str, Path]:
        if self._index is None:
            self.refresh()
        return self._index  # type: ignore[return-value]

    def resolve(self, link: str) -> Path | None:
        """
        Resolve a wikilink target string to an absolute Path, or None if not found.

        *link* should be the raw content inside [[ ]], e.g. "steps/task/step-001"
        or "observations/checkout-flow".
        """
        link = link.strip()

        # Normalise: add .md if missing
        if not link.lower().endswith(".md"):
            link_with_ext = link + ".md"
        else:
            link_with_ext = link

        # 1. Exact match
        candidate = self._vault / link_with_ext
        if candidate.exists():
            return candidate

        index = self._ensure_index()

        # 2. Case-insensitive match on full relative path
        key = link_with_ext.lower()
        if key in index:
            return index[key]

        # 3. Basename-only match (Obsidian shortest-path fallback)
        basename = Path(link_with_ext).name.lower()
        matches = [p for k, p in index.items() if Path(k).name == basename]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            logger.warning(
                "Ambiguous wikilink [[%s]] — %d matches, returning first: %s",
                link, len(matches), matches[0],
            )
            return matches[0]

        logger.debug("Unresolved wikilink: [[%s]]", link)
        return None

    def resolve_all(self, links: list[str]) -> dict[str, Path]:
        """
        Resolve a list of wikilink targets.  Returns a dict of {link: path}
        for links that were successfully resolved.
        """
        result: dict[str, Path] = {}
        for link in links:
            path = self.resolve(link)
            if path is not None:
                result[link] = path
        return result
