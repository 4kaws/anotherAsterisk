"""File read/write tool."""
from __future__ import annotations

from pathlib import Path


class FileTool:

    async def read(self, path: str) -> dict:
        try:
            content = Path(path).read_text(encoding="utf-8")
            return {"content": content, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    async def write(self, path: str, content: str, append: bool = False) -> dict:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if append:
                with p.open("a", encoding="utf-8") as f:
                    f.write(content)
            else:
                p.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(p.resolve())}
        except Exception as e:
            return {"error": str(e), "success": False}
