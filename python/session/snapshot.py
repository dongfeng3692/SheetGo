"""SnapshotManager — 操作快照管理"""

from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from pathlib import Path

from .database import Database
from .models import SnapshotRecord, new_id, now_iso


def _file_hash(path: str) -> str:
    """计算文件的 SHA256 hash"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _zipfile_content_hash(zip_path: str, inner_path: str) -> str:
    """计算 xlsx 内某个文件的 SHA256"""
    h = hashlib.sha256()
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            h.update(zf.read(inner_path))
        except KeyError:
            pass
    return h.hexdigest()


def compute_diff(source_path: str, working_path: str) -> dict:
    """计算两个 xlsx 文件的 zipfile 级 diff

    返回:
        {
            "added_files": [...],
            "deleted_files": [...],
            "modified_files": {filename: {"source_hash": ..., "working_hash": ...}}
        }
    """
    diff: dict = {
        "added_files": [],
        "deleted_files": [],
        "modified_files": {},
    }

    source_files: set[str] = set()
    working_files: set[str] = set()

    try:
        with zipfile.ZipFile(source_path, "r") as zf:
            source_files = set(zf.namelist())
    except (zipfile.BadZipFile, FileNotFoundError):
        pass

    try:
        with zipfile.ZipFile(working_path, "r") as zf:
            working_files = set(zf.namelist())
    except (zipfile.BadZipFile, FileNotFoundError):
        pass

    diff["added_files"] = sorted(working_files - source_files)
    diff["deleted_files"] = sorted(source_files - working_files)

    # 比较共同文件的内容
    common = source_files & working_files
    for name in sorted(common):
        s_hash = _zipfile_content_hash(source_path, name)
        w_hash = _zipfile_content_hash(working_path, name)
        if s_hash != w_hash:
            diff["modified_files"][name] = {
                "source_hash": s_hash,
                "working_hash": w_hash,
            }

    return diff


class SnapshotManager:
    """操作快照管理"""

    def __init__(self, db: Database, workspace_root: str):
        self.db = db
        self.workspace_root = Path(workspace_root)

    def _snapshot_dir(self, session_id: str) -> Path:
        d = self.workspace_root / session_id / "snapshots"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _snapshot_file_path(self, session_id: str, snapshot_id: str) -> Path:
        return self._snapshot_dir(session_id) / f"{snapshot_id}.xlsx"

    def create_snapshot(
        self,
        session_id: str,
        file_id: str,
        description: str,
        source_path: str,
        working_path: str,
        tool_calls: list[dict] | None = None,
    ) -> SnapshotRecord:
        """创建快照

        1. 计算 working 文件的 hash
        2. 比较 source 和 working 的 zipfile 内容差异
        3. 保存 diff 和元信息到数据库
        4. 复制 working 文件到快照目录
        """
        snap_id = new_id()
        ts = now_iso()

        # 获取上一个快照作为 parent
        parent = self.db.get_latest_snapshot(session_id, file_id)
        parent_id = parent.id if parent else None

        # 计算 hash 和 diff
        file_hash = _file_hash(working_path)
        diff = compute_diff(source_path, working_path)

        # 复制 working 文件到快照目录
        snap_file = self._snapshot_file_path(session_id, snap_id)
        shutil.copy2(working_path, snap_file)

        snap = SnapshotRecord(
            id=snap_id,
            session_id=session_id,
            file_id=file_id,
            parent_id=parent_id,
            description=description,
            tool_calls=tool_calls,
            diff=diff,
            file_hash=file_hash,
            created_at=ts,
        )
        self.db.create_snapshot(snap)
        return snap

    def list_snapshots(
        self, session_id: str, file_id: str | None = None
    ) -> list[SnapshotRecord]:
        """列出快照（时间线）"""
        if file_id:
            return self.db.get_snapshot_chain(session_id, file_id)
        # 列出该 session 所有快照
        rows = self.db.conn.execute(
            "SELECT * FROM snapshots WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self.db._row_to_snapshot(r) for r in rows]

    def get_snapshot_diff(self, snapshot_id: str) -> dict:
        """获取快照的 diff 详情"""
        snap = self.db.get_snapshot(snapshot_id)
        if not snap:
            return {}
        return snap.diff

    def get_snapshot_file(self, session_id: str, snapshot_id: str) -> Path:
        """获取快照文件路径"""
        return self._snapshot_file_path(session_id, snapshot_id)
