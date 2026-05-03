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
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "type", "--", text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        else:
            raise RuntimeError(f"desktop_type not supported on {system}")


def _is_wsl() -> bool:
    """Return True when running inside WSL1 or WSL2."""
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


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
