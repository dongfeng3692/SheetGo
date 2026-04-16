"""RollbackEngine — 回滚引擎"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from .database import Database
from .snapshot import SnapshotManager, _file_hash


@dataclass
class RollbackResult:
    success: bool
    snapshot_id: str
    restored_hash: str
    changes_lost: int       # 将丢失的修改数
    message: str


@dataclass
class RollbackPreview:
    snapshot_description: str
    changes_to_lose: list[str]      # ["添加了柱状图", "修改了标题"]
    changes_to_restore: list[str]   # 将恢复的修改描述


class RollbackEngine:
    """回滚引擎

    通过复制快照文件实现回滚，不删除后续快照（保留分支能力）。
    """

    def __init__(self, db: Database, snapshot_mgr: SnapshotManager):
        self.db = db
        self.snapshot_mgr = snapshot_mgr

    def rollback_to(
        self,
        session_id: str,
        file_id: str,
        snapshot_id: str,
        working_path: str,
    ) -> RollbackResult:
        """回滚到指定快照

        1. 从快照目录复制目标快照文件到 working
        2. 验证 hash
        3. 返回回滚结果
        """
        # 验证目标快照存在
        target = self.db.get_snapshot(snapshot_id)
        if not target:
            return RollbackResult(
                success=False,
                snapshot_id=snapshot_id,
                restored_hash="",
                changes_lost=0,
                message=f"快照 {snapshot_id} 不存在",
            )

        # 获取快照链以计算 changes_lost
        chain = self.db.get_snapshot_chain(session_id, file_id)
        target_idx = next(
            (i for i, s in enumerate(chain) if s.id == snapshot_id), -1
        )
        changes_lost = len(chain) - target_idx - 1 if target_idx >= 0 else 0

        # 复制快照文件到 working
        snap_file = self.snapshot_mgr.get_snapshot_file(session_id, snapshot_id)
        if not snap_file.exists():
            return RollbackResult(
                success=False,
                snapshot_id=snapshot_id,
                restored_hash="",
                changes_lost=changes_lost,
                message=f"快照文件不存在: {snap_file}",
            )

        shutil.copy2(snap_file, working_path)

        # 验证 hash
        actual_hash = _file_hash(working_path)
        expected_hash = target.file_hash
        hash_match = actual_hash == expected_hash

        return RollbackResult(
            success=hash_match,
            snapshot_id=snapshot_id,
            restored_hash=actual_hash,
            changes_lost=changes_lost,
            message=(
                f"已回滚到: {target.description}"
                if hash_match
                else f"回滚完成但 hash 不匹配（期望 {expected_hash[:8]}...，实际 {actual_hash[:8]}...）"
            ),
        )

    def get_rollback_preview(
        self, session_id: str, file_id: str, snapshot_id: str
    ) -> RollbackPreview | None:
        """预览回滚效果"""
        chain = self.db.get_snapshot_chain(session_id, file_id)
        target_idx = next(
            (i for i, s in enumerate(chain) if s.id == snapshot_id), -1
        )
        if target_idx < 0:
            return None

        target = chain[target_idx]

        # 将恢复的修改: chain[0] 到 chain[target_idx] 的描述
        changes_to_restore = [s.description for s in chain[: target_idx + 1]]

        # 将丢失的修改: chain[target_idx+1:] 的描述
        changes_to_lose = [s.description for s in chain[target_idx + 1 :]]

        return RollbackPreview(
            snapshot_description=target.description,
            changes_to_lose=changes_to_lose,
            changes_to_restore=changes_to_restore,
        )
