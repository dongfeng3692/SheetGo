"""write_query — SQL 查询结果直接写入 Excel，数据不经过 LLM"""

from __future__ import annotations

import builtins
import math
from typing import Any

import duckdb
import pandas as pd

from .base import BaseTool


class WriteQueryTool(BaseTool):

    @property
    def name(self) -> str:
        return "write_query"

    @property
    def description(self) -> str:
        return (
            "执行 SQL 查询并将结果直接写入 Excel 指定区域。"
            "适用于需要写入大量数据的场景（如过滤、排序、聚合后的结果），"
            "数据在内部从 SQL 直接写入 Excel，不经过 LLM 传输。"
            "列名使用字母 A, B, C, D...（与 read_sheet 一致）。"
            "默认清除写入区域下方的旧数据（clear_old=true）。"
            "示例: write_query(file_path=..., sql=\"SELECT A,B,C FROM sheet WHERE A > 10\", sheet=\"Sheet1\", range=\"A1\")"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Excel 文件路径",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL 查询语句，查询结果将写入 Excel",
                },
                "sheet": {
                    "type": "string",
                    "description": "目标工作表名",
                },
                "range": {
                    "type": "string",
                    "description": "写入起始位置（如 'I6'）或范围（如 'I6:M295'）。仅指定起始单元格时自动扩展。",
                },
                "clear_old": {
                    "type": "boolean",
                    "description": "是否清除目标工作表中写入区域下方的旧数据（默认 true）",
                    "default": True,
                },
            },
            "required": ["file_path", "sql", "sheet", "range"],
        }

    @property
    def safe_level(self) -> str:
        return "write"

    async def execute(
        self,
        file_path: str,
        sql: str,
        sheet: str,
        range: str = "",
        cell_range: str = "",
        clear_old: bool = True,
        **kwargs,
    ) -> Any:
        from excel.duckdb_query import DuckDBQuery
        from excel.models import CellEdit, col_number, col_letter, parse_cell_ref
        from excel.writer import ExcelWriter
        from tools.read_sheet import _col_letter as _cl
        from tools.write_cells import _coerce_value

        # Accept both 'range' and 'cell_range' parameter names
        target_range = range or cell_range or ""

        # Validate SQL
        is_valid, error = DuckDBQuery.validate_sql(sql)
        if not is_valid:
            return {"error": error}

        # Run query — no auto-cast to preserve mixed-type data (e.g. strings in numeric columns)
        con = duckdb.connect(":memory:")
        try:
            xlsx = pd.ExcelFile(file_path, engine="openpyxl")
            original_rows = 0
            for sheet_name in xlsx.sheet_names:
                df_src = pd.read_excel(xlsx, sheet_name=sheet_name, header=None)
                if sheet_name == sheet:
                    original_rows = len(df_src)
                df_src.columns = [_cl(i) for i in builtins.range(len(df_src.columns))]
                con.register(sheet_name, df_src)

            result_df = con.execute(sql).fetchdf()
        except duckdb.Error as e:
            return {"error": f"SQL execution error: {e}"}
        finally:
            con.close()

        # Parse target range
        parts = target_range.split(":")
        start_col, start_row = parse_cell_ref(parts[0])

        # Build CellEdits — include None values to clear old data
        edits: list[CellEdit] = []
        for row_idx in builtins.range(len(result_df)):
            for col_idx in builtins.range(len(result_df.columns)):
                val = result_df.iloc[row_idx].iloc[col_idx]
                if isinstance(val, float) and math.isnan(val):
                    continue  # true NaN (not a value), skip
                elif pd.isna(val) if not isinstance(val, str) else False:
                    continue
                val = _coerce_value(val) if val is not None else None
                cell_ref = f"{col_letter(col_number(start_col) + col_idx)}{start_row + row_idx}"
                edits.append(CellEdit(sheet=sheet, cell=cell_ref, value=val))

        # Write data cells
        writer = ExcelWriter()
        result = writer.write_cells(file_path, edits)

        end_col = col_letter(col_number(start_col) + len(result_df.columns) - 1)
        end_row = start_row + len(result_df) - 1
        actual_range = f"{parts[0]}:{end_col}{end_row}"

        # Clear old data below the written range
        rows_cleared = 0
        if clear_old and original_rows > end_row:
            excess_start = end_row + 1
            excess_count = original_rows - end_row
            del_result = writer.delete_rows(file_path, sheet, excess_start, excess_count)
            rows_cleared = excess_count

        return {
            "success": result.success,
            "rows_written": len(result_df),
            "columns_written": len(result_df.columns),
            "range": actual_range,
            "rows_cleared": rows_cleared,
            "affected_cells": len(result.affected_cells),
            "warnings": result.warnings,
        }
