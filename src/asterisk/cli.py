"""Click CLI — entry point for the asterisk command."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from .config import load_config  # noqa: E402  (after load_dotenv so .env is ready)

_cfg = load_config()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option("0.1.0", prog_name="asterisk")
def cli() -> None:
    """anotherAsterisk — O(N)-cost agentic browser automation."""


@cli.command()
@click.argument("task")
@click.option("--url", "-u", default=None, help="Starting URL for the task.")
@click.option("--provider", "-p", default=None, help="LLM provider: anthropic | openai | gemini")
@click.option(
    "--max-steps", "-n",
    default=None,
    type=int,
    help=f"Hard step limit. [default: {_cfg.agent.max_steps} from config]",
)
@click.option("--headed", is_flag=True, default=False, help="Run browser in headed (visible) mode.")
@click.option(
    "--vault",
    default=None,
    help=f"Path to wiki vault. [default: {_cfg.wiki.vault_path} from config]",
)
@click.option(
    "--mode",
    default=None,
    type=click.Choice(["browser", "desktop", "hybrid"]),
    help="Agent mode: browser | desktop | hybrid. Auto-detected from task if omitted.",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def run(
    task: str,
    url: str | None,
    provider: str | None,
    max_steps: int | None,
    headed: bool,
    vault: str | None,
    mode: str | None,
    verbose: bool,
) -> None:
    """Run the agent on TASK, optionally starting at URL.

    Example:
        asterisk run "search for python on wikipedia" --url https://en.wikipedia.org
    """
    _setup_logging(verbose)

    if provider:
        os.environ["LLM_PROVIDER"] = provider

    resolved_max_steps = max_steps if max_steps is not None else _cfg.agent.max_steps
    resolved_vault = vault if vault is not None else _cfg.wiki.vault_path
    resolved_headless = False if headed else _cfg.agent.headless

    if mode is not None:
        resolved_mode = mode
        mode_source = "flag"
    elif _cfg.agent.mode != "browser":
        resolved_mode = _cfg.agent.mode
        mode_source = "config"
    else:
        from .mode_selector import detect_mode
        resolved_mode, mode_reason = detect_mode(task)
        mode_source = f"auto ({mode_reason})"

    from .agent import Agent

    agent = Agent(
        vault_path=resolved_vault,
        max_steps=resolved_max_steps,
        headless=resolved_headless,
        slow_mo=_cfg.browser.slow_mo,
        viewport_width=_cfg.browser.viewport_width,
        viewport_height=_cfg.browser.viewport_height,
        mode=resolved_mode,
    )

    click.echo(f"Running task: {task!r}")
    click.echo(
        f"Provider: {os.environ.get('LLM_PROVIDER', 'anthropic')}  |  "
        f"Max steps: {resolved_max_steps}  |  "
        f"Mode: {resolved_mode} [{mode_source}]  |  "
        f"Vault: {resolved_vault}"
    )
    click.echo("─" * 60)

    try:
        counter = asyncio.run(agent.run(task, start_url=url))
        click.echo("\n" + "─" * 60)
        click.secho(counter.summary(), fg="green")
    except KeyboardInterrupt:
        click.secho("\nInterrupted.", fg="yellow")
        sys.exit(1)
    except Exception as e:
        click.secho(f"\nAgent error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option("--vault", default="./wiki", show_default=True)
def status(vault: str) -> None:
    """Show the current wiki status (wiki/status.md)."""
    status_file = Path(vault) / "status.md"
    if not status_file.exists():
        click.secho("No status.md found. Has a task been run yet?", fg="yellow")
        return

    content = status_file.read_text(encoding="utf-8")
    click.echo(content)


@cli.command()
@click.option("--vault", default="./wiki", show_default=True)
def wiki(vault: str) -> None:
    """Open the wiki vault in Obsidian (if installed), or print the vault path."""
    vault_path = Path(vault).resolve()
    if not vault_path.exists():
        click.secho(f"Wiki vault not found at {vault_path}", fg="red")
        return

    # Try to open with Obsidian via its URI scheme
    obsidian_uri = f"obsidian://open?path={vault_path}"
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", obsidian_uri], check=True)
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", obsidian_uri], check=True)
        elif sys.platform == "win32":
            os.startfile(obsidian_uri)  # type: ignore[attr-defined]
        else:
            raise OSError("Unsupported platform")
        click.echo(f"Opened wiki in Obsidian: {vault_path}")
    except Exception:
        click.echo(f"Wiki vault is at: {vault_path}")
        click.echo("Open it manually in Obsidian or any markdown editor.")


@cli.command()
@click.option("--vault", default="./wiki", show_default=True)
def lint(vault: str) -> None:
    """Check for broken [[wikilinks]] in the vault."""
    import re
    vault_path = Path(vault).resolve()
    if not vault_path.exists():
        click.secho(f"Vault not found: {vault_path}", fg="red")
        return

    wikilink_re = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
    broken: list[tuple[str, str]] = []

    for md_file in sorted(vault_path.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        for link in wikilink_re.findall(content):
            link = link.strip()
            if not link.endswith(".md"):
                link = link + ".md"
            target = vault_path / link
            if not target.exists():
                rel = md_file.relative_to(vault_path)
                broken.append((str(rel), link))

    if broken:
        click.secho(f"Found {len(broken)} broken wikilink(s):", fg="red")
        for source, target in broken:
            click.echo(f"  {source}  →  [[{target}]]")
    else:
        click.secho("All wikilinks are valid.", fg="green")
