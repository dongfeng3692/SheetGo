"""AgentEngine — 对话引擎（核心循环）"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from .hook_manager import WRITE_TOOLS, HookManager
from .llm_provider import LLMProvider
from .models import (
    AgentEvent,
    ChatEvent,
    ConversationState,
    EvDone,
    EvError,
    EvTextDelta,
    EvTextEnd,
    EvTextStart,
    EvToolCallEnd,
    EvToolCallProgress,
    EvToolCallStart,
    Finish,
    Message,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResult,
    UsageEvent,
)
from .prompt_builder import PromptBuilder, PromptContext
from .tool_registry import ToolRegistry


# Doom loop 检测阈值（同工具同参数连续出现次数）
_DOOM_LOOP_THRESHOLD = 3
# 读写交替循环检测：连续 N 次 read/write 且目标重复时才触发
_READ_WRITE_CYCLE_THRESHOLD = 6
_READ_WRITE_GUARD_READ_TOOLS = frozenset({"read_sheet", "sheet_info"})
_READ_WRITE_GUARD_WRITE_TOOLS = frozenset(set(WRITE_TOOLS) | {"write_query"})

# 默认最大循环次数
_DEFAULT_MAX_STEPS = 50


class AgentEngine:
    """Agent 对话引擎（主循环）

    借鉴 opencode-dev 的 while(true) agent loop 和 claw-code 的 hook-augmented 循环。

    循环逻辑:
    1. 构建消息列表（system + 历史 + 新消息）
    2. 构建 tools 定义
    3. 调用 LLM（流式）
    4. 如果有 tool_calls:
       a. 遍历每个 tool_call
       b. 执行 pre_hooks
       c. 执行工具
       d. 执行 post_hooks
       e. 将 tool_result 追加到消息
       f. 回到步骤 3
    5. 如果无 tool_calls → 结束，返回最终状态
    """

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        prompt: PromptBuilder,
        hooks: HookManager,
    ):
        self.llm = llm
        self.tools = tools
        self.prompt = prompt
        self.hooks = hooks
        self._cancelled = False

    def cancel(self):
        """中断当前对话"""
        self._cancelled = True

    async def chat(
        self,
        state: ConversationState,
        user_message: str,
        on_event: Callable[[AgentEvent], None] | None = None,
        max_steps: int = _DEFAULT_MAX_STEPS,
    ) -> ConversationState:
        """执行一次完整对话循环"""
        self._cancelled = False

        # 构建 system prompt (content blocks with cache_control)
        ctx = PromptContext(
            file_paths=state.file_paths,
            db_paths=state.db_paths,
            schemas=state.schemas,
            samples=state.samples,
            structures=state.structures,
            workspace_dir=state.workspace_dir,
        )
        system_prompt = self.prompt.build_system_prompt(ctx)

        # 添加用户消息到 state
        user_msg = Message(
            id=_new_id(),
            role="user",
            content=user_message,
        )
        state.messages.append(user_msg)

        # 工具调用历史（用于 doom loop / read-write loop 检测）
        recent_tool_calls: list[dict[str, str]] = []

        # 主循环
        for step in range(max_steps):
            if self._cancelled:
                _emit(on_event, EvError(message="对话已被用户中断"))
                break

            # 1. 构建消息
            messages = self.prompt.build_messages(state, "", system_prompt)
            # build_messages 末尾会追加一个空 user 占位，移除它
            # （用户消息已在 state.messages 中，通过 build_messages 的历史遍历包含）
            if messages and messages[-1]["role"] == "user" and not messages[-1].get("content"):
                messages.pop()

            # 2. 构建工具定义
            tool_defs = self.tools.get_definitions()

            # 3. 调用 LLM
            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            usage_input = 0
            usage_output = 0

            try:
                async for event in self.llm.chat(messages, tools=tool_defs):
                    if self._cancelled:
                        break

                    if isinstance(event, TextDelta):
                        if not text_parts:
                            _emit(on_event, EvTextStart())
                        text_parts.append(event.text)
                        _emit(on_event, EvTextDelta(text=event.text))

                    elif isinstance(event, ToolCallStart):
                        pass  # 累积到 ToolCallEnd

                    elif isinstance(event, ToolCallDelta):
                        pass  # 累积到 ToolCallEnd

                    elif isinstance(event, ToolCallEnd):
                        try:
                            args = json.loads(event.arguments) if event.arguments else {}
                        except json.JSONDecodeError:
                            args = {"_raw": event.arguments}
                        tool_calls.append(ToolCall(
                            id=event.id,
                            name=event.name,
                            arguments=args,
                        ))

                    elif isinstance(event, UsageEvent):
                        usage_input += event.input_tokens
                        usage_output += event.output_tokens

                    elif isinstance(event, Finish):
                        pass  # 循环自然结束

            except Exception as e:
                _emit(on_event, EvError(message=f"LLM 调用失败: {e}"))
                break

            # 如果有文本，发出 TextEnd
            if text_parts:
                _emit(on_event, EvTextEnd(full_text="".join(text_parts)))

            # 记录 assistant 消息
            assistant_msg = Message(
                id=_new_id(),
                role="assistant",
                content="".join(text_parts),
                tool_calls=tool_calls if tool_calls else None,
            )
            state.messages.append(assistant_msg)
            state.total_tokens += usage_input + usage_output

            # 4. 如果无 tool_calls → 结束
            if not tool_calls:
                break

            # 5. 遍历 tool_calls
            loop_guard_triggered = False
            for tc_index, tc in enumerate(tool_calls):
                if self._cancelled:
                    break

                _emit(on_event, EvToolCallStart(id=tc.id, name=tc.name))
                args_brief = json.dumps(tc.arguments, ensure_ascii=False)
                if len(args_brief) > 300:
                    args_brief = args_brief[:300] + "..."
                _emit(on_event, EvToolCallProgress(id=tc.id, message=f"call {tc.name}({args_brief})"))

                # Doom loop 检测
                call_entry = _tool_history_entry(tc)
                recent_tool_calls.append(call_entry)
                if len(recent_tool_calls) >= _DOOM_LOOP_THRESHOLD:
                    last_n = recent_tool_calls[-_DOOM_LOOP_THRESHOLD:]
                    if len({(entry["name"], entry["signature"]) for entry in last_n}) == 1:
                        error_message = f"检测到 doom loop: {tc.name} 连续调用 {_DOOM_LOOP_THRESHOLD} 次，已停止继续调用并要求直接收尾"
                        tool_error = "doom loop 检测: 已停止进一步工具调用，请基于现有结果直接输出最终结论"
                        _emit(on_event, EvError(message=error_message))
                        _emit(on_event, EvToolCallEnd(id=tc.id, name=tc.name, result=None, error=tool_error))
                        for offset, skipped_tc in enumerate(tool_calls[tc_index:]):
                            skipped_error = (
                                tool_error
                                if offset == 0
                                else "已因 doom loop 保护取消，勿再继续工具调用，请直接给出最终答复"
                            )
                            state.messages.append(
                                Message(
                                    id=_new_id(),
                                    role="tool",
                                    tool_results=[ToolResult(
                                        call_id=skipped_tc.id,
                                        name=skipped_tc.name,
                                        error=skipped_error,
                                    )],
                                )
                            )
                        loop_guard_triggered = True
                        break

                # 读写交替循环检测: read_sheet → write_cells 反复交替
                if len(recent_tool_calls) >= _READ_WRITE_CYCLE_THRESHOLD:
                    tail = recent_tool_calls[-_READ_WRITE_CYCLE_THRESHOLD:]
                    is_cycle = True
                    for i, entry in enumerate(tail):
                        name = entry["name"]
                        if i % 2 == 0:
                            if name not in _READ_WRITE_GUARD_READ_TOOLS:
                                is_cycle = False
                                break
                        else:
                            if name not in _READ_WRITE_GUARD_WRITE_TOOLS:
                                is_cycle = False
                                break

                    if is_cycle:
                        file_paths = {entry["file_path"] for entry in tail if entry["file_path"]}
                        sheets = {entry["sheet"] for entry in tail if entry["sheet"]}
                        read_signatures = [entry["signature"] for idx, entry in enumerate(tail) if idx % 2 == 0]
                        write_signatures = [entry["signature"] for idx, entry in enumerate(tail) if idx % 2 == 1]
                        repeated_targets = (
                            len(set(read_signatures)) < len(read_signatures)
                            and len(set(write_signatures)) < len(write_signatures)
                        )
                        if len(file_paths) > 1 or len(sheets) > 1 or not repeated_targets:
                            is_cycle = False

                    if is_cycle:
                        error_message = (
                            f"检测到重复 read/write 验证循环: 最近 {_READ_WRITE_CYCLE_THRESHOLD} 次调用都在同一目标间反复确认，"
                            "已停止继续工具调用并要求直接收尾"
                        )
                        tool_error = "读写交替循环检测: 已停止进一步工具调用，请不要继续反复确认，直接基于已有结果输出最终答复"
                        _emit(on_event, EvError(message=error_message))
                        _emit(on_event, EvToolCallEnd(id=tc.id, name=tc.name, result=None, error=tool_error))
                        for offset, skipped_tc in enumerate(tool_calls[tc_index:]):
                            skipped_error = (
                                tool_error
                                if offset == 0
                                else "已因读写循环保护取消，请直接根据已有工具结果作答"
                            )
                            state.messages.append(
                                Message(
                                    id=_new_id(),
                                    role="tool",
                                    tool_results=[ToolResult(
                                        call_id=skipped_tc.id,
                                        name=skipped_tc.name,
                                        error=skipped_error,
                                    )],
                                )
                            )
                        loop_guard_triggered = True
                        break

                # Pre hooks
                modified_tc = self.hooks.run_before(tc)
                if modified_tc is None:
                    # Hook 取消了执行
                    tr = ToolResult(call_id=tc.id, name=tc.name, error="操作被 Hook 取消")
                    _emit(on_event, EvToolCallEnd(id=tc.id, name=tc.name, result=None, error="操作被取消"))
                else:
                    # 执行工具
                    try:
                        tr = await self.tools.execute(modified_tc.name, modified_tc.arguments)
                        tr.call_id = tc.id
                        self.hooks.run_after(modified_tc, tr)
                    except Exception as e:
                        tr = ToolResult(call_id=tc.id, name=tc.name, error=str(e))
                        self.hooks.run_on_error(modified_tc, e)

                    _emit(on_event, EvToolCallEnd(
                        id=tc.id,
                        name=tc.name,
                        result=tr.result,
                        error=tr.error,
                    ))

                # 追加 tool result 消息
                tool_msg = Message(
                    id=_new_id(),
                    role="tool",
                    tool_results=[tr],
                )
                state.messages.append(tool_msg)

            if loop_guard_triggered:
                continue

        _emit(on_event, EvDone())
        return state


def _emit(
    on_event: Callable[[AgentEvent], None] | None,
    event: AgentEvent,
) -> None:
    if on_event:
        on_event(event)


def _new_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


def _tool_history_entry(call: ToolCall) -> dict[str, str]:
    """Create a compact signature for loop detection."""
    arguments = call.arguments if isinstance(call.arguments, dict) else {}
    return {
        "name": call.name,
        "signature": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        "file_path": str(arguments.get("file_path", "")),
        "sheet": str(arguments.get("sheet", "")),
    }
