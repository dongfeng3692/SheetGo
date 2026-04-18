"""Agent Core — 数据模型"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# ChatEvent — LLM 流式响应事件
# ============================================================================


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCallStart:
    id: str
    name: str


@dataclass
class ToolCallDelta:
    id: str
    args_delta: str


@dataclass
class ToolCallEnd:
    id: str
    name: str
    arguments: str


@dataclass
class UsageEvent:
    input_tokens: int
    output_tokens: int


@dataclass
class Finish:
    reason: str  # "stop" | "tool_use"


# Union type
ChatEvent = TextDelta | ToolCallStart | ToolCallDelta | ToolCallEnd | UsageEvent | Finish


# ============================================================================
# AgentEvent — 回调给 UI/调用方的事件
# ============================================================================


@dataclass
class EvTextStart:
    pass


@dataclass
class EvTextDelta:
    text: str


@dataclass
class EvTextEnd:
    full_text: str


@dataclass
class EvToolCallStart:
    id: str
    name: str


@dataclass
class EvToolCallProgress:
    id: str
    message: str


@dataclass
class EvToolCallEnd:
    id: str
    name: str
    result: Any
    error: str | None = None


@dataclass
class EvError:
    message: str


@dataclass
class EvDone:
    pass


AgentEvent = EvTextStart | EvTextDelta | EvTextEnd | EvToolCallStart | EvToolCallProgress | EvToolCallEnd | EvError | EvDone


# ============================================================================
# 核心数据结构
# ============================================================================


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    call_id: str
    name: str
    result: Any = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_message(self) -> dict:
        """转换为 LLM tool_result 消息格式"""
        content = self.error if self.error else str(self.result)
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "content": content,
        }


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Message:
    id: str
    role: str  # "user" | "assistant" | "tool_result" | "system"
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None
    timestamp: str = ""
    tokens: TokenUsage | None = None

    def to_llm_message(self) -> dict:
        """转换为 LLM API 消息格式"""
        msg: dict[str, Any] = {"role": self.role}

        if self.role == "assistant" and self.tool_calls:
            msg["content"] = self.content or None
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False) if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        elif self.role == "tool" and self.tool_results:
            # 单个 tool result
            tr = self.tool_results[0]
            msg["tool_call_id"] = tr.call_id
            if tr.error:
                msg["content"] = json.dumps({"error": tr.error}, ensure_ascii=False)
            else:
                msg["content"] = str(tr.result)
        else:
            msg["content"] = self.content

        return msg


@dataclass
class ConversationState:
    session_id: str
    file_ids: list[str] = field(default_factory=list)
    file_paths: dict[str, str] = field(default_factory=dict)     # file_id → working_path
    db_paths: dict[str, str] = field(default_factory=dict)        # file_id → duckdb_path
    schemas: dict[str, dict] = field(default_factory=dict)        # file_id → schema.json
    samples: dict[str, dict] = field(default_factory=dict)        # file_id → sample rows
    structures: dict[str, dict] = field(default_factory=dict)     # file_id → structure.json
    messages: list[Message] = field(default_factory=list)
    total_tokens: int = 0
    workspace_dir: str = ""                                       # session workspace path


@dataclass
class ChatResponse:
    """非流式 LLM 响应"""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str = "stop"
