"""Tests for models: utility functions and data classes."""

import pytest
from python.excel.models import (
    col_letter,
    col_number,
    parse_cell_ref,
    CellRange,
    EditResult,
    InvalidCellRefError,
)


class TestColLetter:
    def test_a(self):
        assert col_letter(1) == "A"

    def test_z(self):
        assert col_letter(26) == "Z"

    def test_aa(self):
        assert col_letter(27) == "AA"

    def test_aaa(self):
        assert col_letter(703) == "AAA"


class TestColNumber:
    def test_a(self):
        assert col_number("A") == 1

    def test_z(self):
        assert col_number("Z") == 26

    def test_aa(self):
        assert col_number("AA") == 27


class TestParseCellRef:
    def test_simple(self):
        assert parse_cell_ref("B5") == ("B", 5)

    def test_absolute(self):
        assert parse_cell_ref("$AA$100") == ("AA", 100)

    def test_invalid(self):
        with pytest.raises(InvalidCellRefError):
            parse_cell_ref("ABC")

    def test_lowercase(self):
        assert parse_cell_ref("c3") == ("C", 3)


class TestCellRange:
    def test_to_excel_ref(self):
        r = CellRange(sheet="Sheet1", start_col="A", start_row=1,
                      end_col="F", end_row=100)
        assert r.to_excel_ref() == "'Sheet1'!A1:F100"

    def test_col_count(self):
        r = CellRange(sheet="S", start_col="A", start_row=1,
                      end_col="C", end_row=10)
        assert r.col_count() == 3

    def test_row_count(self):
        r = CellRange(sheet="S", start_col="A", start_row=1,
                      end_col="C", end_row=10)
        assert r.row_count() == 10


class TestEditResult:
    def test_ok(self):
        r = EditResult.ok(cells=["A1"], formulas=["B2"])
        assert r.success
        assert r.affected_cells == ["A1"]

    def test_fail(self):
        r = EditResult.fail(warnings=["bad"])
        assert not r.success
        assert r.warnings == ["bad"]
