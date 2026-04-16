"""Data models, exceptions, and utility functions for the Excel engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ExcelEngineError(Exception):
    """Base exception for the Excel engine."""


class SheetNotFoundError(ExcelEngineError):
    """Requested sheet does not exist in the workbook."""


class InvalidCellRefError(ExcelEngineError):
    """Invalid cell reference string (e.g. 'ABC')."""


class SQLError(ExcelEngineError):
    """SQL validation or execution error."""


class XMLPackError(ExcelEngineError):
    """Error during XML pack/unpack operations."""


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def col_letter(n: int) -> str:
    """Convert 1-based column number to Excel column letter(s).

    >>> col_letter(1)
    'A'
    >>> col_letter(26)
    'Z'
    >>> col_letter(27)
    'AA'
    >>> col_letter(703)
    'AAA'
    """
    r = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        r = chr(65 + rem) + r
    return r


def col_number(s: str) -> int:
    """Convert Excel column letter(s) to 1-based column number.

    >>> col_number("A")
    1
    >>> col_number("Z")
    26
    >>> col_number("AA")
    27
    """
    n = 0
    for c in s.upper():
        n = n * 26 + (ord(c) - 64)
    return n


_CELL_REF_RE = re.compile(r"^(\$?)([A-Z]+)(\$?)(\d+)$")


def parse_cell_ref(ref: str) -> tuple[str, int]:
    """Parse a cell reference like 'B5' or '$AA$100' into (col_letters, row_number).

    The returned column does NOT include the '$' prefix.
    Raises InvalidCellRefError if the reference is malformed.
    """
    m = _CELL_REF_RE.match(ref.upper().strip())
    if not m:
        raise InvalidCellRefError(f"Invalid cell reference: {ref!r}")
    return m.group(2), int(m.group(4))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CellRange:
    """A rectangular range in an Excel sheet."""
    sheet: str
    start_col: str       # "A"
    start_row: int       # 1
    end_col: str         # "F"
    end_row: int         # 100

    def to_excel_ref(self) -> str:
        """Return Excel notation: 'Sheet1'!A1:F100"""
        return f"'{self.sheet}'!{self.start_col}{self.start_row}:{self.end_col}{self.end_row}"

    def col_count(self) -> int:
        return col_number(self.end_col) - col_number(self.start_col) + 1

    def row_count(self) -> int:
        return self.end_row - self.start_row + 1


@dataclass
class CellEdit:
    """A single cell modification."""
    sheet: str
    cell: str            # "B2"
    value: Any           # Value or formula (str starting with '=')
    style: dict | None = None


@dataclass
class EditResult:
    """Result of an Excel edit operation."""
    success: bool
    affected_cells: list[str] = field(default_factory=list)
    affected_formulas: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, cells: list[str] | None = None,
           formulas: list[str] | None = None,
           warnings: list[str] | None = None) -> EditResult:
        return cls(success=True,
                   affected_cells=cells or [],
                   affected_formulas=formulas or [],
                   warnings=warnings or [])

    @classmethod
    def fail(cls, warnings: list[str] | None = None) -> EditResult:
        return cls(success=False, warnings=warnings or [])


@dataclass
class FormulaInfo:
    """Information about a formula cell."""
    sheet: str
    cell: str
    formula: str
    depends_on: list[str] = field(default_factory=list)
    is_shared: bool = False
    shared_ref: str | None = None


@dataclass
class ChartConfig:
    """Configuration for creating a chart."""
    chart_type: str          # "bar" | "line" | "pie" | "area" | "scatter"
    source_range: CellRange  # Data source range
    target_cell: str         # Insert position, e.g. "F1"
    target_sheet: str
    title: str = ""
    x_axis_title: str = ""
    y_axis_title: str = ""
    style: str = "monochrome"   # "monochrome" | "finance"
    show_labels: bool = True
    width: float = 15.0     # cm
    height: float = 10.0    # cm


@dataclass
class ChartInfo:
    """Information about an existing chart."""
    sheet: str
    anchor: str             # Top-left cell, e.g. "F1"
    chart_type: str
    title: str | None


@dataclass
class ColumnDesc:
    """Column description from DuckDB."""
    name: str
    dtype: str
    nullable: bool


@dataclass
class StyleConfig:
    """Style configuration for a cell range."""
    role: str               # "input" | "formula" | "cross_sheet" | "header" | "total"
    numfmt: str | None = None
    font_color: str | None = None
    bold: bool = False
    fill_color: str | None = None
    border_style: dict | None = None


@dataclass
class StyleSlot:
    """A predefined style slot in the template's styles.xml."""
    index: int
    role: str               # "input" | "formula" | "cross_sheet" | "header" | "default" | "any"
    font_color: str | None  # "blue" | "black" | "green" | "black_bold" | None
    numfmt_type: str | None # "general" | "currency" | "percent" | "integer" | "year" | "highlight" | None
