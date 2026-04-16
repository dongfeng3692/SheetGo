"""File manager: import, list, remove, export with hash, format detection, DB records."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..session.database import Database
from ..session.models import FileRecord, now_iso


class FileError(Exception):
    """File management error."""


@dataclass
class FileUploadResult:
    """Result of a file import operation."""
    file_id: str
    session_id: str
    file_name: str
    file_size: int
    file_hash: str
    file_type: str
    source_path: str
    working_path: str
    preload_status: str = "pending"
    created_at: str = ""
    duplicate_of: str | None = None  # set if duplicate detected

    def to_dict(self) -> dict[str, Any]:
        d = {
            "fileId": self.file_id,
            "sessionId": self.session_id,
            "fileName": self.file_name,
            "fileSize": self.file_size,
            "fileHash": self.file_hash,
            "fileType": self.file_type,
            "sourcePath": self.source_path,
            "workingPath": self.working_path,
            "preloadStatus": self.preload_status,
            "createdAt": self.created_at,
        }
        if self.duplicate_of:
            d["duplicateOf"] = self.duplicate_of
        return d


class FileManager:
    """File import, storage, and lifecycle management."""

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

    def __init__(self, db: Database) -> None:
        self.db = db

    def import_file(
        self,
        session_id: str,
        file_id: str,
        file_name: str,
        source_path: str,
        working_path: str,
    ) -> FileUploadResult:
        """Process an imported file: hash, format, DB record.

        Called after Rust has already copied the file to source/ and working/.
        """
        # Validate file exists
        if not os.path.isfile(working_path):
            raise FileError(f"Working file not found: {working_path}")

        file_size = os.path.getsize(working_path)
        if file_size > self.MAX_FILE_SIZE:
            raise FileError(
                f"File too large: {file_size} bytes (max {self.MAX_FILE_SIZE})"
            )

        # Compute hash
        file_hash = self.compute_hash(working_path)

        # Detect format
        file_type = self.detect_format(working_path)
        if file_type == "unknown":
            raise FileError(f"Unsupported file format: {file_name}")

        # Check for duplicates in same session
        existing = self._find_by_hash(session_id, file_hash)
        if existing is not None:
            return FileUploadResult(
                file_id=file_id,
                session_id=session_id,
                file_name=file_name,
                file_size=file_size,
                file_hash=file_hash,
                file_type=file_type,
                source_path=source_path,
                working_path=working_path,
                preload_status="duplicate",
                created_at=now_iso(),
                duplicate_of=existing.file_id,
            )

        # Record in DB
        record = FileRecord(
            file_id=file_id,
            session_id=session_id,
            file_name=file_name,
            file_size=file_size,
            file_hash=file_hash,
            file_type=file_type,
            source_path=source_path,
            working_path=working_path,
            preload_status="pending",
        )
        self.db.save_file_record(record)

        return FileUploadResult(
            file_id=file_id,
            session_id=session_id,
            file_name=file_name,
            file_size=file_size,
            file_hash=file_hash,
            file_type=file_type,
            source_path=source_path,
            working_path=working_path,
            preload_status="pending",
            created_at=record.created_at,
        )

    def list_files(self, session_id: str) -> list[FileUploadResult]:
        """List all files for a session."""
        records = self.db.list_file_records(session_id)
        return [self._record_to_result(r) for r in records]

    def get_file_info(self, file_id: str) -> FileUploadResult | None:
        """Get info for a single file."""
        record = self.db.get_file_record(file_id)
        if record is None:
            return None
        return self._record_to_result(record)

    def remove_file(self, file_id: str, session_id: str) -> None:
        """Remove a file: delete from disk and DB."""
        record = self.db.get_file_record(file_id)
        if record is None:
            raise FileError(f"File not found: {file_id}")

        # Delete source, working, and cache files
        for path in [record.source_path, record.working_path]:
            if path and os.path.isfile(path):
                os.remove(path)

        # Delete cache files (duckdb, schema.json, stats.json)
        base_dir = os.path.dirname(os.path.dirname(record.working_path))
        cache_dir = os.path.join(base_dir, "cache") if base_dir else None
        if cache_dir and os.path.isdir(cache_dir):
            for fname in os.listdir(cache_dir):
                if fname.startswith(file_id + ".") or fname.startswith(file_id + "_"):
                    os.remove(os.path.join(cache_dir, fname))

        # Delete from DB
        self.db.conn.execute(
            "DELETE FROM file_records WHERE file_id = ?", (file_id,)
        )
        self.db.conn.commit()

    def export_file(self, file_id: str, dest_path: str) -> None:
        """Export working copy to destination path."""
        record = self.db.get_file_record(file_id)
        if record is None:
            raise FileError(f"File not found: {file_id}")
        if not os.path.isfile(record.working_path):
            raise FileError(f"Working file missing: {record.working_path}")
        shutil.copy2(record.working_path, dest_path)

    def update_preload_status(self, file_id: str, status: str) -> None:
        """Update preload status in DB."""
        self.db.update_preload_status(file_id, status)

    # -- static helpers --------------------------------------------------

    @staticmethod
    def compute_hash(path: str) -> str:
        """Compute SHA-256 hash of a file (streaming, memory-efficient)."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def detect_format(path: str) -> str:
        """Detect file format from extension and magic bytes.

        Returns: "xlsx" | "xlsm" | "csv" | "tsv" | "unknown"
        """
        ext = Path(path).suffix.lower()

        if ext in (".xlsx", ".xlsm"):
            # Validate ZIP magic bytes (PK\x03\x04)
            try:
                with open(path, "rb") as f:
                    magic = f.read(4)
                if magic[:2] != b"PK":
                    return "unknown"
            except OSError:
                return "unknown"
            return ext[1:]  # "xlsx" or "xlsm"

        if ext == ".csv":
            return "csv"
        if ext == ".tsv":
            return "tsv"

        return "unknown"

    # -- private ---------------------------------------------------------

    def _find_by_hash(self, session_id: str, file_hash: str) -> FileRecord | None:
        """Find existing file with same hash in same session."""
        rows = self.db.conn.execute(
            "SELECT * FROM file_records WHERE session_id = ? AND file_hash = ?",
            (session_id, file_hash),
        ).fetchall()
        if rows:
            return self.db._row_to_file_record(rows[0])
        return None

    @staticmethod
    def _record_to_result(record: FileRecord) -> FileUploadResult:
        return FileUploadResult(
            file_id=record.file_id,
            session_id=record.session_id,
            file_name=record.file_name,
            file_size=record.file_size,
            file_hash=record.file_hash,
            file_type=record.file_type,
            source_path=record.source_path,
            working_path=record.working_path,
            preload_status=record.preload_status,
            created_at=record.created_at,
        )
