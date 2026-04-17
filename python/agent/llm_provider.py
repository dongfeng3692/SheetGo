"""LLMProvider — Anthropic 原生格式的 LLM 接口

直接使用 anthropic SDK，不走 litellm。
内部消息格式保持 OpenAI 兼容（engine 层使用），provider 负责 Anthropic 格式转换。

格式转换要点:
  - system 消息从 messages 中提取为独立参数
  - tool_calls → tool_use content blocks
  - tool role → user + tool_result content blocks
  - 流式解析 content_block_delta 事件
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from .models import (
    ChatEvent,
    ChatResponse,
    Finish,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    TokenUsage,
    UsageEvent,
)


@dataclass
class LLMConfig:
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 4096
    thinking_budget: int = 10000  # extended thinking budget tokens (0=off)


class LLMProvider:
    """Anthropic 原生 LLM 接口"""

    def __init__(self, config: LLMConfig):
        self.config = config

    # ------------------------------------------------------------------ #
    #  消息格式转换: OpenAI → Anthropic
    # ------------------------------------------------------------------ #

    @staticmethod
    def _convert_messages(messages: list[dict]) -> tuple[str | list[dict], list[dict]]:
        """将内部消息格式转为 Anthropic API 格式

        Returns: (system_prompt, anthropic_messages)
        system_prompt can be a string or a list of content blocks with cache_control.
        """
        system: str | list[dict] = ""
        result: list[dict] = []

        for msg in messages:
            role = msg.get("role", "user")

            if role == "system":
                content = msg.get("content", "")
                # Support content blocks (list of dicts with cache_control) or plain string
                if isinstance(content, list):
                    system = content
                else:
                    system = content or ""
                continue

            if role == "user":
                result.append({
                    "role": "user",
                    "content": msg.get("content", ""),
                })

            elif role == "assistant":
                content_blocks: list[dict] = []

                # 文本内容
                text = msg.get("content")
                if text:
                    content_blocks.append({"type": "text", "text": text})

                # 工具调用 → tool_use blocks
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        # Anthropic 要求 input 为 dict，不是 JSON 字符串
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, TypeError):
                                args = {}
                        if not isinstance(args, dict):
                            args = {}
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args,
                        })

                if content_blocks:
                    result.append({"role": "assistant", "content": content_blocks})
                else:
                    result.append({"role": "assistant", "content": ""})

            elif role == "tool":
                # OpenAI tool result → Anthropic user + tool_result block
                tool_call_id = msg.get("tool_call_id", "")
                content = msg.get("content", "")
                is_error = False
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and "error" in parsed:
                            is_error = True
                    except (json.JSONDecodeError, TypeError):
                        pass

                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content,
                        "is_error": is_error,
                    }],
                })

        return system, result

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """将 OpenAI function calling 格式转为 Anthropic tools 格式"""
        result = []
        for tool in tools:
            func = tool.get("function", {})
            result.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return result

    def _get_client(self) -> Any:
        """创建或获取 Anthropic async client"""
        import httpx
        import anthropic
        return anthropic.AsyncAnthropic(
            api_key=self.config.api_key or None,
            base_url=self.config.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    # ------------------------------------------------------------------ #
    #  重试逻辑
    # ------------------------------------------------------------------ #

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}
    _MAX_RETRIES = 4
    _RETRY_DELAYS = [10, 30, 60, 120]  # seconds

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        """判断是否为可重试的 API 错误"""
        exc_name = type(exc).__name__
        msg = str(exc).lower()
        # Anthropic SDK 异常
        if hasattr(exc, "status_code") and exc.status_code in LLMProvider._RETRYABLE_STATUS_CODES:
            return True
        # 连接错误
        if "remoteprotocolerror" in exc_name.lower() or "connectionerror" in exc_name.lower():
            return True
        if "overloaded" in msg:
            return True
        # 网络错误 (MiniMax 等)
        if "network error" in msg:
            return True
        # API error with retryable status (wrapped in dict)
        if "error" in msg and any(
            f"'{code}'" in msg or str(code) in msg
            for code in LLMProvider._RETRYABLE_STATUS_CODES
        ):
            return True
        return False

    # ------------------------------------------------------------------ #
    #  流式调用（含自动重试）
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[ChatEvent]:
        """流式调用 Claude，yield ChatEvent（含自动重试）"""
        import asyncio as _asyncio

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                async for event in self._stream_once(messages, tools):
                    yield event
                return
            except Exception as exc:
                if attempt < self._MAX_RETRIES and self._is_retryable_error(exc):
                    delay = self._RETRY_DELAYS[attempt]
                    import sys
                    print(f"           [RETRY] attempt {attempt+1}/{self._MAX_RETRIES}, waiting {delay}s... ({exc})",
                          file=sys.stderr)
                    await _asyncio.sleep(delay)
                    continue
                raise

    async def _stream_once(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> AsyncIterator[ChatEvent]:
        """单次流式调用（不含重试）"""
        client = self._get_client()

        system, anthropic_msgs = self._convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system,
            "messages": anthropic_msgs,
        }

        # Extended thinking (Claude only, temperature must be 1 when enabled)
        if self.config.thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.config.thinking_budget}
            kwargs["temperature"] = 1.0
        else:
            kwargs["temperature"] = self.config.temperature

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # 流式解析状态
        current_tool_id = ""
        current_tool_name = ""
        current_tool_input = ""
        tool_ids_emitted: set[str] = set()

        async with client.messages.stream(**kwargs) as stream_resp:
            async for event in stream_resp:
                # message_start: usage
                if event.type == "message_start":
                    usage = getattr(event.message, "usage", None)
                    if usage:
                        yield UsageEvent(
                            input_tokens=getattr(usage, "input_tokens", 0) or 0,
                            output_tokens=getattr(usage, "output_tokens", 0) or 0,
                        )

                # content_block_start: 新的文本块或工具调用
                elif event.type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block:
                        if block.type == "thinking":
                            pass  # skip thinking blocks
                        elif block.type == "tool_use":
                            current_tool_id = block.id
                            current_tool_name = block.name
                            current_tool_input = ""
                            tool_ids_emitted.add(current_tool_id)
                            yield ToolCallStart(id=current_tool_id, name=current_tool_name)

                # content_block_delta: 增量内容
                elif event.type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        if delta.type == "thinking_delta":
                            pass  # skip thinking deltas
                        elif delta.type == "text_delta":
                            yield TextDelta(text=delta.text)
                        elif delta.type == "input_json_delta":
                            current_tool_input += delta.partial_json
                            yield ToolCallDelta(
                                id=current_tool_id,
                                args_delta=delta.partial_json,
                            )

                # content_block_stop: 一个 content block 结束
                elif event.type == "content_block_stop":
                    if current_tool_id and current_tool_id in tool_ids_emitted:
                        yield ToolCallEnd(
                            id=current_tool_id,
                            name=current_tool_name,
                            arguments=current_tool_input,
                        )
                        current_tool_id = ""
                        current_tool_name = ""
                        current_tool_input = ""

                # message_delta: 最终 usage + stop_reason
                elif event.type == "message_delta":
                    delta = getattr(event, "delta", None)
                    usage = getattr(event, "usage", None)

                    if usage:
                        yield UsageEvent(
                            input_tokens=0,
                            output_tokens=getattr(usage, "output_tokens", 0) or 0,
                        )

                    if delta and delta.stop_reason:
                        yield Finish(reason=delta.stop_reason)

        # 兜底：如果还有未关闭的 tool call
        if current_tool_id and current_tool_id in tool_ids_emitted:
            yield ToolCallEnd(
                id=current_tool_id,
                name=current_tool_name,
                arguments=current_tool_input,
            )

    # ------------------------------------------------------------------ #
    #  非流式调用（含自动重试）
    # ------------------------------------------------------------------ #

    async def chat_no_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        """非流式调用 Claude（含自动重试）"""
        import asyncio as _asyncio

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                return await self._call_once(messages, tools)
            except Exception as exc:
                if attempt < self._MAX_RETRIES and self._is_retryable_error(exc):
                    delay = self._RETRY_DELAYS[attempt]
                    import sys
                    print(f"           [RETRY] attempt {attempt+1}/{self._MAX_RETRIES}, waiting {delay}s... ({exc})",
                          file=sys.stderr)
                    await _asyncio.sleep(delay)
                    continue
                raise

    async def _call_once(
        self,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> ChatResponse:
        """单次非流式调用（不含重试）"""
        client = self._get_client()

        system, anthropic_msgs = self._convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system,
            "messages": anthropic_msgs,
        }

        # Extended thinking (Claude only, temperature must be 1 when enabled)
        if self.config.thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.config.thinking_budget}
            kwargs["temperature"] = 1.0
        else:
            kwargs["temperature"] = self.config.temperature

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await client.messages.create(**kwargs)

        content = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {"_raw": str(block.input)}
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=args))

        usage = TokenUsage()
        if response.usage:
            usage.input_tokens = response.usage.input_tokens or 0
            usage.output_tokens = response.usage.output_tokens or 0

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=response.stop_reason or "end_turn",
        )
