"""Excel Engine: read, write, query, and manipulate Excel files."""

from .models import (
    CellEdit,
    CellRange,
    ChartConfig,
    ChartInfo,
    ColumnDesc,
    EditResult,
    ExcelEngineError,
    FormulaInfo,
    InvalidCellRefError,
    SheetNotFoundError,
    SQLError,
    StyleConfig,
    StyleSlot,
    XMLPackError,
    col_letter,
    col_number,
    parse_cell_ref,
)
from .reader import ExcelReader
from .writer import ExcelWriter
from .xml_helpers import XMLHelpers
from .formula_parser import FormulaParser
from .style_engine import StyleEngine
from .chart_engine import ChartEngine
from .duckdb_query import DuckDBQuery
from .template_engine import TemplateEngine

__all__ = [
    # Core classes
    "ExcelReader",
    "ExcelWriter",
    "XMLHelpers",
    "FormulaParser",
    "StyleEngine",
    "ChartEngine",
    "DuckDBQuery",
    "TemplateEngine",
    # Data models
    "CellEdit",
    "CellRange",
    "ChartConfig",
    "ChartInfo",
    "ColumnDesc",
    "EditResult",
    "FormulaInfo",
    "StyleConfig",
    "StyleSlot",
    # Exceptions
    "ExcelEngineError",
    "InvalidCellRefError",
    "SheetNotFoundError",
    "SQLError",
    "XMLPackError",
    # Utility functions
    "col_letter",
    "col_number",
    "parse_cell_ref",
]
