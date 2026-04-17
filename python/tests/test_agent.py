"""Agent Core 测试"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import (
    AgentEngine,
    ConversationState,
    HookManager,
    LLMConfig,
    LLMProvider,
    Message,
    PromptBuilder,
    ToolRegistry,
)
from agent.models import (
    ChatEvent,
    EvDone,
    EvError,
    EvTextDelta,
    EvTextEnd,
    EvTextStart,
    EvToolCallEnd,
    EvToolCallStart,
    Finish,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResult,
)
from agent.prompt_builder import PromptContext, SystemPromptBuilder
from tools.base import BaseTool


# ============================================================================
# Mock LLM Provider — 预设 LLM 响应
# ============================================================================


class MockLLMProvider(LLMProvider):
    """用于测试的 Mock LLM Provider"""

    def __init__(self, responses: list[list[ChatEvent]] | None = None):
        super().__init__(LLMConfig())
        self.responses = responses or []
        self._call_count = 0

    def set_responses(self, responses: list[list[ChatEvent]]):
        self.responses = responses
        self._call_count = 0

    async def chat(self, messages, tools=None, stream=True):
        if self._call_count >= len(self.responses):
            # 默认：纯文本回复
            yield TextDelta(text="好的，我了解了。")
            yield Finish(reason="stop")
            return

        events = self.responses[self._call_count]
        self._call_count += 1
        for event in events:
            yield event


# ============================================================================
# Mock Tool — 用于测试的简单工具
# ============================================================================


class EchoTool(BaseTool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo back the input"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        }

    async def execute(self, text: str = "", **kwargs):
        return {"echo": text}


class FailTool(BaseTool):
    @property
    def name(self) -> str:
        return "fail_tool"

    @property
    def description(self) -> str:
        return "Always fails"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
            },
            "required": ["reason"],
        }

    async def execute(self, reason: str = "", **kwargs):
        raise ValueError(reason)


class WriteTool(BaseTool):
    @property
    def name(self) -> str:
        return "write_test"

    @property
    def description(self) -> str:
        return "A test write tool"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "data": {"type": "string"},
            },
            "required": ["data"],
        }

    @property
    def safe_level(self) -> str:
        return "write"

    async def execute(self, data: str = "", **kwargs):
        return {"written": data}


# ============================================================================
# Helper: 创建标准 engine
# ============================================================================


def _make_engine(llm=None):
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(FailTool())
    registry.register(WriteTool())

    hooks = HookManager()
    prompt = PromptBuilder()

    return AgentEngine(
        llm=llm or MockLLMProvider(),
        tools=registry,
        prompt=prompt,
        hooks=hooks,
    )


# ============================================================================
# Tests
# ============================================================================


class TestSingleTurnConversation:
    """测试: 单轮对话（无工具调用）"""

    @pytest.mark.asyncio
    async def test_text_only_response(self):
        events_list = []
        def on_event(ev):
            events_list.append(ev)

        llm = MockLLMProvider([[
            TextDelta(text="你好！"),
            TextDelta(text="我是 Exceler AI。"),
            Finish(reason="stop"),
        ]])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "你好", on_event)

        assert any(isinstance(e, EvTextStart) for e in events_list)
        assert any(isinstance(e, EvTextEnd) for e in events_list)
        assert any(isinstance(e, EvDone) for e in events_list)
        assert len(result.messages) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_user_message_recorded(self):
        llm = MockLLMProvider([[
            TextDelta(text="ok"),
            Finish(reason="stop"),
        ]])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "显示数据")

        assert result.messages[0].role == "user"
        assert result.messages[0].content == "显示数据"


class TestToolCallConversation:
    """测试: 工具调用"""

    @pytest.mark.asyncio
    async def test_single_tool_call(self):
        events_list = []
        def on_event(ev):
            events_list.append(ev)

        # 第一轮: LLM 调用 echo 工具
        # 第二轮: LLM 生成最终回复
        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="echo"),
                ToolCallDelta(id="tc_1", args_delta='{"text":'),
                ToolCallDelta(id="tc_1", args_delta='"hello"}'),
                ToolCallEnd(id="tc_1", name="echo", arguments='{"text":"hello"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="Echo: hello"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "测试 echo", on_event)

        # 应有: user, assistant(tool_call), tool_result, assistant(text)
        assert len(result.messages) == 4
        assert result.messages[1].role == "assistant"
        assert result.messages[1].tool_calls is not None
        assert result.messages[2].role == "tool"
        assert result.messages[3].role == "assistant"
        assert result.messages[3].content == "Echo: hello"

        # 事件检查
        tool_starts = [e for e in events_list if isinstance(e, EvToolCallStart)]
        tool_ends = [e for e in events_list if isinstance(e, EvToolCallEnd)]
        assert len(tool_starts) == 1
        assert tool_starts[0].name == "echo"
        assert len(tool_ends) == 1
        assert tool_ends[0].result == {"echo": "hello"}

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_turn(self):
        events_list = []
        def on_event(ev):
            events_list.append(ev)

        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="echo"),
                ToolCallEnd(id="tc_1", name="echo", arguments='{"text":"a"}'),
                ToolCallStart(id="tc_2", name="echo"),
                ToolCallEnd(id="tc_2", name="echo", arguments='{"text":"b"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="done"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "test", on_event)

        # user + assistant(2 tool_calls) + tool_result_1 + tool_result_2 + assistant(text)
        assert len(result.messages) == 5
        assert len(result.messages[1].tool_calls) == 2


class TestToolError:
    """测试: 工具执行失败"""

    @pytest.mark.asyncio
    async def test_tool_error_returned_to_llm(self):
        events_list = []
        def on_event(ev):
            events_list.append(ev)

        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="fail_tool"),
                ToolCallEnd(id="tc_1", name="fail_tool", arguments='{"reason":"test error"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="抱歉，出错了"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "test", on_event)

        # 错误应作为 tool_result 传回
        tool_results = [e for e in events_list if isinstance(e, EvToolCallEnd)]
        assert len(tool_results) == 1
        assert tool_results[0].error is not None
        assert "test error" in tool_results[0].error

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="nonexistent"),
                ToolCallEnd(id="tc_1", name="nonexistent", arguments='{}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="ok"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "test")
        # 工具不存在，错误传回 LLM，LLM 继续回复
        assert len(result.messages) == 4


class TestHooks:
    """测试: Hook 系统"""

    @pytest.mark.asyncio
    async def test_before_hook_cancels(self):
        events_list = []
        def on_event(ev):
            events_list.append(ev)

        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="write_test"),
                ToolCallEnd(id="tc_1", name="write_test", arguments='{"data":"test"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="cancelled"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)

        # 注册一个取消写入的 hook
        engine.hooks.register_before("write_test", lambda call: None)

        state = ConversationState(session_id="test")
        result = await engine.chat(state, "test", on_event)

        tool_ends = [e for e in events_list if isinstance(e, EvToolCallEnd)]
        assert tool_ends[0].error is not None
        assert "取消" in tool_ends[0].error

    @pytest.mark.asyncio
    async def test_before_hook_modifies_args(self):
        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="echo"),
                ToolCallEnd(id="tc_1", name="echo", arguments='{"text":"original"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="done"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)

        # hook 修改参数
        def modify_args(call):
            call.arguments["text"] = "modified"
            return call

        engine.hooks.register_before("echo", modify_args)

        events_list = []
        def on_event(ev):
            events_list.append(ev)

        state = ConversationState(session_id="test")
        result = await engine.chat(state, "test", on_event)

        # echo 工具应该收到 "modified"
        tool_ends = [e for e in events_list if isinstance(e, EvToolCallEnd)]
        assert tool_ends[0].result == {"echo": "modified"}

    @pytest.mark.asyncio
    async def test_after_hook_called(self):
        after_calls = []

        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="echo"),
                ToolCallEnd(id="tc_1", name="echo", arguments='{"text":"hi"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="done"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)
        engine.hooks.register_after("echo", lambda call, result: after_calls.append((call.name, result)))

        state = ConversationState(session_id="test")
        await engine.chat(state, "test")

        assert len(after_calls) == 1
        assert after_calls[0][0] == "echo"
        assert after_calls[0][1].result == {"echo": "hi"}


class TestDoomLoop:
    """测试: Doom loop 检测"""

    @pytest.mark.asyncio
    async def test_doom_loop_detected(self):
        events_list = []
        def on_event(ev):
            events_list.append(ev)

        # LLM 连续 3 次调用相同工具相同参数
        repeated_call = [
            ToolCallStart(id="tc_1", name="echo"),
            ToolCallEnd(id="tc_1", name="echo", arguments='{"text":"same"}'),
            Finish(reason="tool_use"),
        ]

        llm = MockLLMProvider([repeated_call, repeated_call, repeated_call])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "test", on_event)

        errors = [e for e in events_list if isinstance(e, EvError)]
        assert len(errors) >= 1
        assert "doom loop" in errors[0].message.lower()


class TestCancellation:
    """测试: 中断"""

    @pytest.mark.asyncio
    async def test_cancel_stops_loop(self):
        events_list = []
        cancel_done = asyncio.Event()

        def on_event(ev):
            events_list.append(ev)
            if isinstance(ev, EvToolCallEnd) and not cancel_done.is_set():
                engine.cancel()
                cancel_done.set()

        # LLM 会调用工具（触发 tool call 循环），然后我们取消
        llm = MockLLMProvider([
            [
                ToolCallStart(id="tc_1", name="echo"),
                ToolCallEnd(id="tc_1", name="echo", arguments='{"text":"a"}'),
                Finish(reason="tool_use"),
            ],
            [
                TextDelta(text="done"),
                Finish(reason="stop"),
            ],
        ])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "test", on_event)

        # 取消后应收到错误事件
        errors = [e for e in events_list if isinstance(e, EvError)]
        assert len(errors) >= 1


class TestTokenTracking:
    """测试: Token 统计"""

    @pytest.mark.asyncio
    async def test_tokens_accumulated(self):
        llm = MockLLMProvider([[
            TextDelta(text="hi"),
            Finish(reason="stop"),
        ]])

        engine = _make_engine(llm)
        state = ConversationState(session_id="test")

        result = await engine.chat(state, "test")
        assert hasattr(result, "total_tokens")


class TestPromptBuilder:
    """测试: Prompt 构建"""

    @staticmethod
    def _extract_text(prompt) -> str:
        """Extract text from prompt (string or content blocks list)."""
        if isinstance(prompt, str):
            return prompt
        # Content blocks: [{"type": "text", "text": "..."}, ...]
        return " ".join(b.get("text", "") for b in prompt if isinstance(b, dict))

    def test_system_prompt_contains_intro(self):
        builder = PromptBuilder()
        ctx = PromptContext()
        prompt = builder.build_system_prompt(ctx)
        text = self._extract_text(prompt)

        assert "Exceler AI" in text
        assert "tool" in text.lower()

    def test_system_prompt_with_file_paths(self):
        builder = PromptBuilder()
        ctx = PromptContext(
            file_paths={"f001": "/data/report.xlsx"},
            db_paths={"f001": "/cache/f001.duckdb"},
        )
        prompt = builder.build_system_prompt(ctx)
        text = self._extract_text(prompt)
        assert "/data/report.xlsx" in text
        assert "/cache/f001.duckdb" in text

    def test_system_prompt_with_schema(self):
        builder = PromptBuilder()
        ctx = PromptContext(
            schemas={"f001": {"sheets": [{"name": "Sheet1", "columns": [{"name": "A", "type": "str"}], "row_count": 100}]}},
        )
        prompt = builder.build_system_prompt(ctx)
        text = self._extract_text(prompt)
        assert "Sheet1" in text

    def test_builder_pattern_renders_sections(self):
        prompt = (
            SystemPromptBuilder()
            .with_environment("2026-04-14", "/work")
            .with_file_context(PromptContext(
                file_paths={"f1": "/path/to/file.xlsx"},
            ))
            .render()
        )
        # Static sections
        assert "Exceler AI" in prompt
        assert "# System" in prompt
        assert "# Doing tasks" in prompt
        assert "# Excel expertise" in prompt
        assert "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__" in prompt
        # Dynamic sections
        assert "2026-04-14" in prompt
        assert "/work" in prompt
        assert "/path/to/file.xlsx" in prompt

    def test_dynamic_boundary_present(self):
        from agent.prompt_builder import DYNAMIC_BOUNDARY
        prompt = SystemPromptBuilder().render()
        assert DYNAMIC_BOUNDARY in prompt


class TestToolRegistry:
    """测试: 工具注册"""

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = EchoTool()
        registry.register(tool)

        assert registry.get_tool("echo") is not None
        assert "echo" in registry.list_tools()

    def test_get_definitions_returns_all(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(WriteTool())

        defs = registry.get_definitions()
        names = [d["function"]["name"] for d in defs]
        assert "echo" in names
        assert "write_test" in names

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        registry = ToolRegistry()
        registry.register(EchoTool())

        result = await registry.execute("echo", {"text": "hi"})
        assert result.result == {"echo": "hi"}
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert result.error is not None
        assert not result.success
