"""Excel writer: XML-level precise writes that preserve formatting."""

from __future__ import annotations

import copy
import datetime as _dt
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import xml.etree.ElementTree as ET

from .models import (
    CellEdit,
    CellRange,
    EditResult,
    SheetNotFoundError,
    col_letter,
    col_number,
    parse_cell_ref,
)
from .xml_helpers import XMLHelpers, _tag, _write_tree

# Namespace shortcut
_NS_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Excel epoch: 1899-12-30 (the bogus leap-year bug is included)
_EXCEL_EPOCH = _dt.datetime(1899, 12, 30)


def _datetime_to_serial(dt: _dt.datetime) -> float:
    """Convert Python datetime to Excel serial date number."""
    delta = dt - _EXCEL_EPOCH
    return delta.days + delta.seconds / 86400.0


_DATE_NUMFMT = "yyyy-mm-dd"
_DATETIME_NUMFMT = "yyyy-mm-dd\\ hh:mm:ss"


class ExcelWriter:
    """XML-level Excel writer. All modifications preserve existing formatting."""

    def __init__(self) -> None:
        self._xml = XMLHelpers()

    # -- temp workdir safety wrapper -------------------------------------

    def _with_temp_workdir(
        self,
        file_path: str | Path,
        func,
        *args,
        **kwargs,
    ) -> Any:
        """Execute *func* inside an unpack→modify→pack cycle.

        Creates a backup before modification. Restores backup on failure.
        """
        file_path = str(file_path)
        backup = file_path + ".bak"
        shutil.copy2(file_path, backup)
        work_dir = tempfile.mkdtemp(prefix="exceler_")
        try:
            self._xml.unpack(file_path, work_dir)
            result = func(work_dir, *args, **kwargs)
            self._xml.pack(work_dir, file_path)
            return result
        except Exception:
            # Restore backup on any failure
            shutil.copy2(backup, file_path)
            raise
        finally:
            if os.path.isdir(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
            if os.path.isfile(backup):
                os.remove(backup)

    # -- write_cells -----------------------------------------------------

    def write_cells(
        self,
        file_path: str | Path,
        edits: list[CellEdit],
        preserve_format: bool = True,
    ) -> EditResult:
        """Batch-write cells. Each CellEdit specifies sheet, cell, value."""
        return self._with_temp_workdir(
            file_path, self._write_cells_impl, edits, preserve_format
        )

    def _write_cells_impl(
        self,
        work_dir: str,
        edits: list[CellEdit],
        preserve_format: bool,
    ) -> EditResult:
        affected: list[str] = []
        formulas: list[str] = []
        warnings: list[str] = []

        # Group edits by sheet
        by_sheet: dict[str, list[CellEdit]] = {}
        for edit in edits:
            by_sheet.setdefault(edit.sheet, []).append(edit)

        for sheet, sheet_edits in by_sheet.items():
            ws_path = self._xml.get_sheet_xml_path(work_dir, sheet)
            tree = ET.parse(ws_path)
            root = tree.getroot()
            sheet_data = root.find(_tag("sheetData"))
            if sheet_data is None:
                warnings.append(f"No sheetData in {sheet}")
                continue

            max_written_col: str | None = None
            max_written_row = 0

            for edit in sheet_edits:
                col_letters, row_num = parse_cell_ref(edit.cell)
                r_str = str(row_num)
                cell_ref = f"{col_letters}{row_num}"
                max_written_row = max(max_written_row, row_num)
                if max_written_col is None or col_number(col_letters) > col_number(max_written_col):
                    max_written_col = col_letters

                # Find or create row
                row_el = None
                for r in sheet_data:
                    if r.get("r") == r_str:
                        row_el = r
                        break
                if row_el is None:
                    row_el = self._insert_row_element(sheet_data, row_num)

                # Find or create cell
                cell_el = None
                for c in row_el:
                    if c.get("r") == cell_ref:
                        cell_el = c
                        break

                value = edit.value

                if isinstance(value, str) and value.startswith("="):
                    # Formula
                    if cell_el is None:
                        cell_el = ET.SubElement(row_el, _tag("c"))
                        cell_el.set("r", cell_ref)
                    # Remove existing <v> (calculated value)
                    for v in cell_el.findall(_tag("v")):
                        cell_el.remove(v)
                    # Remove existing <f>
                    for f in cell_el.findall(_tag("f")):
                        cell_el.remove(f)
                    # Remove type attribute (formulas don't use t="s" etc.)
                    if "t" in cell_el.attrib:
                        del cell_el.attrib["t"]

                    f_el = ET.SubElement(cell_el, _tag("f"))
                    f_el.text = value.lstrip("=")
                    formulas.append(cell_ref)
                else:
                    # Static value
                    if cell_el is None:
                        cell_el = ET.SubElement(row_el, _tag("c"))
                        cell_el.set("r", cell_ref)
                    elif not preserve_format:
                        # Clear existing content
                        for child in list(cell_el):
                            cell_el.remove(child)

                    # Remove existing <f> and <v>
                    for f in cell_el.findall(_tag("f")):
                        cell_el.remove(f)
                    for v in cell_el.findall(_tag("v")):
                        cell_el.remove(v)
                    for is_el in cell_el.findall(_tag("is")):
                        cell_el.remove(is_el)

                    if isinstance(value, str):
                        # String → inline string (no sharedStrings.xml needed)
                        cell_el.set("t", "inlineStr")
                        is_el = ET.SubElement(cell_el, _tag("is"))
                        t_el = ET.SubElement(is_el, _tag("t"))
                        t_el.text = value
                        if value and (value[0] in " \t\n" or value[-1] in " \t\n"):
                            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    elif isinstance(value, _dt.datetime):
                        # datetime → Excel serial number + date style
                        serial = _datetime_to_serial(value)
                        cell_el.attrib.pop("t", None)
                        v_el = ET.SubElement(cell_el, _tag("v"))
                        v_el.text = str(serial)
                        # Apply date format style (preserve existing style attrs)
                        numfmt = _DATETIME_NUMFMT if value.hour or value.minute or value.second else _DATE_NUMFMT
                        cur_style = int(cell_el.get("s", "0"))
                        date_style = self._ensure_numfmt_style(work_dir, cur_style, numfmt)
                        cell_el.set("s", str(date_style))
                    elif isinstance(value, _dt.date):
                        # bare date → convert to datetime midnight then serial
                        serial = _datetime_to_serial(_dt.datetime(value.year, value.month, value.day))
                        cell_el.attrib.pop("t", None)
                        v_el = ET.SubElement(cell_el, _tag("v"))
                        v_el.text = str(serial)
                        cur_style = int(cell_el.get("s", "0"))
                        date_style = self._ensure_numfmt_style(work_dir, cur_style, _DATE_NUMFMT)
                        cell_el.set("s", str(date_style))
                    elif isinstance(value, bool):
                        cell_el.set("t", "b")
                        v_el = ET.SubElement(cell_el, _tag("v"))
                        v_el.text = "1" if value else "0"
                    elif isinstance(value, (int, float)):
                        cell_el.attrib.pop("t", None)
                        v_el = ET.SubElement(cell_el, _tag("v"))
                        v_el.text = str(value)
                    elif value is None:
                        # Clear cell
                        cell_el.attrib.pop("t", None)
                    else:
                        # Fallback: convert to inline string
                        cell_el.set("t", "inlineStr")
                        is_el = ET.SubElement(cell_el, _tag("is"))
                        t_el = ET.SubElement(is_el, _tag("t"))
                        t_el.text = str(value)

                # Apply style if specified
                if edit.style and "s" in edit.style:
                    cell_el.set("s", str(edit.style["s"]))

                affected.append(f"{sheet}!{cell_ref}")

            if max_written_col is not None and max_written_row > 0:
                self._update_dimension(root, max_written_col, max_written_row)

            _write_tree(tree, ws_path)

        return EditResult.ok(cells=affected, formulas=formulas, warnings=warnings)

    # -- add_formula -----------------------------------------------------

    def add_formula(
        self,
        file_path: str | Path,
        sheet: str,
        cell: str,
        formula: str,
    ) -> EditResult:
        """Write a formula to a cell. Convenience wrapper for write_cells."""
        edit = CellEdit(sheet=sheet, cell=cell, value=formula)
        return self.write_cells(file_path, [edit])

    # -- add_column ------------------------------------------------------

    def add_column(
        self,
        file_path: str | Path,
        sheet: str,
        col: str,
        header: str | None = None,
        data: list[Any] | None = None,
        formula: str | None = None,
        formula_rows: tuple[int, int] | None = None,
        numfmt: str | None = None,
    ) -> EditResult:
        """Add a column to a worksheet."""
        return self._with_temp_workdir(
            file_path, self._add_column_impl,
            sheet, col.upper(), header, data, formula, formula_rows, numfmt,
        )

    def _add_column_impl(
        self,
        work_dir: str,
        sheet: str,
        col: str,
        header: str | None,
        data: list[Any] | None,
        formula: str | None,
        formula_rows: tuple[int, int] | None,
        numfmt: str | None,
    ) -> EditResult:
        ws_path = self._xml.get_sheet_xml_path(work_dir, sheet)
        prev_col = col_letter(col_number(col) - 1) if col_number(col) > 1 else "A"

        ws_tree = ET.parse(ws_path)
        changes = 0

        # Resolve styles from previous column
        header_style = self._get_cell_style(ws_tree, prev_col, 1) if header else 0

        data_style = None
        if formula_rows:
            start_row = formula_rows[0]
            ref_style = self._get_cell_style(ws_tree, prev_col, start_row)
            data_style = (
                self._ensure_numfmt_style(work_dir, ref_style, numfmt)
                if numfmt else ref_style
            )

        # Re-parse tree
        ws_tree = ET.parse(ws_path)
        root = ws_tree.getroot()
        sheet_data = root.find(_tag("sheetData"))

        row_map = self._build_row_map(sheet_data)

        # Header cell
        if header and 1 in row_map:
            cell = ET.SubElement(row_map[1], _tag("c"))
            cell.set("r", f"{col}1")
            cell.set("s", str(header_style))
            cell.set("t", "inlineStr")
            is_el = ET.SubElement(cell, _tag("is"))
            t_el = ET.SubElement(is_el, _tag("t"))
            t_el.text = header
            changes += 1

        # Formula cells
        if formula and formula_rows:
            start, end = formula_rows
            for row_num in range(start, end + 1):
                if row_num not in row_map:
                    row_el = ET.SubElement(sheet_data, _tag("row"))
                    row_el.set("r", str(row_num))
                    row_map[row_num] = row_el

                formula_text = formula.replace("{row}", str(row_num)).lstrip("=")
                cell = ET.SubElement(row_map[row_num], _tag("c"))
                cell.set("r", f"{col}{row_num}")
                if data_style is not None:
                    cell.set("s", str(data_style))
                f_el = ET.SubElement(cell, _tag("f"))
                f_el.text = formula_text
                changes += 1

        # Static data cells
        if data:
            for i, val in enumerate(data):
                row_num = i + 2  # Data starts at row 2 (row 1 is header)
                if row_num not in row_map:
                    row_el = ET.SubElement(sheet_data, _tag("row"))
                    row_el.set("r", str(row_num))
                    row_map[row_num] = row_el

                cell = ET.SubElement(row_map[row_num], _tag("c"))
                cell.set("r", f"{col}{row_num}")
                if data_style is not None:
                    cell.set("s", str(data_style))

                if isinstance(val, str):
                    cell.set("t", "inlineStr")
                    is_el = ET.SubElement(cell, _tag("is"))
                    t_el = ET.SubElement(is_el, _tag("t"))
                    t_el.text = val
                elif isinstance(val, (int, float)):
                    v = ET.SubElement(cell, _tag("v"))
                    v.text = str(val)
                changes += 1

        # Update dimension
        max_row = 1
        if formula_rows:
            max_row = max(max_row, formula_rows[1])
        if data:
            max_row = max(max_row, len(data) + 1)
        self._update_dimension(root, col, max_row)

        # Extend <cols> if needed
        self._extend_cols(root, col, prev_col)

        _write_tree(ws_tree, ws_path)
        affected = [f"{sheet}!{col}{r}" for r in range(1, changes + 1)]
        return EditResult.ok(cells=affected)

    # -- insert_row ------------------------------------------------------

    def insert_row(
        self,
        file_path: str | Path,
        sheet: str,
        at_row: int,
        values: dict[str, Any] | None = None,
        formula: dict[str, str] | None = None,
        copy_style_from: int | None = None,
    ) -> EditResult:
        """Insert a row at *at_row*, shifting existing rows down."""
        return self._with_temp_workdir(
            file_path, self._insert_row_impl,
            sheet, at_row, values, formula, copy_style_from,
        )

    def _insert_row_impl(
        self,
        work_dir: str,
        sheet: str,
        at_row: int,
        values: dict[str, Any] | None,
        formula: dict[str, str] | None,
        copy_style_from: int | None,
    ) -> EditResult:
        # Step 1: Shift rows down
        self._xml.shift_rows(work_dir, sheet, at_row, delta=1)

        ws_path = self._xml.get_sheet_xml_path(work_dir, sheet)
        tree = ET.parse(ws_path)
        root = tree.getroot()
        sheet_data = root.find(_tag("sheetData"))

        # Step 2: Get style from reference row
        style_map: dict[str, int] = {}
        if copy_style_from is not None:
            style_map = self._get_row_styles(tree, copy_style_from)

        # Step 3: Build new row
        row_el = ET.SubElement(sheet_data, _tag("row"))
        row_el.set("r", str(at_row))

        # Re-sort rows by number
        self._sort_rows(sheet_data)

        # Add value cells
        affected: list[str] = []
        formulas: list[str] = []

        if values:
            for col, val in values.items():
                col = col.upper()
                cell_ref = f"{col}{at_row}"
                cell = ET.SubElement(row_el, _tag("c"))
                cell.set("r", cell_ref)

                if col in style_map:
                    cell.set("s", str(style_map[col]))

                if isinstance(val, str):
                    cell.set("t", "inlineStr")
                    is_el = ET.SubElement(cell, _tag("is"))
                    t_el = ET.SubElement(is_el, _tag("t"))
                    t_el.text = val
                elif isinstance(val, (int, float)):
                    v = ET.SubElement(cell, _tag("v"))
                    v.text = str(val)

                affected.append(f"{sheet}!{cell_ref}")

        # Add formula cells
        if formula:
            for col, f_text in formula.items():
                col = col.upper()
                cell_ref = f"{col}{at_row}"
                cell = ET.SubElement(row_el, _tag("c"))
                cell.set("r", cell_ref)

                if col in style_map:
                    cell.set("s", str(style_map[col]))

                f_el = ET.SubElement(cell, _tag("f"))
                f_el.text = f_text.replace("{row}", str(at_row)).lstrip("=")
                formulas.append(cell_ref)
                affected.append(f"{sheet}!{cell_ref}")

        _write_tree(tree, ws_path)
        return EditResult.ok(cells=affected, formulas=formulas)

    # -- delete_rows -----------------------------------------------------

    def delete_rows(
        self,
        file_path: str | Path,
        sheet: str,
        start: int,
        count: int = 1,
    ) -> EditResult:
        """Delete rows [start, start+count) and shift remaining up."""
        return self._with_temp_workdir(
            file_path, self._delete_rows_impl, sheet, start, count,
        )

    def _delete_rows_impl(
        self,
        work_dir: str,
        sheet: str,
        start: int,
        count: int,
    ) -> EditResult:
        ws_path = self._xml.get_sheet_xml_path(work_dir, sheet)
        tree = ET.parse(ws_path)
        root = tree.getroot()
        sheet_data = root.find(_tag("sheetData"))
        if sheet_data is None:
            return EditResult.ok()

        # Remove rows in [start, start+count)
        removed: list[str] = []
        for row_el in list(sheet_data):
            r_str = row_el.get("r")
            if r_str is None:
                continue
            r = int(r_str)
            if start <= r < start + count:
                removed.append(f"{sheet}!Row {r}")
                sheet_data.remove(row_el)

        # Shift remaining rows up
        for row_el in sheet_data:
            r_str = row_el.get("r")
            if r_str is None:
                continue
            r = int(r_str)
            if r >= start + count:
                row_el.set("r", str(r - count))
                # Update cell refs
                for cell_el in row_el:
                    old_ref = cell_el.get("r", "")
                    if old_ref:
                        col_part = re.match(r"([A-Z]+)", old_ref).group(1)
                        cell_el.set("r", f"{col_part}{r - count}")

        _write_tree(tree, ws_path)

        # Also shift formula references
        self._xml.shift_rows(work_dir, sheet, start, delta=-count)

        return EditResult.ok(cells=removed)

    # -- apply_style -----------------------------------------------------

    def apply_style(
        self,
        file_path: str | Path,
        sheet: str,
        cell_range: CellRange,
        style_index: int,
    ) -> EditResult:
        """Apply a style index to all cells in the given range."""
        return self._with_temp_workdir(
            file_path, self._apply_style_impl, sheet, cell_range, style_index,
        )

    def _apply_style_impl(
        self,
        work_dir: str,
        sheet: str,
        cell_range: CellRange,
        style_index: int,
    ) -> EditResult:
        ws_path = self._xml.get_sheet_xml_path(work_dir, sheet)
        tree = ET.parse(ws_path)
        root = tree.getroot()
        sheet_data = root.find(_tag("sheetData"))
        if sheet_data is None:
            return EditResult.ok()

        start_cn = col_number(cell_range.start_col)
        end_cn = col_number(cell_range.end_col)
        affected: list[str] = []

        for row_el in sheet_data:
            r_str = row_el.get("r")
            if r_str is None:
                continue
            r = int(r_str)
            if r < cell_range.start_row or r > cell_range.end_row:
                continue

            # Collect existing cells in range
            cells_by_col: dict[str, ET.Element] = {}
            for cell_el in row_el:
                ref = cell_el.get("r", "")
                m = re.match(r"([A-Z]+)(\d+)", ref)
                if m:
                    cn = col_number(m.group(1))
                    if start_cn <= cn <= end_cn:
                        cells_by_col[m.group(1)] = cell_el

            # Set style on existing cells, create empty cells for gaps
            for cn in range(start_cn, end_cn + 1):
                cl = col_letter(cn)
                cell_ref = f"{cl}{r}"
                if cl in cells_by_col:
                    cells_by_col[cl].set("s", str(style_index))
                else:
                    cell_el = ET.SubElement(row_el, _tag("c"))
                    cell_el.set("r", cell_ref)
                    cell_el.set("s", str(style_index))
                affected.append(f"{sheet}!{cell_ref}")

        _write_tree(tree, ws_path)
        return EditResult.ok(cells=affected)

    # -- create_sheet ----------------------------------------------------

    def create_sheet(
        self,
        file_path: str | Path,
        name: str,
    ) -> EditResult:
        """Create a new worksheet in the workbook."""
        return self._with_temp_workdir(
            file_path, self._create_sheet_impl, name,
        )

    def _create_sheet_impl(self, work_dir: str, name: str) -> EditResult:
        # 1. Determine next sheet number
        ws_dir = os.path.join(work_dir, "xl", "worksheets")
        existing = [f for f in os.listdir(ws_dir) if f.endswith(".xml")]
        sheet_num = len(existing) + 1
        sheet_file = f"sheet{sheet_num}.xml"
        sheet_path = os.path.join(ws_dir, sheet_file)

        # 2. Create minimal worksheet XML
        ws_root = ET.Element(_tag("worksheet"))
        ns_ss = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ws_root.set("xmlns", ns_ss)
        dim = ET.SubElement(ws_root, _tag("dimension"))
        dim.set("ref", "A1")
        sd = ET.SubElement(ws_root, _tag("sheetData"))
        ws_tree = ET.ElementTree(ws_root)
        _write_tree(ws_tree, sheet_path)

        # 3. Update workbook.xml
        wb_path = os.path.join(work_dir, "xl", "workbook.xml")
        wb_tree = ET.parse(wb_path)
        wb_root = wb_tree.getroot()
        sheets_el = wb_root.find(_tag("sheets"))
        if sheets_el is None:
            return EditResult.fail(warnings=["No <sheets> element in workbook.xml"])

        # Find next rId
        rid = f"rId{sheet_num + 10}"  # offset to avoid clashes
        existing_rids = {s.get(f"{{{_NS_REL}}}id") for s in sheets_el}
        while rid in existing_rids:
            sheet_num_rid = int(rid[3:]) + 1
            rid = f"rId{sheet_num_rid}"

        sheet_el = ET.SubElement(sheets_el, _tag("sheet"))
        sheet_el.set("name", name)
        sheet_el.set("sheetId", str(sheet_num))
        sheet_el.set(f"{{{_NS_REL}}}id", rid)
        _write_tree(wb_tree, wb_path)

        # 4. Update workbook.xml.rels
        rels_path = os.path.join(work_dir, "xl", "_rels", "workbook.xml.rels")
        rels_tree = ET.parse(rels_path)
        rels_root = rels_tree.getroot()
        rel_el = ET.SubElement(rels_root, "Relationship")
        rel_el.set("Id", rid)
        rel_el.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet")
        rel_el.set("Target", f"worksheets/{sheet_file}")
        _write_tree(rels_tree, rels_path)

        # 5. Update [Content_Types].xml
        ct_path = os.path.join(work_dir, "[Content_Types].xml")
        ct_tree = ET.parse(ct_path)
        ct_root = ct_tree.getroot()
        override = ET.SubElement(ct_root, "Override")
        override.set("PartName", f"/xl/worksheets/{sheet_file}")
        override.set("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
        _write_tree(ct_tree, ct_path)

        return EditResult.ok(cells=[f"{name}!A1"])

    # -- private helpers -------------------------------------------------

    @staticmethod
    def _get_cell_style(
        ws_tree: ET.ElementTree, col: str, row: int
    ) -> int:
        """Get the style index of a cell in the worksheet."""
        ref = f"{col}{row}"
        for row_el in ws_tree.getroot().iter(_tag("row")):
            if row_el.get("r") == str(row):
                for c in row_el:
                    if c.get("r") == ref:
                        return int(c.get("s", "0"))
        return 0

    @staticmethod
    def _get_row_styles(
        ws_tree: ET.ElementTree, row_num: int
    ) -> dict[str, int]:
        """Get {col_letter: style_index} for all cells in a row."""
        result: dict[str, int] = {}
        for row_el in ws_tree.getroot().iter(_tag("row")):
            if row_el.get("r") == str(row_num):
                for c in row_el:
                    ref = c.get("r", "")
                    m = re.match(r"([A-Z]+)", ref)
                    if m and "s" in c.attrib:
                        result[m.group(1)] = int(c.get("s"))
                break
        return result

    @staticmethod
    def _ensure_numfmt_style(
        work_dir: str, ref_style_idx: int, numfmt_code: str
    ) -> int:
        """Clone a cellXfs entry with a given numfmt. Returns new style index."""
        styles_path = os.path.join(work_dir, "xl", "styles.xml")
        tree = ET.parse(styles_path)
        root = tree.getroot()

        # Find or add numFmt
        numfmts = root.find(_tag("numFmts"))
        numfmt_id = None
        if numfmts is not None:
            for nf in numfmts:
                if nf.get("formatCode") == numfmt_code:
                    numfmt_id = int(nf.get("numFmtId"))
                    break

        if numfmt_id is None:
            max_id = 163
            if numfmts is not None:
                for nf in numfmts:
                    max_id = max(max_id, int(nf.get("numFmtId", "0")))
            else:
                numfmts = ET.SubElement(root, _tag("numFmts"))
                numfmts.set("count", "0")

            numfmt_id = max_id + 1
            nf = ET.SubElement(numfmts, _tag("numFmt"))
            nf.set("numFmtId", str(numfmt_id))
            nf.set("formatCode", numfmt_code)
            numfmts.set("count", str(len(list(numfmts))))

        # Find or create matching cellXfs entry
        cellxfs = root.find(_tag("cellXfs"))
        xf_list = list(cellxfs)
        ref_xf = xf_list[min(ref_style_idx, len(xf_list) - 1)]

        for i, xf in enumerate(xf_list):
            if (xf.get("numFmtId") == str(numfmt_id)
                    and xf.get("fontId") == ref_xf.get("fontId")
                    and xf.get("fillId") == ref_xf.get("fillId")
                    and xf.get("borderId") == ref_xf.get("borderId")):
                return i

        new_xf = copy.deepcopy(ref_xf)
        new_xf.set("numFmtId", str(numfmt_id))
        new_xf.set("applyNumberFormat", "true")
        cellxfs.append(new_xf)
        cellxfs.set("count", str(len(list(cellxfs))))

        _write_tree(tree, styles_path)
        return len(list(cellxfs)) - 1

    @staticmethod
    def _insert_row_element(
        sheet_data: ET.Element, row_num: int
    ) -> ET.Element:
        """Insert a <row> element at the correct sorted position."""
        row_el = ET.SubElement(sheet_data, _tag("row"))
        row_el.set("r", str(row_num))
        ExcelWriter._sort_rows(sheet_data)
        return row_el

    @staticmethod
    def _sort_rows(sheet_data: ET.Element) -> None:
        """Sort <row> children by their r attribute."""
        rows = list(sheet_data)
        rows.sort(key=lambda r: int(r.get("r", "0")))
        for r in list(sheet_data):
            sheet_data.remove(r)
        for r in rows:
            sheet_data.append(r)

    @staticmethod
    def _build_row_map(sheet_data: ET.Element) -> dict[int, ET.Element]:
        """Build {row_number: row_element} from sheetData."""
        result: dict[int, ET.Element] = {}
        for row_el in sheet_data:
            r = row_el.get("r")
            if r:
                result[int(r)] = row_el
        return result

    @staticmethod
    def _update_dimension(root: ET.Element, new_col: str, new_row: int) -> None:
        """Expand <dimension ref="..."> if the written cell exceeds current bounds."""
        for dim in root.iter(_tag("dimension")):
            old_ref = dim.get("ref", "")
            if not old_ref:
                dim.set("ref", f"A1:{new_col}{new_row}")
                return

            if ":" in old_ref:
                start_ref, end_ref = old_ref.split(":", 1)
            else:
                start_ref = old_ref
                end_ref = old_ref

            end_col_match = re.match(r"([A-Z]+)", end_ref)
            end_row_match = re.search(r"(\d+)", end_ref)
            end_col = end_col_match.group(1) if end_col_match else new_col
            end_row = int(end_row_match.group(1)) if end_row_match else new_row

            final_col = end_col
            if col_number(new_col) > col_number(end_col):
                final_col = new_col

            final_row = max(end_row, new_row)
            dim.set("ref", f"{start_ref}:{final_col}{final_row}")
            return

        dim = ET.SubElement(root, _tag("dimension"))
        dim.set("ref", f"A1:{new_col}{new_row}")

    @staticmethod
    def _extend_cols(
        root: ET.Element, new_col: str, prev_col: str
    ) -> None:
        """Clone previous column's <col> definition for the new column."""
        cols_el = root.find(_tag("cols"))
        if cols_el is None:
            return
        new_cn = col_number(new_col)
        # Already covered?
        for c in cols_el:
            if int(c.get("min", "0")) <= new_cn <= int(c.get("max", "0")):
                return
        # Clone from previous
        prev_cn = col_number(prev_col)
        for c in cols_el:
            if int(c.get("min", "0")) <= prev_cn <= int(c.get("max", "0")):
                new_col_def = copy.deepcopy(c)
                new_col_def.set("min", str(new_cn))
                new_col_def.set("max", str(new_cn))
                cols_el.append(new_col_def)
                break
