"""list_files — 列出工作目录下的文件"""

from __future__ import annotations

import os
from typing import Any

from .base import BaseTool


class ListFilesTool(BaseTool):

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "列出指定目录下的文件。默认列出工作目录中的文件，"
            "可指定子目录（如 'working'、'source'、'exports'）和文件类型过滤。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "目录路径。可以是绝对路径，也可以是相对于工作目录的路径。默认为工作目录。",
                },
                "extension": {
                    "type": "string",
                    "description": "文件扩展名过滤，如 '.xlsx'、'.csv'。默认不过滤。",
                },
            },
            "required": [],
        }

    @property
    def safe_level(self) -> str:
        return "read"

    async def execute(
        self,
        directory: str | None = None,
        extension: str | None = None,
        **kwargs,
    ) -> dict:
        target = directory or ""
        if not os.path.isabs(target):
            # 相对路径：尝试基于 working 子目录或当前目录解析
            target = os.path.abspath(target)

        if not os.path.isdir(target):
            return {"error": f"目录不存在: {target}"}

        files: list[dict] = []
        try:
            entries = os.listdir(target)
        except PermissionError:
            return {"error": f"无权限访问目录: {target}"}

        for name in sorted(entries):
            full = os.path.join(target, name)
            if not os.path.isfile(full):
                continue
            if extension and not name.lower().endswith(extension.lower()):
                continue
            try:
                stat = os.stat(full)
                files.append({
                    "name": name,
                    "size": stat.st_size,
                    "modified": _fmt_time(stat.st_mtime),
                    "path": full,
                })
            except OSError:
                files.append({"name": name, "path": full})

        return {
            "directory": target,
            "files": files,
            "total": len(files),
        }


def _fmt_time(ts: float) -> str:
    """Format a timestamp as readable string."""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S")
