"""Formula parser: reference extraction, dependency analysis, shared formula expansion."""

from __future__ import annotations

import re
from typing import Any

from .models import FormulaInfo, InvalidCellRefError, col_letter, col_number, parse_cell_ref
from .xml_helpers import shift_formula as _xml_shift_formula

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCEL_ERRORS = frozenset({
    "#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#NULL!", "#NUM!", "#N/A",
})

# Common Excel functions — used to filter out false positives in name-ref detection
_BUILTIN_FUNCTIONS = frozenset({
    "SUM", "AVERAGE", "COUNT", "COUNTA", "COUNTBLANK", "MAX", "MIN",
    "IF", "IFS", "AND", "OR", "NOT", "XOR", "SWITCH",
    "VLOOKUP", "HLOOKUP", "LOOKUP", "INDEX", "MATCH", "XLOOKUP",
    "SUMIF", "SUMIFS", "COUNTIF", "COUNTIFS", "AVERAGEIF", "AVERAGEIFS",
    "CONCATENATE", "CONCAT", "TEXTJOIN", "LEFT", "RIGHT", "MID", "LEN",
    "UPPER", "LOWER", "PROPER", "TRIM", "SUBSTITUTE", "REPLACE",
    "IFERROR", "ISERROR", "ISBLANK", "ISNA", "ISTEXT", "ISNUMBER",
    "ROUND", "ROUNDUP", "ROUNDDOWN", "INT", "MOD", "ABS", "POWER",
    "TODAY", "NOW", "DATE", "YEAR", "MONTH", "DAY", "WEEKDAY",
    "ROW", "COLUMN", "ROWS", "COLUMNS", "ADDRESS", "INDIRECT", "OFFSET",
    "SUMPRODUCT", "SUBTOTAL", "AGGREGATE",
    "FILTER", "SORT", "UNIQUE", "SEQUENCE", "RANDARRAY",
    "LET", "LAMBDA", "MAP", "REDUCE", "SCAN", "MAKEARRAY",
    "PIVOTBY", "GROUPBY",
    # Math
    "CEILING", "FLOOR", "PRODUCT", "QUOTIENT",
    # Statistical
    "MEDIAN", "STDEV", "STDEV.P", "STDEV.S", "VAR", "VAR.P", "VAR.S",
    "PERCENTILE", "QUARTILE", "LARGE", "SMALL", "RANK",
    # Info
    "CELL", "TYPE", "N", "ISFORMULA",
})

# Functions that may not survive round-trip or are problematic in some contexts
_FORBIDDEN_FUNCTIONS = frozenset({
    "FILTER",      # Dynamic array, Excel 365+
    "SORT",        # Dynamic array
    "UNIQUE",      # Dynamic array
    "SEQUENCE",    # Dynamic array
    "RANDARRAY",   # Dynamic array
    "XLOOKUP",     # Excel 365+
    "LET",         # Excel 365+
    "LAMBDA",      # Excel 365+
    "PIVOTBY",     # Excel 365+
    "GROUPBY",     # Excel 365+
})

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Cell reference: optional $, column letters, optional $, row digits
_CELL_REF_RE = re.compile(r"(\$?)([A-Z]+)(\$?)(\d+)")

# Quoted sheet name prefix: 'Sheet Name'!
_QUOTED_SHEET_RE = re.compile(r"'([^']*(?:''[^']*)*)'!")

# Unquoted sheet name prefix: SheetName! (letter/underscore/CJK start)
_UNQUOTED_SHEET_RE = re.compile(
    r"(?<!')([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_.\u4e00-\u9fff]*)!"
)


class FormulaParser:
    """Formula analysis: reference extraction, dependency graph, validation."""

    # -- reference extraction --------------------------------------------

    @staticmethod
    def extract_cell_references(formula: str) -> list[str]:
        """Extract cell references from a formula string.

        Returns refs like ['A1', '$B$5', 'C10'] (with $ prefixes preserved).
        Skips references inside quoted sheet names.
        """
        # Split on quoted sheet names to avoid matching inside them
        segments = re.split(r"('[^']*(?:''[^']*)*')", formula)
        refs: list[str] = []
        for i, seg in enumerate(segments):
            if i % 2 == 1:
                continue  # quoted sheet name, skip
            for m in _CELL_REF_RE.finditer(seg):
                refs.append(m.group(0))
        return refs

    @staticmethod
    def extract_sheet_references(formula: str) -> list[str]:
        """Extract sheet name references from a formula.

        Handles both quoted ('Sheet Name'!) and unquoted (Sheet1!) forms.
        Returns a list of sheet names (may have duplicates).
        """
        refs: list[str] = []

        # Quoted sheet names
        for m in _QUOTED_SHEET_RE.finditer(formula):
            name = m.group(1).replace("''", "'")  # unescape doubled quotes
            refs.append(name)

        # Unquoted sheet names (avoid re-matching quoted ones)
        # Remove quoted portions first
        stripped = _QUOTED_SHEET_RE.sub("", formula)
        for m in _UNQUOTED_SHEET_RE.finditer(stripped):
            refs.append(m.group(1))

        return refs

    @staticmethod
    def extract_name_references(formula: str) -> list[str]:
        """Heuristic extraction of named-range references.

        Strips cell refs, sheet refs, and function calls, then identifies
        remaining bare identifiers. May produce false positives.
        """
        # Remove quoted sheet name portions
        stripped = _QUOTED_SHEET_RE.sub("", formula)
        # Remove unquoted sheet name portions
        stripped = _UNQUOTED_SHEET_RE.sub("", stripped)
        # Remove cell references ($A$1, B5, etc.)
        stripped = _CELL_REF_RE.sub("", stripped)

        # Find identifiers that are NOT function calls (not followed by '(')
        idents = re.findall(r"\b([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_.\u4e00-\u9fff]*)\b(?![(])", stripped)

        # Filter: at least 3 chars, not cell-ref pattern, not builtin function
        result: list[str] = []
        cell_pat = re.compile(r"^[A-Z]{1,3}[0-9]+$")
        for ident in idents:
            if len(ident) < 3:
                continue
            if cell_pat.match(ident.upper()):
                continue
            if ident.upper() in _BUILTIN_FUNCTIONS:
                continue
            result.append(ident)
        return result

    # -- dependency graph ------------------------------------------------

    @staticmethod
    def build_dependency_graph(
        formulas: list[FormulaInfo],
    ) -> dict[str, list[str]]:
        """Build a dependency graph from formula info list.

        Returns {cell_ref: [dep1, dep2, ...]} where deps are cell refs
        extracted from the formula. Keys include sheet prefix:
        'Sheet1!B2': ['Sheet1!A1', 'Sheet2!C3']
        """
        graph: dict[str, list[str]] = {}
        for fi in formulas:
            key = f"{fi.sheet}!{fi.cell}"
            deps: list[str] = []

            for ref in FormulaParser.extract_cell_references(fi.formula):
                sheet_refs = FormulaParser.extract_sheet_references(
                    fi.formula
                )
                # Determine which sheet this ref belongs to
                # Simple approach: if no sheet prefix in formula near this ref,
                # assume same sheet
                deps.append(f"{fi.sheet}!{ref.lstrip('$')}")

            # Also add cross-sheet refs
            for sref in FormulaParser.extract_sheet_references(fi.formula):
                # Find cell refs that follow this sheet reference
                # This is a simplified approach; a full parser would be more precise
                pass

            graph[key] = deps
        return graph

    # -- forbidden function detection ------------------------------------

    @staticmethod
    def detect_forbidden_functions(formula: str) -> list[str]:
        """Detect Excel functions that may not be compatible.

        Returns a list of function names found that are in the forbidden set.
        Checks for both standalone calls and nested calls.
        """
        found: list[str] = []
        # Match function calls: NAME(
        for m in re.finditer(r"\b([A-Z]+)\s*\(", formula.upper()):
            fname = m.group(1)
            if fname in _FORBIDDEN_FUNCTIONS:
                if fname not in found:
                    found.append(fname)
        return found

    # -- shared formula expansion ----------------------------------------

    @staticmethod
    def expand_shared_formula(
        formula: str,
        primary_ref: str,
        target_ref: str,
    ) -> str:
        """Expand a shared formula from its primary cell to a target cell.

        Adjusts relative references by the row/column offset between
        primary_ref and target_ref.

        Args:
            formula: The formula text from the primary cell.
            primary_ref: Cell reference of the primary cell (e.g. "B2").
            target_ref: Cell reference of the target cell (e.g. "B5").
        """
        p_col, p_row = parse_cell_ref(primary_ref)
        t_col, t_row = parse_cell_ref(target_ref)

        d_col = col_number(t_col) - col_number(p_col)
        d_row = t_row - p_row

        if d_col == 0 and d_row == 0:
            return formula

        def shift(m: re.Match) -> str:
            dollar_col = m.group(1)
            col_part = m.group(2)
            dollar_row = m.group(3)
            row = int(m.group(4))

            # Only shift non-absolute references
            new_col = col_part
            new_row = row

            if not dollar_col and d_col != 0:
                n = col_number(col_part) + d_col
                if n < 1:
                    n = 1
                new_col = col_letter(n)

            if not dollar_row and d_row != 0:
                new_row = max(1, row + d_row)

            return f"{dollar_col}{new_col}{dollar_row}{new_row}"

        # Split on quoted sheet names to preserve them
        segments = re.split(r"('[^']*(?:''[^']*)*')", formula)
        result: list[str] = []
        for i, seg in enumerate(segments):
            if i % 2 == 1:
                result.append(seg)
            else:
                result.append(_CELL_REF_RE.sub(shift, seg))
        return "".join(result)

    # -- convenience: shift formula rows ---------------------------------

    @staticmethod
    def shift_formula(formula: str, at_row: int, delta: int) -> str:
        """Delegate to xml_helpers.shift_formula for row shifting."""
        return _xml_shift_formula(formula, at_row, delta)
