"""Formula scanner: scan formulas and build dependency graph."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..excel.formula_parser import FormulaParser
from ..excel.reader import ExcelReader


@dataclass
class CellFormula:
    """A single formula cell's information."""
    cell: str
    formula: str
    depends_on: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)


@dataclass
class SheetFormulaInfo:
    """Formula info for a single sheet."""
    sheet: str
    formulas: list[CellFormula] = field(default_factory=list)


@dataclass
class FormulaScanResult:
    """Complete formula scan result across all sheets."""
    sheets: list[SheetFormulaInfo] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    total_count: int = 0
    cross_sheet_count: int = 0
    forbidden_count: int = 0


class FormulaScanner:
    """Scan formulas and build dependency graph."""

    @staticmethod
    def scan(file_path: str) -> FormulaScanResult:
        """Scan all formulas in the workbook.

        Delegates to ExcelReader for raw extraction, FormulaParser for analysis.
        """
        # Read raw formula info
        raw_formulas = ExcelReader.read_formulas(file_path)
        if not raw_formulas:
            return FormulaScanResult()

        # Build dependency graph
        dep_graph = FormulaParser.build_dependency_graph(raw_formulas)

        # Convert to CellFormula and group by sheet
        sheet_map: dict[str, list[CellFormula]] = {}
        all_sheets: set[str] = set()
        total_forbidden = 0

        for fi in raw_formulas:
            all_sheets.add(fi.sheet)
            deps = FormulaParser.extract_cell_references(fi.formula)
            forbidden = FormulaParser.detect_forbidden_functions(fi.formula)
            total_forbidden += len(forbidden)

            cf = CellFormula(
                cell=fi.cell,
                formula=fi.formula,
                depends_on=deps,
                forbidden=forbidden,
            )
            sheet_map.setdefault(fi.sheet, []).append(cf)

        # Count cross-sheet references by looking at sheet refs in formula text
        cross_count = 0
        for fi in raw_formulas:
            sheet_refs = FormulaParser.extract_sheet_references(fi.formula)
            for ref in sheet_refs:
                if ref != fi.sheet:
                    cross_count += 1

        sheets = [
            SheetFormulaInfo(sheet=name, formulas=formulas)
            for name, formulas in sheet_map.items()
        ]

        return FormulaScanResult(
            sheets=sheets,
            dependency_graph=dep_graph,
            total_count=len(raw_formulas),
            cross_sheet_count=cross_count,
            forbidden_count=total_forbidden,
        )
