"""Statistics calculator: column-level and file-level stats for preload."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class DataQuality:
    """Data quality summary across the entire file."""
    null_rate: float
    duplicate_rows: int
    mixed_type_columns: list[str] = field(default_factory=list)
    outlier_columns: dict[str, int] = field(default_factory=dict)


@dataclass
class FileStats:
    """File-level statistics cache."""
    file_id: str
    total_sheets: int
    total_rows: int
    total_cols: int
    total_formulas: int
    data_quality: DataQuality
    formula_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "fileId": self.file_id,
            "totalSheets": self.total_sheets,
            "totalRows": self.total_rows,
            "totalCols": self.total_cols,
            "totalFormulas": self.total_formulas,
            "dataQuality": {
                "nullRate": self.data_quality.null_rate,
                "duplicateRows": self.data_quality.duplicate_rows,
                "mixedTypeColumns": self.data_quality.mixed_type_columns,
                "outlierColumns": self.data_quality.outlier_columns,
            },
            "formulaSummary": self.formula_summary,
        }


class StatsCalculator:
    """Compute statistics from DataFrames."""

    @staticmethod
    def compute_column_stats(series: pd.Series) -> dict:
        """Compute stats for a single column.

        Numeric: min, max, mean, median, std.
        Categorical: top 5 values with counts.
        Datetime: min, max as ISO strings.
        """
        dtype_str = str(series.dtype)
        clean = series.dropna()

        if len(clean) == 0:
            return {"null_count": int(series.isna().sum())}

        if "int" in dtype_str or "float" in dtype_str:
            desc = clean.describe()
            return {
                "min": _to_python(desc.get("min")),
                "max": _to_python(desc.get("max")),
                "mean": _to_python(desc.get("mean")),
                "median": _to_python(desc.get("50%")),
                "std": _to_python(desc.get("std")),
            }

        if "datetime" in dtype_str or "date" in dtype_str:
            mn = clean.min()
            mx = clean.max()
            return {
                "min": mn.isoformat() if hasattr(mn, "isoformat") else str(mn),
                "max": mx.isoformat() if hasattr(mx, "isoformat") else str(mx),
            }

        # Categorical / object / bool
        vc = clean.value_counts().head(5)
        return {
            "topValues": [
                {"value": str(v), "count": int(c)}
                for v, c in vc.items()
            ],
        }

    @staticmethod
    def compute_file_stats(
        file_id: str,
        data: dict[str, pd.DataFrame],
        formula_result: Any | None = None,
        validation_errors: list[dict] | None = None,
    ) -> FileStats:
        """Compute file-level statistics."""
        total_rows = sum(len(df) for df in data.values())
        total_cols = sum(len(df.columns) for df in data.values())

        formula_count = 0
        formula_summary: dict[str, Any] = {
            "totalCount": 0,
            "errors": 0,
            "crossSheetRefs": 0,
            "compatWarnings": [],
        }

        if formula_result is not None:
            formula_count = formula_result.total_count
            formula_summary["totalCount"] = formula_count
            formula_summary["crossSheetRefs"] = formula_result.cross_sheet_count

            # Collect forbidden function warnings
            warnings: list[str] = []
            for sf in formula_result.sheets:
                for cf in sf.formulas:
                    for fn in cf.forbidden:
                        warnings.append(f"{cf.cell}: uses {fn}()")
            formula_summary["compatWarnings"] = warnings

        dq = StatsCalculator.compute_data_quality(data)

        return FileStats(
            file_id=file_id,
            total_sheets=len(data),
            total_rows=total_rows,
            total_cols=total_cols,
            total_formulas=formula_count,
            data_quality=dq,
            formula_summary=formula_summary,
        )

    @staticmethod
    def compute_data_quality(data: dict[str, pd.DataFrame]) -> DataQuality:
        """Assess data quality: null rates, duplicates, mixed types."""
        total_cells = 0
        total_nulls = 0
        total_dupes = 0
        mixed_cols: list[str] = []

        for sheet_name, df in data.items():
            total_cells += df.size
            total_nulls += int(df.isna().sum().sum())
            total_dupes += int(df.duplicated().sum())

            # Detect mixed-type columns
            for idx, col in enumerate(df.columns):
                # Use positional indexing so duplicate headers do not return a DataFrame.
                series = df.iloc[:, idx].dropna()
                if len(series) == 0:
                    continue
                types = series.apply(type).nunique()
                if types > 1:
                    mixed_cols.append(f"{sheet_name}.{col}")

        null_rate = total_nulls / total_cells if total_cells > 0 else 0.0

        return DataQuality(
            null_rate=round(null_rate, 4),
            duplicate_rows=total_dupes,
            mixed_type_columns=mixed_cols,
        )


def _to_python(val: Any) -> Any:
    """Convert numpy types to plain Python for JSON serialization."""
    if val is None:
        return None
    if hasattr(val, "item"):
        return val.item()  # numpy scalar
    return val
