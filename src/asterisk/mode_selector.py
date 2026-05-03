"""Heuristic mode selector — picks browser or desktop based on task content."""
from __future__ import annotations

# Native desktop applications — if mentioned, prefer desktop mode
_DESKTOP_APPS = frozenset({
    "discord", "spotify", "slack", "zoom", "teams", "skype", "steam",
    "obs", "obs studio", "vlc", "whatsapp", "telegram", "signal",
    "calculator", "notepad", "excel", "word", "powerpoint", "outlook",
    "photoshop", "illustrator", "vs code", "vscode", "visual studio",
    "file explorer", "task manager", "control panel", "finder",
    "itunes", "winamp", "foobar2000", "winrar", "7zip",
    "epic games", "battle.net", "origin", "uplay", "ubisoft connect",
})

# Web content signals — if mentioned, prefer browser mode even if a browser app is named
_WEB_SIGNALS = frozenset({
    "youtube", "yt video", "yt channel", "youtu.be", "google", "wikipedia", "twitter", "facebook", "instagram",
    "reddit", "amazon", "ebay", "github", "stackoverflow", "linkedin",
    "twitch", "tiktok", "netflix", "website", "webpage", "url",
    "http://", "https://", ".com", ".org", ".net", ".io",
    "browse", "search the web", "open tab", "new tab", "web page",
    "online", "internet",
})


def detect_mode(task: str) -> tuple[str, str]:
    """Return (mode, reason) for the given task string.

    Returns 'desktop' if the task mentions a known native app and no web content.
    Returns 'browser' otherwise (safe default for web navigation tasks).
    """
    t = task.lower()
    has_desktop = any(app in t for app in _DESKTOP_APPS)
    has_web = any(sig in t for sig in _WEB_SIGNALS)

    if has_desktop and not has_web:
        app = next(a for a in _DESKTOP_APPS if a in t)
        return "desktop", f"detected native app '{app}'"
    if has_web:
        sig = next(s for s in _WEB_SIGNALS if s in t)
        return "browser", f"detected web content '{sig}'"
    return "browser", "no specific signals — defaulting to browser"
