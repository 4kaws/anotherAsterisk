"""Wiki writer — writes step files, status, and observations with schema validation."""
from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator


class StepSchema(BaseModel):
    step: int
    task: str
    action_taken: str
    element: Optional[str] = None
    url: str
    outcome: str
    next_hint: str
    related: list[str] = []
    timestamp: str

    @field_validator("outcome")
    @classmethod
    def _valid_outcome(cls, v: str) -> str:
        if v not in ("success", "failure", "pending"):
            raise ValueError(f"outcome must be success/failure/pending, got {v!r}")
        return v


class WikiWriteError(Exception):
    """Raised when a wiki write operation fails validation."""


class WikiWriter:
    """Write step files and status updates to the wiki vault."""

    def __init__(self, vault_path: str = "./wiki") -> None:
        self._vault = Path(vault_path).resolve()

    def write_step(
        self,
        task_slug: str,
        step_number: int,
        data: dict,
        screenshot_bytes: Optional[bytes] = None,
    ) -> Path:
        """
        Write a step markdown file (and optionally its screenshot).

        The data dict is validated against StepSchema before writing.
        Returns the path of the written file.
        """
        # Ensure timestamp is present
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            step = StepSchema(**data)
        except Exception as e:
            raise WikiWriteError(f"Invalid step data: {e}") from e

        step_dir = self._vault / "steps" / task_slug
        step_dir.mkdir(parents=True, exist_ok=True)

        step_file = step_dir / f"step-{step_number:03d}.md"
        related_links = "\n".join(f"- {r}" for r in step.related) if step.related else "_none_"

        # Write screenshot alongside if provided
        screenshot_ref = ""
        if screenshot_bytes:
            png_file = step_dir / f"step-{step_number:03d}.png"
            png_file.write_bytes(screenshot_bytes)
            screenshot_ref = f"\n![screenshot](step-{step_number:03d}.png)\n"

        content = textwrap.dedent(f"""\
            # Step {step_number:03d} — {step.task}

            **Outcome**: {step.outcome}
            **URL**: {step.url}
            **Timestamp**: {step.timestamp}
            {screenshot_ref}
            ## Action Taken

            {step.action_taken}

            ## Related

            {related_links}

            ## Raw Data

            ```json
            {json.dumps(step.model_dump(), indent=2)}
            ```
        """)

        step_file.write_text(content, encoding="utf-8")
        return step_file

    def update_status(
        self,
        task: str,
        step: int,
        url: str,
        progress: str,
        last_action: str,
        next_hint: str,
    ) -> None:
        """Overwrite wiki/status.md with the current agent state."""
        now = datetime.now(timezone.utc).isoformat()
        content = textwrap.dedent(f"""\
            # Status

            > This file is always loaded. It is the agent's heartbeat.

            ## Current State

            - **task**: {task}
            - **step**: {step}
            - **url**: {url}
            - **progress**: {progress}
            - **last_action**: {last_action}
            - **next_hint**: {next_hint}

            ---
            _Last updated: {now}_
        """)
        (self._vault / "status.md").write_text(content, encoding="utf-8")

    def write_observation(self, slug: str, content: str) -> Path:
        """Write a reusable observation file to wiki/observations/<slug>.md."""
        obs_dir = self._vault / "observations"
        obs_dir.mkdir(parents=True, exist_ok=True)

        obs_file = obs_dir / f"{slug}.md"
        obs_file.write_text(content, encoding="utf-8")
        return obs_file

    def update_index(self, task_slug: str, description: str, status: str = "active") -> None:
        """Add or update a task entry in wiki/index.md."""
        index_file = self._vault / "index.md"
        content = index_file.read_text(encoding="utf-8") if index_file.exists() else ""

        marker = "| _(none yet)_ | | |"
        entry = f"| {task_slug} | {description} | {status} |"

        if marker in content:
            content = content.replace(marker, entry)
        elif task_slug in content:
            # Already present — do nothing
            return
        else:
            # Append to the table — find the header row and add below it
            header = "| Slug | Description | Status |"
            if header in content:
                content = content.replace(
                    header + "\n|------|-------------|--------|",
                    header + "\n|------|-------------|--------|\n" + entry,
                )

        index_file.write_text(content, encoding="utf-8")
