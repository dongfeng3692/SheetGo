"""Tests for ExcelReader: calamine reads + openpyxl metadata."""

import pytest
from python.excel.reader import ExcelReader


class TestReadSheetNames:
    def test_basic(self, simple_xlsx):
        names = ExcelReader.read_sheet_names(simple_xlsx)
        assert "Sheet1" in names


class TestReadSheetData:
    def test_full_sheet(self, simple_xlsx):
        df = ExcelReader.read_sheet_data(simple_xlsx, "Sheet1")
        # 4 data rows + 1 formula row (B6=SUM, calamine sees it as empty)
        assert len(df) >= 4
        assert "Name" in df.columns
        assert df.iloc[0]["Name"] == "Alice"

    def test_sheet_not_found(self, simple_xlsx):
        from python.excel.models import SheetNotFoundError
        with pytest.raises(SheetNotFoundError):
            ExcelReader.read_sheet_data(simple_xlsx, "NonExistent")


class TestReadCell:
    def test_string_cell(self, simple_xlsx):
        val = ExcelReader.read_cell(simple_xlsx, "Sheet1", "A2")
        assert val == "Alice"

    def test_numeric_cell(self, simple_xlsx):
        val = ExcelReader.read_cell(simple_xlsx, "Sheet1", "B2")
        assert val == 100.0  # calamine returns float

    def test_header_cell(self, simple_xlsx):
        val = ExcelReader.read_cell(simple_xlsx, "Sheet1", "A1")
        assert val == "Name"

    def test_empty_cell(self, simple_xlsx):
        val = ExcelReader.read_cell(simple_xlsx, "Sheet1", "Z99")
        assert val is None


class TestReadAllSheets:
    def test_basic(self, simple_xlsx):
        result = ExcelReader.read_all_sheets(simple_xlsx)
        assert "Sheet1" in result
        assert len(result["Sheet1"]) >= 4


class TestReadFormulas:
    def test_find_formulas(self, simple_xlsx):
        formulas = ExcelReader.read_formulas(simple_xlsx, "Sheet1")
        assert len(formulas) >= 1
        # Should find the SUM formula
        f = next((f for f in formulas if f.cell == "B6"), None)
        assert f is not None
        assert "SUM" in f.formula

    def test_all_sheets(self, simple_xlsx):
        formulas = ExcelReader.read_formulas(simple_xlsx)
        assert len(formulas) >= 1


class TestReadDimensions:
    def test_basic(self, simple_xlsx):
        dims = ExcelReader.read_dimensions(simple_xlsx, "Sheet1")
        assert dims.start_col == "A"
        assert dims.end_row >= 5


class TestReadMergedCells:
    def test_no_merges(self, simple_xlsx):
        merges = ExcelReader.read_merged_cells(simple_xlsx, "Sheet1")
        assert merges == []


class TestReadStyles:
    def test_basic(self, simple_xlsx):
        styles = ExcelReader.read_styles(simple_xlsx, "Sheet1")
        assert isinstance(styles, dict)
        assert "A1" in styles  # Header should have style info
