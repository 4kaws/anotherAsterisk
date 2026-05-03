"""Shell command execution tool."""
from __future__ import annotations

import asyncio


class BashTool:
    """Execute shell commands. Returns stdout, stderr, and exit code."""

    TIMEOUT = 30  # seconds

    async def run(self, command: str, working_dir: str | None = None) -> dict:
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                ),
                timeout=self.TIMEOUT,
            )
            stdout, stderr = await proc.communicate()
            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode,
                "success": proc.returncode == 0,
            }
        except asyncio.TimeoutError:
            return {"error": f"Command timed out after {self.TIMEOUT}s", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}
