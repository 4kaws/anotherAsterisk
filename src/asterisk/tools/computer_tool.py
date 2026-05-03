"""Full desktop screenshot, click, and type tool."""
from __future__ import annotations

import asyncio
import platform
from pathlib import Path

_SCREEN_TMP = "/tmp/asterisk_screen.png"


class ComputerTool:
    """
    Takes a screenshot of the full desktop and can click/type at desktop coordinates.
    Supports macOS (screencapture + osascript), Linux (scrot/gnome-screenshot + xdotool),
    and Windows (PowerShell).
    """

    async def screenshot(self) -> bytes:
        system = platform.system()
        if system == "Darwin":
            proc = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-t", "png", _SCREEN_TMP,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return Path(_SCREEN_TMP).read_bytes()

        elif system == "Linux":
            # On WSL2 running under Windows, use PowerShell to capture the real
            # Windows desktop instead of the empty WSLg X display.
            if _is_wsl():
                return await _wsl_screenshot()

            for cmd in [
                ["scrot", _SCREEN_TMP],
                ["gnome-screenshot", "-f", _SCREEN_TMP],
                ["import", "-window", "root", _SCREEN_TMP],
            ]:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.wait()
                    p = Path(_SCREEN_TMP)
                    if p.exists():
                        return p.read_bytes()
                except FileNotFoundError:
                    continue
            raise RuntimeError(
                "No screenshot tool found. Install scrot: sudo apt install scrot"
            )

        elif system == "Windows":
            win_tmp = "C:/temp/asterisk_screen.png"
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Screen]::PrimaryScreen | ForEach-Object { "
                "$bmp = New-Object System.Drawing.Bitmap($_.Bounds.Width, $_.Bounds.Height); "
                "$g = [System.Drawing.Graphics]::FromImage($bmp); "
                "$g.CopyFromScreen($_.Bounds.Location, [System.Drawing.Point]::Empty, $_.Bounds.Size); "
                f"$bmp.Save('{win_tmp}') }}"
            )
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-Command", ps_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return Path(win_tmp).read_bytes()

        raise RuntimeError(f"Unsupported OS: {system}")

    async def click(self, x: int, y: int) -> None:
        """Click at absolute desktop coordinates."""
        system = platform.system()
        if system == "Darwin":
            script = f'tell application "System Events" to click at {{{x}, {y}}}'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        elif system == "Linux" and _is_wsl():
            await _wsl_click(x, y)
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "mousemove", str(x), str(y), "click", "1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        else:
            raise RuntimeError(f"desktop_click not supported on {system}")

    async def type_text(self, text: str) -> None:
        """Type text at the current cursor position."""
        system = platform.system()
        if system == "Darwin":
            script = f'tell application "System Events" to keystroke "{text}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        elif system == "Linux" and _is_wsl():
            await _wsl_type(text)
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "type", "--", text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        else:
            raise RuntimeError(f"desktop_type not supported on {system}")

    async def hotkey(self, keys: str) -> None:
        """Send a keyboard shortcut. keys = 'ctrl+k', 'enter', 'ctrl+shift+s', etc."""
        system = platform.system()
        sendkeys_str = _to_sendkeys(keys)
        if system == "Darwin":
            # osascript for macOS hotkeys — convert to key code approach
            script = f'tell application "System Events" to keystroke "{sendkeys_str}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        elif system == "Linux" and _is_wsl():
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.SendKeys]::SendWait('{sendkeys_str}')"
            )
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe", "-NoProfile", "-Command", ps_cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "key", keys.replace("+", "+"),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        else:
            raise RuntimeError(f"desktop_hotkey not supported on {system}")


_SENDKEYS_MAP = {
    "ctrl": "^", "shift": "+", "alt": "%",
    "enter": "{ENTER}", "return": "{ENTER}",
    "escape": "{ESCAPE}", "esc": "{ESCAPE}",
    "tab": "{TAB}", "backspace": "{BACKSPACE}",
    "delete": "{DELETE}", "del": "{DELETE}",
    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
    "home": "{HOME}", "end": "{END}",
    "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}",
    "f5": "{F5}", "f6": "{F6}", "f7": "{F7}", "f8": "{F8}",
}


def _to_sendkeys(keys: str) -> str:
    """Convert human-friendly shortcut ('ctrl+k', 'enter') to SendKeys format."""
    parts = [p.strip().lower() for p in keys.split("+")]
    result = ""
    for part in parts:
        result += _SENDKEYS_MAP.get(part, part)
    return result


def _is_wsl() -> bool:
    """Return True when running inside WSL1 or WSL2."""
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


async def _wsl_click(x: int, y: int) -> None:
    """Click at Windows desktop coordinates from WSL2 via PowerShell WinAPI."""
    ps_cmd = (
        "Add-Type -TypeDefinition '"
        "using System; using System.Runtime.InteropServices; "
        "public class W { "
        "[DllImport(\"user32.dll\")] public static extern bool SetCursorPos(int x, int y); "
        "[DllImport(\"user32.dll\")] public static extern void mouse_event(uint f,int x,int y,uint d,UIntPtr e); "
        "public static void Click(int x,int y){ SetCursorPos(x,y); mouse_event(2,0,0,0,UIntPtr.Zero); mouse_event(4,0,0,0,UIntPtr.Zero); } "
        "}'; "
        f"[W]::Click({x},{y})"
    )
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-Command", ps_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()


async def _wsl_type(text: str) -> None:
    """Type text into the focused Windows app from WSL2 via PowerShell SendKeys."""
    # Escape special SendKeys chars: +^%~(){}[]
    escaped = ""
    for ch in text:
        if ch in "+^%~(){}[]":
            escaped += "{" + ch + "}"
        else:
            escaped += ch
    ps_cmd = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}')"
    )
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-Command", ps_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()


async def _wsl_screenshot() -> bytes:
    """Capture the Windows desktop from WSL via powershell.exe."""
    # Save to a Windows-accessible temp path then read it back via the WSL mount
    win_tmp = r"C:\Windows\Temp\asterisk_screen.png"
    wsl_tmp = "/mnt/c/Windows/Temp/asterisk_screen.png"
    ps_cmd = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
        "$b=[System.Drawing.Rectangle]::FromLTRB(0,0,"
        "[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,"
        "[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
        "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height); "
        "$g=[System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
        f"$bmp.Save('{win_tmp}')"
    )
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-Command", ps_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    return Path(wsl_tmp).read_bytes()
