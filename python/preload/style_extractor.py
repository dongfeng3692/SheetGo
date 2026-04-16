"""Style extractor: lightweight style index from Excel files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..excel.models import CellRange, col_letter
from ..excel.reader import ExcelReader


@dataclass
class CellStyle:
    """Style information for a single cell."""
    font_name: str | None = None
    font_size: float | None = None
    bold: bool = False
    italic: bool = False
    font_color: str | None = None
    fill_color: str | None = None
    number_format: str | None = None
    horizontal: str | None = None
    vertical: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.font_name is not None:
            d["font_name"] = self.font_name
        if self.font_size is not None:
            d["font_size"] = self.font_size
        if self.bold:
            d["bold"] = True
        if self.italic:
            d["italic"] = True
        if self.font_color is not None:
            d["font_color"] = self.font_color
        if self.fill_color is not None:
            d["fill_color"] = self.fill_color
        if self.number_format is not None:
            d["number_format"] = self.number_format
        if self.horizontal is not None:
            d["horizontal"] = self.horizontal
        if self.vertical is not None:
            d["vertical"] = self.vertical
        return d


@dataclass
class SheetStyleIndex:
    """Style index for a single sheet."""
    sheet: str
    cells: dict[str, CellStyle] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sheet": self.sheet,
            "cells": {k: v.to_dict() for k, v in self.cells.items()},
        }


@dataclass
class StyleIndex:
    """Complete style index across all sheets."""
    sheets: list[SheetStyleIndex] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"sheets": [s.to_dict() for s in self.sheets]}


class StyleExtractor:
    """Extract style index from Excel files."""

    MAX_STYLE_SCAN_ROWS: int = 100

    @staticmethod
    def extract(
        file_path: str, sheet_names: list[str] | None = None
    ) -> StyleIndex:
        """Extract style index for all sheets.

        Only scans the first MAX_STYLE_SCAN_ROWS for performance.
        """
        if sheet_names is None:
            sheet_names = ExcelReader.read_sheet_names(file_path)

        result_sheets: list[SheetStyleIndex] = []

        for sname in sheet_names:
            try:
                dims = ExcelReader.read_dimensions(file_path, sname)
                end_col = dims.end_col
                end_row = min(dims.end_row, StyleExtractor.MAX_STYLE_SCAN_ROWS)

                rng = CellRange(
                    sheet=sname,
                    start_col="A",
                    start_row=1,
                    end_col=end_col,
                    end_row=end_row,
                )

                raw_styles = ExcelReader.read_styles(file_path, sname, rng)
                cells: dict[str, CellStyle] = {}
                for cell_ref, info in raw_styles.items():
                    cells[cell_ref] = StyleExtractor._to_cell_style(info)

                result_sheets.append(SheetStyleIndex(sheet=sname, cells=cells))
            except Exception:
                # If we can't read styles for a sheet, skip it
                result_sheets.append(SheetStyleIndex(sheet=sname, cells={}))

        return StyleIndex(sheets=result_sheets)

    @staticmethod
    def _to_cell_style(raw: dict) -> CellStyle:
        """Convert raw style dict from ExcelReader to CellStyle."""
        return CellStyle(
            font_name=raw.get("font_name"),
            font_size=raw.get("font_size"),
            bold=raw.get("bold", False),
            italic=raw.get("italic", False),
            font_color=raw.get("font_color"),
            fill_color=raw.get("fill_color"),
            number_format=raw.get("number_format"),
            horizontal=raw.get("horizontal"),
            vertical=raw.get("vertical"),
        )
