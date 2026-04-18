"""Preload pipeline: 10-step post-upload data extraction and caching."""

from __future__ import annotations

import json
import os
import shutil
import time
import traceback
from datetime import date, datetime, time as time_value
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..excel.duckdb_query import DuckDBQuery
from ..excel.reader import ExcelReader
from .formula_scanner import FormulaScanner, FormulaScanResult
from .schema_extractor import SchemaExtractor, SheetSchema
from .stats_calculator import FileStats, StatsCalculator
from .style_extractor import StyleExtractor, StyleIndex

# Progress callback: (stage, progress_pct, message, elapsed_ms)
ProgressCallback = Callable[[str, int, str, int], None]

STAGES = [
    "copying",    # 0
    "reading",    # 1
    "duckdb",     # 2
    "schema",     # 3
    "sampling",   # 4
    "stats",      # 5
    "formulas",   # 6
    "validation", # 7
    "styles",     # 8
    "structure",  # 9  — LLM structure analysis
    "done",       # 10
]

_STEP_WEIGHTS = [5, 15, 20, 15, 5, 10, 10, 10, 5, 5, 5]


@dataclass
class PreloadConfig:
    """Input configuration for a preload run."""
    file_id: str
    source_path: str
    working_path: str
    duckdb_path: str
    schema_path: str
    stats_path: str
    structure_path: str = ""       # path for structure analysis JSON
    sample_rows: int = 20
    max_stats_rows: int = 100_000
    run_validation: bool = False  # Module 05 not yet implemented


@dataclass
class PreloadResult:
    """Output of a preload run."""
    file_id: str
    status: str  # "ok" | "error"
    schema_path: str
    stats_path: str
    duckdb_path: str
    structure_path: str = ""
    duration_ms: int = 0
    error_message: str | None = None


class PreloadPipeline:
    """10-step preload pipeline: copy → read → DuckDB → schema → stats → formulas → styles → cache."""

    def __init__(self, config: PreloadConfig) -> None:
        self._config = config
        self._start_time: float = 0.0
        self._on_progress: ProgressCallback | None = None
        self._progress_accumulated: int = 0

    def run(
        self,
        on_progress: ProgressCallback | None = None,
    ) -> PreloadResult:
        """Execute the full preload pipeline. Synchronous."""
        self._on_progress = on_progress
        self._start_time = time.monotonic()
        cfg = self._config

        try:
            # Step 1: Copy source to working
            self._emit("copying", 0, "Copying file...")
            self._step_copy()

            # Step 2: Read all sheets
            self._emit("reading", 5, "Reading data...")
            data = self._step_read()

            # Step 3: Register to DuckDB
            self._emit("duckdb", 20, "Loading to DuckDB...")
            self._step_duckdb(data)

            # Step 4: Extract schema
            self._emit("schema", 40, "Extracting schema...")
            schemas = self._step_schema(data)

            # Step 5: Sample data (embedded in schema)
            self._emit("sampling", 55, "Extracting samples...")

            # Step 6: Compute stats
            self._emit("stats", 60, "Computing statistics...")
            stats = self._step_stats(data, schemas)

            # Step 7: Scan formulas
            self._emit("formulas", 70, "Scanning formulas...")
            formula_result = self._step_formulas()
            # Update formula info in schemas
            self._attach_formulas(schemas, formula_result)
            # Recompute stats with formula info
            stats = StatsCalculator.compute_file_stats(
                cfg.file_id, data, formula_result
            )

            # Step 8: Validation (optional, skip if module not available)
            self._emit("validation", 80, "Running validation...")

            # Step 9: Extract styles
            self._emit("styles", 90, "Extracting styles...")
            style_index = self._step_styles()

            # Step 10: Structure analysis (LLM)
            self._emit("structure", 93, "Analyzing file structure...")
            self._step_structure(schemas)

            # Step 11: Write cache
            self._emit("done", 95, "Writing cache...")
            self._step_write_cache(schemas, stats, formula_result, style_index)

            elapsed = int((time.monotonic() - self._start_time) * 1000)
            self._emit("done", 100, f"Done ({elapsed}ms)")

            return PreloadResult(
                file_id=cfg.file_id,
                status="ok",
                schema_path=cfg.schema_path,
                stats_path=cfg.stats_path,
                duckdb_path=cfg.duckdb_path,
                structure_path=cfg.structure_path,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            self._emit("error", 0, f"Error: {e}")
            return PreloadResult(
                file_id=cfg.file_id,
                status="error",
                schema_path=cfg.schema_path,
                stats_path=cfg.stats_path,
                duckdb_path=cfg.duckdb_path,
                structure_path=cfg.structure_path,
                duration_ms=elapsed,
                error_message=traceback.format_exc(),
            )

    # -- progress --------------------------------------------------------

    def _emit(self, stage: str, pct: int, msg: str) -> None:
        if self._on_progress:
            elapsed = int((time.monotonic() - self._start_time) * 1000)
            self._on_progress(stage, pct, msg, elapsed)

    # -- steps -----------------------------------------------------------

    def _step_copy(self) -> None:
        """Copy source file to working directory."""
        cfg = self._config
        os.makedirs(os.path.dirname(cfg.working_path), exist_ok=True)
        source_path = os.path.abspath(cfg.source_path)
        working_path = os.path.abspath(cfg.working_path)
        if source_path == working_path:
            return
        shutil.copy2(cfg.source_path, cfg.working_path)

    def _step_read(self) -> dict[str, pd.DataFrame]:
        """Read all sheets from working file."""
        return ExcelReader.read_all_sheets(self._config.working_path)

    def _step_duckdb(self, data: dict[str, pd.DataFrame]) -> None:
        """Register all DataFrames into DuckDB."""
        cfg = self._config
        os.makedirs(os.path.dirname(cfg.duckdb_path), exist_ok=True)

        # Sanitize table names for DuckDB
        sanitized: dict[str, pd.DataFrame] = {}
        for sheet_name, df in data.items():
            table_name = SchemaExtractor._sanitize_table_name(sheet_name)
            sanitized[table_name] = df

        DuckDBQuery.register_dataframes(cfg.duckdb_path, sanitized)

    def _step_schema(self, data: dict[str, pd.DataFrame]) -> list[SheetSchema]:
        """Extract schema for all sheets."""
        cfg = self._config
        return SchemaExtractor.extract(
            data=data,
            duckdb_path=cfg.duckdb_path,
            file_path=cfg.working_path,
            sample_rows=cfg.sample_rows,
        )

    def _step_stats(
        self,
        data: dict[str, pd.DataFrame],
        schemas: list[SheetSchema],
    ) -> FileStats:
        """Compute file-level statistics."""
        return StatsCalculator.compute_file_stats(self._config.file_id, data)

    def _step_formulas(self) -> FormulaScanResult:
        """Scan formulas and build dependency graph."""
        return FormulaScanner.scan(self._config.working_path)

    def _step_styles(self) -> StyleIndex:
        """Extract style index."""
        return StyleExtractor.extract(self._config.working_path)

    def _step_structure(self, schemas: list[SheetSchema]) -> None:
        """Run structure analysis via LLM and write result to cache."""
        cfg = self._config
        if not cfg.structure_path:
            return

        from .structure_analyzer import StructureAnalyzer

        # Build merged cells map from schemas
        merged_cells_map: dict[str, list[str]] = {}
        for s in schemas:
            if s.merged_cells:
                merged_cells_map[s.name] = s.merged_cells

        # Build schema summary for LLM context
        schema_summary: dict[str, dict] = {}
        for s in schemas:
            schema_summary[s.name] = {
                "columns": [
                    {"name": c.name, "dtype": c.dtype, "col_letter": c.col_letter}
                    for c in s.columns
                ],
                "row_count": s.row_count,
                "col_count": s.col_count,
            }

        api_key = os.environ.get("LLM_API_KEY", "")
        model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
        base_url = os.environ.get("LLM_BASE_URL") or None

        result = StructureAnalyzer.analyze(
            file_id=cfg.file_id,
            file_path=cfg.working_path,
            api_key=api_key,
            model=model,
            base_url=base_url,
            merged_cells_map=merged_cells_map,
            schema_summary=schema_summary,
        )

        # Write result to cache
        _write_json_file(cfg.structure_path, result.to_dict())

    def _step_write_cache(
        self,
        schemas: list[SheetSchema],
        stats: FileStats,
        formula_result: FormulaScanResult,
        style_index: StyleIndex,
    ) -> None:
        """Write schema and stats JSON files."""
        cfg = self._config

        # Schema JSON
        schema_data = {
            "fileId": cfg.file_id,
            "sheets": [s.to_dict() for s in schemas],
        }
        _write_json_file(cfg.schema_path, schema_data)

        # Stats JSON
        _write_json_file(cfg.stats_path, stats.to_dict())

    def _attach_formulas(
        self,
        schemas: list[SheetSchema],
        formula_result: FormulaScanResult,
    ) -> None:
        """Attach formula info to sheet schemas."""
        schema_map = {s.name: s for s in schemas}
        for sf in formula_result.sheets:
            if sf.sheet in schema_map:
                schema_map[sf.sheet].formulas = [
                    {
                        "cell": cf.cell,
                        "formula": cf.formula,
                        "dependsOn": cf.depends_on,
                    }
                    for cf in sf.formulas
                ]

    # -- cache read ------------------------------------------------------

    @staticmethod
    def get_schema(schema_path: str) -> dict | None:
        """Read cached schema JSON."""
        if not os.path.isfile(schema_path):
            return None
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def get_stats(stats_path: str) -> dict | None:
        """Read cached stats JSON."""
        if not os.path.isfile(stats_path):
            return None
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None


def _json_default(value: Any) -> Any:
    """Serialize values that Python's json encoder cannot handle by default."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date, time_value)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        item = value.item()
        if item is not value:
            return _json_default(item)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json_file(target_path: str, payload: Any) -> None:
    """Write JSON atomically so failed serialization never leaves a broken cache file."""
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    temp_path = f"{target_path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        os.replace(temp_path, target_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
