"""Session Store — 数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def new_id() -> str:
    """生成 UUID"""
    return uuid4().hex[:16]


def now_iso() -> str:
    """当前 UTC 时间 ISO 格式"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Session:
    id: str
    name: str
    created_at: str
    updated_at: str
    agent_type: str = "main"
    settings: dict = field(default_factory=dict)
    total_tokens: int = 0
    total_cost: float = 0.0


@dataclass
class MessageRecord:
    id: str
    session_id: str
    role: str              # "user" | "assistant" | "tool_result" | "system"
    content: str
    tool_calls: list[dict] | None = None
    tool_results: list[dict] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: str = ""


@dataclass
class SnapshotRecord:
    id: str
    session_id: str
    file_id: str
    parent_id: str | None = None
    description: str = ""
    tool_calls: list[dict] | None = None
    diff: dict = field(default_factory=dict)
    file_hash: str = ""
    created_at: str = ""


@dataclass
class MemoryEntry:
    id: str
    session_id: str
    category: str          # "preference" | "pattern" | "context"
    key: str
    value: Any = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class FileRecord:
    file_id: str
    session_id: str
    file_name: str
    file_size: int
    file_hash: str
    file_type: str
    source_path: str
    working_path: str
    created_at: str = ""
    preload_status: str = "pending"
