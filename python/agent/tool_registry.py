"""ToolRegistry — 工具注册中心"""

from __future__ import annotations

from typing import Any

from .models import ToolResult


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, Any] = {}           # name → BaseTool

    def register(self, tool: Any) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Any | None:
        """获取工具实例"""
        return self._tools.get(name)

    def get_definitions(self) -> list[dict]:
        """获取所有已注册工具的定义（function calling 格式）"""
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """执行工具"""
        call_id = ""  # 由 engine 层填充
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"未知工具: {name}",
            )

        try:
            result = await tool.execute(**arguments)
            return ToolResult(call_id=call_id, name=name, result=result)
        except NotImplementedError:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"工具 {name} 尚未实现",
            )
        except Exception as e:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"工具执行失败: {type(e).__name__}: {e}",
            )

    def list_tools(self) -> list[str]:
        """列出所有已注册工具"""
        return list(self._tools.keys())

    def is_write_tool(self, name: str) -> bool:
        """检查工具是否为写入类"""
        tool = self._tools.get(name)
        return tool is not None and tool.safe_level == "write"
