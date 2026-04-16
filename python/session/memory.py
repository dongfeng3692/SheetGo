"""MemoryManager — 分层记忆管理"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .database import Database
from .models import MessageRecord, new_id, now_iso


@runtime_checkable
class LLMProtocol(Protocol):
    """LLM 接口协议，供对话压缩使用。模块 6 实现后注入。"""

    async def chat(self, messages: list[dict]) -> str: ...


class MemoryManager:
    """分层记忆管理

    - 短期记忆: 内存中，构建 Prompt 时使用（最近 N 条消息）
    - 中期记忆: 对话压缩摘要（需要 LLM）
    - 长期记忆: 用户偏好和操作模式（SQLite memories 表）
    - 工作记忆: 当前工作簿状态（file_records）
    """

    def __init__(self, db: Database, llm: LLMProtocol | None = None):
        self.db = db
        self.llm = llm

    # ------------------------------------------------------------------ #
    #  短期记忆
    # ------------------------------------------------------------------ #

    def get_conversation_context(
        self, session_id: str, max_messages: int = 10
    ) -> list[dict]:
        """获取最近 N 条消息，格式化为 LLM 消息格式"""
        messages = self.db.get_recent_messages(session_id, count=max_messages)
        result: list[dict] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            if msg.tool_results:
                entry["tool_results"] = msg.tool_results
            result.append(entry)
        return result

    # ------------------------------------------------------------------ #
    #  中期记忆（对话压缩）
    # ------------------------------------------------------------------ #

    async def compact_conversation(
        self, session_id: str, keep_recent: int = 4
    ) -> str:
        """压缩对话历史

        1. 保留最近 keep_recent 条消息
        2. 将更早的消息发送给 LLM 生成摘要
        3. 将摘要保存为系统消息
        4. 删除已压缩的旧消息
        5. 返回摘要文本
        """
        messages = self.db.get_messages(session_id, limit=10000)
        if len(messages) <= keep_recent + 5:
            return ""

        if not self.llm:
            # 无 LLM 时只做简单裁剪，不生成摘要
            return ""

        to_compress = messages[:-keep_recent]

        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "请总结以下对话的关键信息，包括："
                    "用户需求、已完成的操作、当前文件状态。"
                    "保持简洁，不超过 200 字。"
                ),
            },
            *[self._format_message(m) for m in to_compress],
        ]

        summary = await self.llm.chat(summary_prompt)

        # 保存摘要为系统消息
        self.db.save_message(
            MessageRecord(
                id=new_id(),
                session_id=session_id,
                role="system",
                content=f"[对话摘要] {summary}",
                created_at=now_iso(),
            )
        )

        # 删除旧消息
        for m in to_compress:
            self.db.conn.execute(
                "DELETE FROM messages WHERE id = ?", (m.id,)
            )
        self.db.conn.commit()

        return summary

    @staticmethod
    def _format_message(msg: MessageRecord) -> dict:
        return {"role": msg.role, "content": msg.content}

    # ------------------------------------------------------------------ #
    #  长期记忆
    # ------------------------------------------------------------------ #

    def remember_preference(
        self, session_id: str, key: str, value: Any
    ) -> None:
        """记住用户偏好（如"喜欢使用中文列名"）"""
        self.db.save_memory(session_id, "preference", key, value)

    def get_preferences(self, session_id: str) -> dict:
        """获取所有用户偏好"""
        entries = self.db.list_memories(session_id, category="preference")
        return {e.key: e.value for e in entries}

    def remember_pattern(
        self, session_id: str, pattern: str, description: str
    ) -> None:
        """记住操作模式（如"用户经常做数据透视"）"""
        self.db.save_memory(session_id, "pattern", pattern, description)

    # ------------------------------------------------------------------ #
    #  工作记忆
    # ------------------------------------------------------------------ #

    def get_working_state(self, session_id: str) -> dict:
        """获取当前工作状态（哪些文件打开、preload 状态）"""
        records = self.db.list_file_records(session_id)
        files = []
        for r in records:
            files.append({
                "file_id": r.file_id,
                "file_name": r.file_name,
                "preload_status": r.preload_status,
            })
        return {"files": files}
