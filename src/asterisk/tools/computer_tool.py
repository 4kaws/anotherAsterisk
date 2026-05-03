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
