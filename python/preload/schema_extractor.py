"""Schema extractor: column types, null counts, unique counts, samples."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..excel.duckdb_query import DuckDBQuery
from ..excel.models import col_letter
from ..excel.reader import ExcelReader
from .stats_calculator import StatsCalculator


@dataclass
class ColumnSchema:
    """Schema for a single column within a sheet."""
    name: str
    index: int
    col_letter: str
    dtype: str
    duckdb_type: str | None = None
    nullable: bool = True
    null_count: int = 0
    unique_count: int = 0
    sample: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "name": self.name,
            "index": self.index,
            "colLetter": self.col_letter,
            "dtype": self.dtype,
            "nullable": self.nullable,
            "nullCount": self.null_count,
            "uniqueCount": self.unique_count,
            "sample": [_json_safe(v) for v in self.sample],
            "stats": _json_safe_dict(self.stats),
        }
        if self.duckdb_type is not None:
            d["duckdbType"] = self.duckdb_type
        return d


@dataclass
class SheetSchema:
    """Schema for an entire sheet."""
    name: str
    table_name: str
    data_range: str
    row_count: int
    col_count: int
    has_headers: bool = True
    columns: list[ColumnSchema] = field(default_factory=list)
    merged_cells: list[str] = field(default_factory=list)
    formulas: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tableName": self.table_name,
            "dataRange": self.data_range,
            "rowCount": self.row_count,
            "colCount": self.col_count,
            "hasHeaders": self.has_headers,
            "columns": [c.to_dict() for c in self.columns],
            "mergedCells": self.merged_cells,
            "formulas": self.formulas,
        }


class SchemaExtractor:
    """Extract per-sheet column schemas from DataFrames."""

    @staticmethod
    def extract(
        data: dict[str, pd.DataFrame],
        duckdb_path: str | None = None,
        file_path: str | None = None,
        sample_rows: int = 20,
    ) -> list[SheetSchema]:
        """Extract schema for all sheets.

        Uses pandas dtype detection + optional DuckDB DESCRIBE + openpyxl for merged cells.
        """
        schemas: list[SheetSchema] = []

        for sheet_name, df in data.items():
            table_name = SchemaExtractor._sanitize_table_name(sheet_name)

            # DuckDB type info (optional)
            duckdb_types: list[str | None] = []
            if duckdb_path:
                try:
                    cols = DuckDBQuery.describe_table(duckdb_path, table_name)
                    duckdb_types = [c.dtype for c in cols]
                except Exception:
                    pass  # DuckDB not yet registered or table missing

            # Column schemas
            columns: list[ColumnSchema] = []
            for i, col_name in enumerate(df.columns):
                cs = SchemaExtractor._extract_column(
                    df, str(col_name), i, sample_rows,
                    duckdb_types[i] if i < len(duckdb_types) else None,
                )
                columns.append(cs)

            # Merged cells (optional, needs file path)
            merged: list[str] = []
            if file_path:
                try:
                    merged = ExcelReader.read_merged_cells(file_path, sheet_name)
                except Exception:
                    pass

            row_count = len(df)
            col_count = len(df.columns)
            data_range = SchemaExtractor._compute_data_range(row_count, col_count)

            schemas.append(SheetSchema(
                name=sheet_name,
                table_name=table_name,
                data_range=data_range,
                row_count=row_count,
                col_count=col_count,
                columns=columns,
                merged_cells=merged,
            ))

        return schemas

    @staticmethod
    def _sanitize_table_name(sheet_name: str) -> str:
        """Convert sheet name to a valid DuckDB table name."""
        name = sheet_name.lower().strip()
        name = re.sub(r"[^a-z0-9_]", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name:
            name = "sheet"
        if name[0].isdigit():
            name = f"_{name}"
        return name

    @staticmethod
    def _extract_column(
        df: pd.DataFrame,
        col_name: str,
        col_index: int,
        sample_rows: int,
        duckdb_type: str | None = None,
    ) -> ColumnSchema:
        """Extract schema for one column."""
        # Use positional indexing so duplicate headers still resolve to a Series.
        series = df.iloc[:, col_index]
        null_count = int(series.isna().sum())
        unique_count = int(series.nunique())

        # Sample: first N non-null values
        sample = series.dropna().head(sample_rows).tolist()

        # Stats
        stats = StatsCalculator.compute_column_stats(series)

        return ColumnSchema(
            name=col_name,
            index=col_index,
            col_letter=col_letter(col_index + 1),
            dtype=str(series.dtype),
            duckdb_type=duckdb_type,
            nullable=null_count > 0,
            null_count=null_count,
            unique_count=unique_count,
            sample=sample,
            stats=stats,
        )

    @staticmethod
    def _compute_data_range(row_count: int, col_count: int) -> str:
        """Return Excel-style range like 'A1:F100'."""
        if col_count == 0 or row_count == 0:
            return "A1"
        end_col = col_letter(col_count)
        # +1 for header row
        return f"A1:{end_col}{row_count + 1}"


def _json_safe(val: Any) -> Any:
    """Convert value to JSON-safe type."""
    if val is None:
        return None
    if isinstance(val, pd.Timestamp):
        return val.isoformat()
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if hasattr(val, "item"):
        item = val.item()
        if item is val:
            return val
        return _json_safe(item)
    return val


def _json_safe_dict(d: dict) -> dict:
    """Convert all values in a dict to JSON-safe types."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _json_safe_dict(v)
        elif isinstance(v, list):
            result[k] = [
                _json_safe_dict(item) if isinstance(item, dict) else _json_safe(item)
                for item in v
            ]
        else:
            result[k] = _json_safe(v)
    return result
