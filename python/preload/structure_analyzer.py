"""StructureAnalyzer — analyze Excel file structure using LLM.

Reads first 200 rows of each sheet via calamine (raw, no header promotion),
sends to LLM for structure analysis, outputs structured JSON.

Cached as {file_id}_structure.json in the workspace cache directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..excel.reader import ExcelReader
from .structure_llm import StructureLLMCaller


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Region:
    """A detected region within a sheet."""

    type: str          # "table" | "form" | "mixed" | "blank"
    name: str
    start_cell: str    # e.g. "A1"
    end_cell: str      # e.g. "F20"
    header_row: int | None
    row_count: int
    col_count: int
    columns: list[dict] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "type": self.type,
            "name": self.name,
            "startCell": self.start_cell,
            "endCell": self.end_cell,
            "rowCount": self.row_count,
            "colCount": self.col_count,
            "notes": self.notes,
        }
        if self.header_row is not None:
            d["headerRow"] = self.header_row
        if self.columns:
            d["columns"] = self.columns
        if self.fields:
            d["fields"] = self.fields
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Region:
        return cls(
            type=d.get("type", "mixed"),
            name=d.get("name", ""),
            start_cell=d.get("startCell", "A1"),
            end_cell=d.get("endCell", "A1"),
            header_row=d.get("headerRow"),
            row_count=d.get("rowCount", 0),
            col_count=d.get("colCount", 0),
            columns=d.get("columns", []),
            fields=d.get("fields", []),
            notes=d.get("notes", ""),
        )


@dataclass
class SheetStructure:
    """Structure analysis for a single sheet."""

    name: str
    layout: str        # "single_table" | "multi_table" | "form" | "mixed"
    description: str
    regions: list[Region] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "layout": self.layout,
            "description": self.description,
            "regions": [r.to_dict() for r in self.regions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SheetStructure:
        return cls(
            name=d.get("name", ""),
            layout=d.get("layout", "mixed"),
            description=d.get("description", ""),
            regions=[Region.from_dict(r) for r in d.get("regions", [])],
        )


@dataclass
class StructureResult:
    """Structure analysis result for an entire file."""

    file_id: str
    status: str        # "ok" | "skipped"
    sheets: list[SheetStructure] = field(default_factory=list)
    analysis_source: str = "llm"
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "fileId": self.file_id,
            "status": self.status,
            "sheets": [s.to_dict() for s in self.sheets],
            "analysisSource": self.analysis_source,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StructureResult:
        return cls(
            file_id=d.get("fileId", ""),
            status=d.get("status", "skipped"),
            sheets=[SheetStructure.from_dict(s) for s in d.get("sheets", [])],
            analysis_source=d.get("analysisSource", "llm"),
            timestamp=d.get("timestamp", ""),
        )


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class StructureAnalyzer:
    """Analyze Excel file structure using LLM.

    Usage:
        result = StructureAnalyzer.analyze(
            file_id="abc123",
            file_path="/path/to/file.xlsx",
            api_key="sk-ant-...",
            merged_cells_map={"Sheet1": ["A1:C1", ...]},
            schema_summary={"Sheet1": {"columns": [...], ...}},
        )
    """

    MAX_ROWS = 200

    @classmethod
    def analyze(
        cls,
        file_id: str,
        file_path: str,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
        merged_cells_map: dict[str, list[str]] | None = None,
        schema_summary: dict[str, dict] | None = None,
    ) -> StructureResult:
        """Analyze file structure via LLM.

        Returns StructureResult. On failure, returns with status="skipped".
        """
        now = datetime.now(timezone.utc).isoformat()

        if not api_key:
            return StructureResult(
                file_id=file_id,
                status="skipped",
                timestamp=now,
            )

        # 1. Read raw data (no header promotion)
        try:
            raw_sheets = cls._read_raw_sheets(file_path)
        except Exception:
            return StructureResult(
                file_id=file_id,
                status="skipped",
                timestamp=now,
            )

        if not raw_sheets:
            return StructureResult(
                file_id=file_id,
                status="ok",
                sheets=[],
                timestamp=now,
            )

        # 2. Call LLM for analysis
        caller = StructureLLMCaller(api_key=api_key, model=model, base_url=base_url)
        result = caller.analyze(
            raw_sheets=raw_sheets,
            merged_cells_map=merged_cells_map or {},
            schema_summary=schema_summary or {},
            max_rows=cls.MAX_ROWS,
        )

        if result is None:
            return StructureResult(
                file_id=file_id,
                status="skipped",
                timestamp=now,
            )

        # 3. Parse LLM response into StructureResult
        try:
            sheets = [
                SheetStructure.from_dict(s)
                for s in result.get("sheets", [])
            ]
            return StructureResult(
                file_id=file_id,
                status="ok",
                sheets=sheets,
                analysis_source="llm",
                timestamp=now,
            )
        except Exception:
            return StructureResult(
                file_id=file_id,
                status="skipped",
                timestamp=now,
            )

    @classmethod
    def _read_raw_sheets(cls, file_path: str) -> dict[str, list[list[Any]]]:
        """Read raw sheet data via calamine (no header promotion).

        Returns {sheet_name: [[row1_col1, row1_col2, ...], [row2_col1, ...]]}
        """
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(file_path)
        result: dict[str, list[list[Any]]] = {}
        for name in wb.sheet_names:
            data = wb.get_sheet_by_name(name).to_python()
            if data:
                result[name] = data[:cls.MAX_ROWS]
            else:
                result[name] = []
        return result
