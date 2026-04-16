"""Preload pipeline: 10-step post-upload data extraction and caching."""

from __future__ import annotations

import json
import os
import shutil
import time
import traceback
from dataclasses import dataclass, field
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
    "done",       # 9
]

_STEP_WEIGHTS = [5, 15, 20, 15, 5, 10, 10, 10, 5, 5]


@dataclass
class PreloadConfig:
    """Input configuration for a preload run."""
    file_id: str
    source_path: str
    working_path: str
    duckdb_path: str
    schema_path: str
    stats_path: str
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
    duration_ms: int
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

            # Step 10: Write cache
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

    def _step_write_cache(
        self,
        schemas: list[SheetSchema],
        stats: FileStats,
        formula_result: FormulaScanResult,
        style_index: StyleIndex,
    ) -> None:
        """Write schema and stats JSON files."""
        cfg = self._config
        os.makedirs(os.path.dirname(cfg.schema_path), exist_ok=True)

        # Schema JSON
        schema_data = {
            "fileId": cfg.file_id,
            "sheets": [s.to_dict() for s in schemas],
        }
        with open(cfg.schema_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f, ensure_ascii=False, indent=2)

        # Stats JSON
        with open(cfg.stats_path, "w", encoding="utf-8") as f:
            json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)

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
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def get_stats(stats_path: str) -> dict | None:
        """Read cached stats JSON."""
        if not os.path.isfile(stats_path):
            return None
        with open(stats_path, "r", encoding="utf-8") as f:
            return json.load(f)
