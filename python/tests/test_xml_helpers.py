"""Tests for xml_helpers: unpack, pack, shift_rows, shared strings."""

import os
import tempfile
import zipfile

import pytest
from openpyxl import Workbook
from python.excel.xml_helpers import XMLHelpers, shift_formula, shift_sqref


class TestShiftFormula:
    """shift_formula moves ALL row refs >= at, including $-prefixed ones.

    This is correct for row insertion: physical positions change regardless
    of absolute/relative addressing.
    """

    def test_simple_ref(self):
        assert shift_formula("A1+B2", at=1, delta=1) == "A2+B3"

    def test_absolute_col_stays(self):
        # $ on column is preserved, but row still shifts
        assert shift_formula("$A1", at=1, delta=2) == "$A3"

    def test_dollar_row_still_shifts(self):
        # $ on row doesn't prevent shift — physical position changed
        assert shift_formula("A$1", at=1, delta=2) == "A$3"

    def test_absolute_both_still_shifts(self):
        assert shift_formula("$A$1", at=1, delta=2) == "$A$3"

    def test_below_threshold(self):
        assert shift_formula("A1", at=3, delta=1) == "A1"

    def test_at_threshold(self):
        assert shift_formula("A3", at=3, delta=1) == "A4"

    def test_quoted_sheet_name(self):
        # Should NOT corrupt text inside quoted sheet names
        result = shift_formula("'Budget FY2025'!A1", at=1, delta=1)
        assert "'Budget FY2025'!A2" == result

    def test_mixed_refs(self):
        # All rows >= 2 shift by 2
        result = shift_formula("A1+$B$3+C5", at=2, delta=2)
        assert result == "A1+$B$5+C7"


class TestShiftSqref:
    def test_single_cell(self):
        assert shift_sqref("A1", at=1, delta=1) == "A2"

    def test_range(self):
        result = shift_sqref("A1:B5", at=3, delta=1)
        assert result == "A1:B6"

    def test_multi_area(self):
        result = shift_sqref("A1 B2:C3", at=1, delta=1)
        assert result == "A2 B3:C4"


class TestUnpackPack:
    def test_roundtrip(self, simple_xlsx, tmp_dir):
        xml = XMLHelpers()
        work_dir = os.path.join(tmp_dir, "unpack_test")
        output = os.path.join(tmp_dir, "output.xlsx")

        xml.unpack(simple_xlsx, work_dir)
        assert os.path.isdir(work_dir)
        assert os.path.isfile(os.path.join(work_dir, "[Content_Types].xml"))
        assert os.path.isdir(os.path.join(work_dir, "xl", "worksheets"))

        xml.pack(work_dir, output)
        assert os.path.isfile(output)
        assert zipfile.is_zipfile(output)

    def test_pack_validates_xml(self, tmp_dir):
        xml = XMLHelpers()
        work_dir = os.path.join(tmp_dir, "bad_xml")
        os.makedirs(os.path.join(work_dir, "xl", "worksheets"))
        os.makedirs(os.path.join(work_dir, "xl", "_rels"))
        os.makedirs(os.path.join(work_dir, "_rels"))

        # Write a malformed XML file
        ct_path = os.path.join(work_dir, "[Content_Types].xml")
        with open(ct_path, "w") as f:
            f.write('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">')

        # Create a malformed worksheet XML
        ws_path = os.path.join(work_dir, "xl", "worksheets", "sheet1.xml")
        with open(ws_path, "w") as f:
            f.write("<invalid xml<<<>")

        from python.excel.models import XMLPackError
        output = os.path.join(tmp_dir, "bad.xlsx")
        with pytest.raises(XMLPackError):
            xml.pack(work_dir, output)


class TestSharedStrings:
    def _make_xlsx_with_shared_strings(self, tmp_dir):
        """Create an xlsx that uses shared strings (via minimax template)."""
        from python.excel.template_engine import TemplateEngine
        te = TemplateEngine()
        path = os.path.join(tmp_dir, "shared.xlsx")
        te.create_minimal(path)
        return path

    def test_get_shared_strings_empty(self, tmp_dir):
        """Template xlsx has an empty shared strings table."""
        path = self._make_xlsx_with_shared_strings(tmp_dir)
        xml = XMLHelpers()
        work_dir = os.path.join(tmp_dir, "unpacked_ss")
        xml.unpack(path, work_dir)
        ss = xml.get_shared_strings(work_dir)
        assert isinstance(ss, dict)

    def test_find_or_add_new(self, tmp_dir):
        path = self._make_xlsx_with_shared_strings(tmp_dir)
        xml = XMLHelpers()
        work_dir = os.path.join(tmp_dir, "unpacked_ss2")
        xml.unpack(path, work_dir)

        old_ss = xml.get_shared_strings(work_dir)
        idx = xml.find_or_add_shared_string(work_dir, "HELLO_WORLD")
        new_ss = xml.get_shared_strings(work_dir)
        assert "HELLO_WORLD" in new_ss.values()
        assert len(new_ss) == len(old_ss) + 1

    def test_find_or_add_existing(self, tmp_dir):
        path = self._make_xlsx_with_shared_strings(tmp_dir)
        xml = XMLHelpers()
        work_dir = os.path.join(tmp_dir, "unpacked_ss3")
        xml.unpack(path, work_dir)

        xml.find_or_add_shared_string(work_dir, "TEST_VAL")
        idx2 = xml.find_or_add_shared_string(work_dir, "TEST_VAL")
        ss = xml.get_shared_strings(work_dir)
        assert ss[idx2] == "TEST_VAL"

    def test_build_shared_strings(self):
        xml = XMLHelpers()
        result = xml.build_shared_strings(["hello", "world", "hello"])
        assert 'uniqueCount="2"' in result  # dedup
        assert 'count="3"' in result  # total
        assert "<si><t>hello</t></si>" in result


class TestSheetPathResolution:
    def test_resolve_sheet(self, unpacked_xlsx):
        xml = XMLHelpers()
        path = xml.get_sheet_xml_path(unpacked_xlsx, "Sheet1")
        assert os.path.isfile(path)
        assert path.endswith(".xml")
