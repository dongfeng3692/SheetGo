"""HookManager — 工具执行钩子系统"""

from __future__ import annotations

from typing import Any, Callable

from .models import ToolCall, ToolResult


# 写入类工具列表（用于 SnapshotHook 等判断）
WRITE_TOOLS = frozenset({
    "write_cells", "add_formula", "add_column", "insert_row",
    "apply_style", "create_chart", "create_sheet", "merge_cells",
})


# Hook 函数类型
BeforeHook = Callable[[ToolCall], ToolCall | None]
AfterHook = Callable[[ToolCall, ToolResult], None]
ErrorHook = Callable[[ToolCall, Exception], None]


class HookManager:
    """工具执行钩子

    借鉴 claw-code 的三阶段 Hook: pre/post/failure。
    Pre hook 可修改 ToolCall 或返回 None 取消执行。
    """

    def __init__(self):
        self._before: list[tuple[str | None, BeforeHook]] = []
        self._after: list[tuple[str | None, AfterHook]] = []
        self._on_error: list[tuple[str | None, ErrorHook]] = []

    def register_before(
        self, tool_name: str | None, hook: BeforeHook
    ) -> None:
        """注册 pre hook。tool_name=None 表示所有工具。"""
        self._before.append((tool_name, hook))

    def register_after(
        self, tool_name: str | None, hook: AfterHook
    ) -> None:
        """注册 post hook。"""
        self._after.append((tool_name, hook))

    def register_on_error(
        self, tool_name: str | None, hook: ErrorHook
    ) -> None:
        """注册 error hook。"""
        self._on_error.append((tool_name, hook))

    def run_before(self, call: ToolCall) -> ToolCall | None:
        """执行 pre hooks。

        先执行工具特定 hook，再执行全局 hook。
        任一 hook 返回 None → 取消执行（短路）。
        返回修改后的 ToolCall 或 None。
        """
        current = call

        # 先执行工具特定 hook
        for name, hook in self._before:
            if name is not None and name != call.name:
                continue
            result = hook(current)
            if result is None:
                return None
            current = result

        return current

    def run_after(self, call: ToolCall, result: ToolResult) -> None:
        """执行 post hooks。"""
        for name, hook in self._after:
            if name is not None and name != call.name:
                continue
            try:
                hook(call, result)
            except Exception:
                pass  # post hook 不应阻断流程

    def run_on_error(self, call: ToolCall, error: Exception) -> None:
        """执行 error hooks。"""
        for name, hook in self._on_error:
            if name is not None and name != call.name:
                continue
            try:
                hook(call, error)
            except Exception:
                pass

    def clear(self) -> None:
        """清除所有 hooks"""
        self._before.clear()
        self._after.clear()
        self._on_error.clear()
