"""Tests for FormulaParser: reference extraction, forbidden functions."""

import pytest
from python.excel.formula_parser import FormulaParser


class TestExtractCellReferences:
    def test_simple(self):
        refs = FormulaParser.extract_cell_references("A1+B2")
        assert "A1" in refs
        assert "B2" in refs

    def test_absolute(self):
        refs = FormulaParser.extract_cell_references("$A$1+$B2")
        assert "$A$1" in refs
        assert "$B2" in refs

    def test_quoted_sheet(self):
        # Should not match inside quoted sheet names
        refs = FormulaParser.extract_cell_references("'Sheet 1'!A1+2025")
        assert "A1" in refs
        assert len(refs) == 1  # 2025 is not a cell ref


class TestExtractSheetReferences:
    def test_unquoted(self):
        refs = FormulaParser.extract_sheet_references("Sheet1!A1+Sheet2!B2")
        assert "Sheet1" in refs
        assert "Sheet2" in refs

    def test_quoted(self):
        refs = FormulaParser.extract_sheet_references("'Budget FY2025'!A1")
        assert "Budget FY2025" in refs


class TestForbiddenFunctions:
    def test_detect_filter(self):
        found = FormulaParser.detect_forbidden_functions("=FILTER(A1:B5,C1:C5>0)")
        assert "FILTER" in found

    def test_detect_xlookup(self):
        found = FormulaParser.detect_forbidden_functions("=XLOOKUP(1,A:A,B:B)")
        assert "XLOOKUP" in found

    def test_allow_sum(self):
        found = FormulaParser.detect_forbidden_functions("=SUM(A1:A10)")
        assert found == []

    def test_multiple_forbidden(self):
        found = FormulaParser.detect_forbidden_functions("=FILTER(SORT(A1:B5),1)")
        assert "FILTER" in found
        assert "SORT" in found


class TestExpandSharedFormula:
    def test_same_sheet_down(self):
        result = FormulaParser.expand_shared_formula("A1+B1", "B2", "B5")
        assert result == "A4+B4"

    def test_absolute_stays(self):
        result = FormulaParser.expand_shared_formula("A$1+$B$5", "C2", "C4")
        assert result == "A$1+$B$5"

    def test_no_change_same_cell(self):
        result = FormulaParser.expand_shared_formula("A1+B1", "B2", "B2")
        assert result == "A1+B1"


class TestShiftFormula:
    def test_delegate(self):
        result = FormulaParser.shift_formula("A5+B5", at_row=3, delta=2)
        assert result == "A7+B7"
