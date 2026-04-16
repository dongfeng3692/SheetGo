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
# 读写交替循环检测：连续 N 次 read_sheet → write_cells 模式
_READ_WRITE_CYCLE_THRESHOLD = 4

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

        # 构建 system prompt
        ctx = PromptContext(
            file_paths=state.file_paths,
            db_paths=state.db_paths,
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

        # Doom loop 检测历史
        recent_tool_calls: list[tuple[str, str]] = []

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
            for tc in tool_calls:
                if self._cancelled:
                    break

                _emit(on_event, EvToolCallStart(id=tc.id, name=tc.name))
                args_brief = json.dumps(tc.arguments, ensure_ascii=False)
                if len(args_brief) > 300:
                    args_brief = args_brief[:300] + "..."
                _emit(on_event, EvToolCallProgress(id=tc.id, message=f"call {tc.name}({args_brief})"))

                # Doom loop 检测
                tc_sig = (tc.name, json.dumps(tc.arguments, sort_keys=True))
                recent_tool_calls.append(tc_sig)
                if len(recent_tool_calls) >= _DOOM_LOOP_THRESHOLD:
                    last_n = recent_tool_calls[-_DOOM_LOOP_THRESHOLD:]
                    if len(set(last_n)) == 1:
                        _emit(on_event, EvError(
                            message=f"检测到 doom loop: {tc.name} 连续调用 {_DOOM_LOOP_THRESHOLD} 次"
                        ))
                        # 追加错误 tool_result 保持消息序列完整
                        tr = ToolResult(call_id=tc.id, name=tc.name, error="doom loop 检测: 操作已中止")
                        tool_msg = Message(
                            id=_new_id(),
                            role="tool",
                            tool_results=[tr],
                        )
                        state.messages.append(tool_msg)
                        _emit(on_event, EvDone())
                        return state

                # 读写交替循环检测: read_sheet → write_cells 反复交替
                if len(recent_tool_calls) >= _READ_WRITE_CYCLE_THRESHOLD:
                    tail = [c[0] for c in recent_tool_calls[-_READ_WRITE_CYCLE_THRESHOLD:]]
                    _read_tools = {"read_sheet", "sheet_info"}
                    _write_tools = {"write_cells", "add_formula", "add_column", "insert_row"}
                    is_cycle = True
                    for i, name in enumerate(tail):
                        if i % 2 == 0:
                            if name not in _read_tools:
                                is_cycle = False
                                break
                        else:
                            if name not in _write_tools:
                                is_cycle = False
                                break
                    if is_cycle:
                        _emit(on_event, EvError(
                            message=f"检测到读写交替循环: 连续 {_READ_WRITE_CYCLE_THRESHOLD} 次 read→write 模式，请停止反复确认"
                        ))
                        tr = ToolResult(call_id=tc.id, name=tc.name, error="读写交替循环检测: 操作已中止，请直接输出最终结果")
                        tool_msg = Message(
                            id=_new_id(),
                            role="tool",
                            tool_results=[tr],
                        )
                        state.messages.append(tool_msg)
                        _emit(on_event, EvDone())
                        return state

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
