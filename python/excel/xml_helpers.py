"""XML helpers for OOXML xlsx manipulation: unpack, pack, shift rows, shared strings."""

from __future__ import annotations

import os
import re
import shutil
import zipfile
import xml.dom.minidom
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

from .models import XMLPackError

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

NS_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_XML = "http://www.w3.org/XML/1998/namespace"

# Register namespaces at import so ET.write preserves them in output
ET.register_namespace("", NS_SS)
ET.register_namespace("r", NS_REL)
ET.register_namespace(
    "xdr",
    "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
)
ET.register_namespace(
    "x14", "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
)
ET.register_namespace(
    "mc", "http://schemas.openxmlformats.org/markup-compatibility/2006"
)

NSMAP = {"ss": NS_SS}


def _tag(local: str) -> str:
    """Return Clark notation for a SpreadsheetML tag."""
    return f"{{{NS_SS}}}{local}"


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------


def _pretty_print_xml(content: bytes) -> str:
    """Pretty-print raw XML bytes. Falls back to decoded content on failure."""
    try:
        dom = xml.dom.minidom.parseString(content)
        pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
        lines = [line for line in pretty.splitlines() if line.strip()]
        return "\n".join(lines) + "\n"
    except Exception:
        return content.decode("utf-8", errors="replace")


def _write_tree(tree: ET.ElementTree, path: str | Path) -> None:
    """Write an ElementTree to disk with minidom pretty-printing."""
    p = str(path)
    tree.write(p, encoding="unicode", xml_declaration=False)
    with open(p, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        dom = xml.dom.minidom.parseString(raw.encode("utf-8"))
        pretty = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
        lines = [line for line in pretty.splitlines() if line.strip()]
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Core formula shifting logic (adapted from minimax xlsx_shift_rows.py)
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"(\$?)([A-Z]+)(\$?)(\d+)")


def _shift_refs(text: str, at: int, delta: int) -> str:
    """Shift cell references in a non-quoted formula fragment."""

    def replacer(m: re.Match) -> str:
        dollar_col = m.group(1)
        col_part = m.group(2)
        dollar_row = m.group(3)
        row = int(m.group(4))
        if row >= at:
            row = max(1, row + delta)
        return f"{dollar_col}{col_part}{dollar_row}{row}"

    return _REF_PATTERN.sub(replacer, text)


def shift_formula(formula: str, at: int, delta: int) -> str:
    """Shift row references >= *at* by *delta* in a formula string.

    Correctly skips content inside single-quoted sheet name prefixes
    (e.g. ``'Budget FY2025'!A1`` won't corrupt the year).
    """
    segments = re.split(r"('[^']*(?:''[^']*)*')", formula)
    result = []
    for i, seg in enumerate(segments):
        if i % 2 == 1:
            result.append(seg)  # quoted sheet name, leave untouched
        else:
            result.append(_shift_refs(seg, at, delta))
    return "".join(result)


def shift_sqref(sqref: str, at: int, delta: int) -> str:
    """Shift row references in a space-separated sqref string."""
    parts = sqref.split()
    result = []
    for part in parts:
        if ":" in part:
            left, right = part.split(":", 1)
            result.append(f"{shift_formula(left, at, delta)}:{shift_formula(right, at, delta)}")
        else:
            result.append(shift_formula(part, at, delta))
    return " ".join(result)


def _shift_chart_range(text: str, at: int, delta: int) -> str:
    """Shift row refs inside a chart range like ``Sheet1!$B$5:$B$20``."""
    if "!" not in text:
        return text
    bang = text.index("!")
    return text[: bang + 1] + shift_formula(text[bang + 1 :], at, delta)


# ---------------------------------------------------------------------------
# XML file processors for shift_rows
# ---------------------------------------------------------------------------


def _process_worksheet(path: str, at: int, delta: int) -> int:
    """Update row/cell references in a worksheet XML. Returns change count."""
    tree = ET.parse(path)
    root = tree.getroot()
    changes = 0

    # 1. <dimension ref="...">
    for dim in root.iter(_tag("dimension")):
        old = dim.get("ref", "")
        new = shift_sqref(old, at, delta)
        if new != old:
            dim.set("ref", new)
            changes += 1

    # 2. <row r="N"> and <c r="XN"> inside sheetData
    sheet_data = root.find(_tag("sheetData"))
    if sheet_data is not None:
        for row_el in list(sheet_data):
            r_str = row_el.get("r")
            if r_str is None:
                continue
            r = int(r_str)
            if r >= at:
                row_el.set("r", str(max(1, r + delta)))
                changes += 1
                for cell_el in row_el:
                    cell_ref = cell_el.get("r", "")
                    if cell_ref:
                        new_ref = shift_formula(cell_ref, at, delta)
                        if new_ref != cell_ref:
                            cell_el.set("r", new_ref)
                            changes += 1

            # Update formulas in every row
            for cell_el in row_el:
                f_el = cell_el.find(_tag("f"))
                if f_el is not None and f_el.text:
                    new_f = shift_formula(f_el.text, at, delta)
                    if new_f != f_el.text:
                        f_el.text = new_f
                        changes += 1

    # 3. <mergeCell ref="...">
    for mc in root.iter(_tag("mergeCell")):
        old = mc.get("ref", "")
        new = shift_sqref(old, at, delta)
        if new != old:
            mc.set("ref", new)
            changes += 1

    # 4. <conditionalFormatting sqref="...">
    for cf in root.iter(_tag("conditionalFormatting")):
        old = cf.get("sqref", "")
        new = shift_sqref(old, at, delta)
        if new != old:
            cf.set("sqref", new)
            changes += 1

    # 5. <dataValidation sqref="...">
    for dv in root.iter(_tag("dataValidation")):
        old = dv.get("sqref", "")
        new = shift_sqref(old, at, delta)
        if new != old:
            dv.set("sqref", new)
            changes += 1

    if changes > 0:
        _write_tree(tree, path)
    return changes


def _process_chart(path: str, at: int, delta: int) -> int:
    """Update data range references in a chart XML (regex-based)."""
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()

    def replace_f(m: re.Match) -> str:
        return f"{m.group(1)}{_shift_chart_range(m.group(2), at, delta)}{m.group(3)}"

    new_content = re.sub(
        r"(<(?:[^:>]+:)?f>)([^<]+)(</(?:[^:>]+:)?f>)", replace_f, content
    )
    changed = content != new_content
    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_content)
    return 1 if changed else 0


def _process_table(path: str, at: int, delta: int) -> int:
    """Update the ref attribute on the <table> root element."""
    tree = ET.parse(path)
    root = tree.getroot()
    old = root.get("ref", "")
    if not old:
        return 0
    new = shift_sqref(old, at, delta)
    if new == old:
        return 0
    root.set("ref", new)
    _write_tree(tree, path)
    return 1


def _process_pivot_cache(path: str, at: int, delta: int) -> int:
    """Update worksheetSource ref in a pivot cache definition."""
    tree = ET.parse(path)
    root = tree.getroot()
    changes = 0
    for ws in root.iter():
        if ws.tag.endswith("}worksheetSource") or ws.tag == "worksheetSource":
            old = ws.get("ref", "")
            if old:
                new = shift_sqref(old, at, delta)
                if new != old:
                    ws.set("ref", new)
                    changes += 1
    if changes:
        _write_tree(tree, path)
    return changes


# ---------------------------------------------------------------------------
# XMLHelpers class
# ---------------------------------------------------------------------------


class XMLHelpers:
    """OOXML XML operations: unpack, pack, shift rows, shared strings."""

    # -- unpack / pack --------------------------------------------------

    def unpack(self, xlsx_path: str | Path, work_dir: str | Path) -> None:
        """Unzip an xlsx into *work_dir* with pretty-printed XML."""
        xlsx_path = str(xlsx_path)
        work_dir = str(work_dir)

        if not os.path.isfile(xlsx_path):
            raise XMLPackError(f"File not found: {xlsx_path}")

        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        os.makedirs(work_dir)

        try:
            with zipfile.ZipFile(xlsx_path, "r") as z:
                # Zip-slip protection
                real_out = os.path.realpath(work_dir)
                for member in z.namelist():
                    member_path = os.path.realpath(os.path.join(work_dir, member))
                    if not (
                        member_path.startswith(real_out + os.sep)
                        or member_path == real_out
                    ):
                        shutil.rmtree(work_dir, ignore_errors=True)
                        raise XMLPackError(
                            f"Zip entry {member!r} escapes target directory"
                        )
                z.extractall(work_dir)
        except zipfile.BadZipFile:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise XMLPackError(f"Not a valid ZIP/xlsx file: {xlsx_path}")

        # Pretty-print XML and .rels files
        for dirpath, _, filenames in os.walk(work_dir):
            for fname in filenames:
                if fname.endswith(".xml") or fname.endswith(".rels"):
                    fpath = os.path.join(dirpath, fname)
                    with open(fpath, "rb") as f:
                        raw = f.read()
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(_pretty_print_xml(raw))

    def pack(self, work_dir: str | Path, output_path: str | Path) -> None:
        """Validate XML files and pack *work_dir* into an xlsx."""
        work_dir = str(work_dir)
        output_path = str(output_path)

        if not os.path.isdir(work_dir):
            raise XMLPackError(f"Directory not found: {work_dir}")

        ct = os.path.join(work_dir, "[Content_Types].xml")
        if not os.path.isfile(ct):
            raise XMLPackError("Missing [Content_Types].xml in work directory")

        # Validate all XML
        for dirpath, _, filenames in os.walk(work_dir):
            for fname in filenames:
                if fname.endswith(".xml") or fname.endswith(".rels"):
                    fpath = os.path.join(dirpath, fname)
                    try:
                        ET.parse(fpath)
                    except ET.ParseError as e:
                        rel = os.path.relpath(fpath, work_dir)
                        raise XMLPackError(f"Malformed XML in {rel}: {e}") from e

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for dirpath, _, filenames in os.walk(work_dir):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    arcname = os.path.relpath(fpath, work_dir)
                    z.write(fpath, arcname)

    # -- shift rows -----------------------------------------------------

    def shift_rows(
        self,
        work_dir: str | Path,
        sheet: str | None,
        at_row: int,
        delta: int,
    ) -> int:
        """Shift all row references >= *at_row* by *delta* across relevant XML files.

        Processes: worksheets, charts, tables, pivot caches.
        Returns total number of changes made.
        """
        work_dir = str(work_dir)
        total = 0

        # Worksheets
        ws_dir = os.path.join(work_dir, "xl", "worksheets")
        if os.path.isdir(ws_dir):
            for fname in sorted(os.listdir(ws_dir)):
                if fname.endswith(".xml"):
                    fpath = os.path.join(ws_dir, fname)
                    # If sheet specified, only process matching sheet
                    if sheet is not None:
                        try:
                            resolved = self.get_sheet_xml_path(work_dir, sheet)
                            if os.path.basename(resolved) != fname:
                                continue
                        except Exception:
                            continue
                    total += _process_worksheet(fpath, at_row, delta)

        # Charts
        charts_dir = os.path.join(work_dir, "xl", "charts")
        if os.path.isdir(charts_dir):
            for fname in sorted(os.listdir(charts_dir)):
                if fname.endswith(".xml"):
                    total += _process_chart(
                        os.path.join(charts_dir, fname), at_row, delta
                    )

        # Tables
        tables_dir = os.path.join(work_dir, "xl", "tables")
        if os.path.isdir(tables_dir):
            for fname in sorted(os.listdir(tables_dir)):
                if fname.endswith(".xml"):
                    total += _process_table(
                        os.path.join(tables_dir, fname), at_row, delta
                    )

        # Pivot caches
        cache_dir = os.path.join(work_dir, "xl", "pivotCaches")
        if os.path.isdir(cache_dir):
            for fname in sorted(os.listdir(cache_dir)):
                if "Definition" in fname and fname.endswith(".xml"):
                    total += _process_pivot_cache(
                        os.path.join(cache_dir, fname), at_row, delta
                    )

        return total

    # -- sheet path resolution ------------------------------------------

    def get_sheet_xml_path(self, work_dir: str | Path, sheet: str) -> str:
        """Resolve a sheet name to its worksheet XML file path.

        Walks workbook.xml → workbook.xml.rels → xl/worksheets/sheetN.xml.
        """
        work_dir = str(work_dir)

        # 1. Parse workbook.xml for sheet name → rId mapping
        wb_path = os.path.join(work_dir, "xl", "workbook.xml")
        wb_tree = ET.parse(wb_path)
        wb_root = wb_tree.getroot()
        target_rid: str | None = None
        for s in wb_root.iter(_tag("sheet")):
            if s.get("name") == sheet:
                target_rid = s.get(f"{{{NS_REL}}}id")
                break
        if target_rid is None:
            from .models import SheetNotFoundError

            raise SheetNotFoundError(f"Sheet {sheet!r} not found in workbook")

        # 2. Resolve rId → file path via workbook.xml.rels
        rels_path = os.path.join(work_dir, "xl", "_rels", "workbook.xml.rels")
        rels_tree = ET.parse(rels_path)
        for rel in rels_tree.getroot():
            if rel.get("Id") == target_rid:
                target = rel.get("Target")
                if target:
                    # Strip leading slash
                    target = target.lstrip("/")
                    # If target already starts with xl/, join to work_dir directly
                    if target.startswith("xl/") or target.startswith("xl\\"):
                        return os.path.normpath(os.path.join(work_dir, target))
                    return os.path.normpath(os.path.join(work_dir, "xl", target))
        raise SheetNotFoundError(
            f"Sheet {sheet!r} has rId {target_rid} but no matching relationship"
        )

    # -- shared strings -------------------------------------------------

    def get_shared_strings(self, work_dir: str | Path) -> dict[int, str]:
        """Read sharedStrings.xml and return {index: text}."""
        work_dir = str(work_dir)
        ss_path = os.path.join(work_dir, "xl", "sharedStrings.xml")
        if not os.path.isfile(ss_path):
            return {}

        tree = ET.parse(ss_path)
        root = tree.getroot()
        result: dict[int, str] = {}
        for idx, si in enumerate(root.iter(_tag("si"))):
            # Handle both simple <si><t>text</t></si> and rich text <si><r><t>text</t></r></si>
            t_el = si.find(_tag("t"))
            if t_el is not None and t_el.text:
                result[idx] = t_el.text
            else:
                # Rich text: concatenate all <t> elements
                parts = []
                for t in si.iter(_tag("t")):
                    if t.text:
                        parts.append(t.text)
                result[idx] = "".join(parts)
        return result

    def find_or_add_shared_string(self, work_dir: str | Path, text: str) -> int:
        """Find existing string index or append a new entry. Returns the index.

        NOTE: This method is no longer used by the writer (which now uses inline strings).
        It is kept for backward compatibility with any external callers.
        """
        work_dir = str(work_dir)
        ss_path = os.path.join(work_dir, "xl", "sharedStrings.xml")

        # Create sharedStrings.xml if it doesn't exist
        if not os.path.isfile(ss_path):
            self._create_empty_shared_strings(ss_path)
            self._register_shared_strings_content_type(work_dir)
            self._register_shared_strings_rel(work_dir)

        tree = ET.parse(ss_path)
        root = tree.getroot()

        # Search existing
        for idx, si in enumerate(root.iter(_tag("si"))):
            t_el = si.find(_tag("t"))
            if t_el is not None and t_el.text == text:
                return idx

        # Not found — append new <si>
        si = ET.SubElement(root, _tag("si"))
        t = ET.SubElement(si, _tag("t"))
        t.text = text
        # Preserve whitespace if needed
        if text and (text[0] in " \t\n" or text[-1] in " \t\n"):
            t.set(f"{{{NS_XML}}}space", "preserve")

        # Update count attributes
        count = root.get("count")
        unique_count = root.get("uniqueCount")
        if count is not None:
            root.set("count", str(int(count) + 1))
        if unique_count is not None:
            root.set("uniqueCount", str(int(unique_count) + 1))

        _write_tree(tree, ss_path)
        return int(unique_count) if unique_count else 0

    @staticmethod
    def _create_empty_shared_strings(ss_path: str) -> None:
        """Create a minimal sharedStrings.xml with zero entries."""
        os.makedirs(os.path.dirname(ss_path), exist_ok=True)
        content = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0" uniqueCount="0"/>'
        )
        with open(ss_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _register_shared_strings_content_type(work_dir: str) -> None:
        """Ensure sharedStrings is registered in [Content_Types].xml."""
        ct_path = os.path.join(work_dir, "[Content_Types].xml")
        if not os.path.isfile(ct_path):
            return
        tree = ET.parse(ct_path)
        root = tree.getroot()
        ns = "{http://schemas.openxmlformats.org/package/2006/content-types}"
        for override in root.iter(f"{ns}Override"):
            if override.get("PartName") == "/xl/sharedStrings.xml":
                return
        override = ET.SubElement(root, f"{ns}Override")
        override.set("PartName", "/xl/sharedStrings.xml")
        override.set("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
        _write_tree(tree, ct_path)

    @staticmethod
    def _register_shared_strings_rel(work_dir: str) -> None:
        """Ensure sharedStrings is referenced in workbook.xml.rels."""
        rels_path = os.path.join(work_dir, "xl", "_rels", "workbook.xml.rels")
        if not os.path.isfile(rels_path):
            return
        tree = ET.parse(rels_path)
        root = tree.getroot()
        ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
        for rel in root.iter(f"{ns}Relationship"):
            if rel.get("Target") == "sharedStrings.xml":
                return
        max_id = 0
        for rel in root.iter(f"{ns}Relationship"):
            rid = rel.get("Id", "")
            if rid.startswith("rId"):
                try:
                    max_id = max(max_id, int(rid[3:]))
                except ValueError:
                    pass
        rel = ET.SubElement(root, f"{ns}Relationship")
        rel.set("Id", f"rId{max_id + 1}")
        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings")
        rel.set("Target", "sharedStrings.xml")
        _write_tree(tree, rels_path)

    def build_shared_strings(self, strings: list[str]) -> str:
        """Build a complete sharedStrings.xml from a string list."""
        # Deduplicate while preserving order
        seen: dict[str, int] = {}
        unique: list[str] = []
        for s in strings:
            if s not in seen:
                seen[s] = len(unique)
                unique.append(s)

        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            f' count="{len(strings)}" uniqueCount="{len(unique)}">',
        ]
        for s in unique:
            escaped = (
                s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            preserve = ' xml:space="preserve"' if s and (s[0] in " \t\n" or s[-1] in " \t\n") else ""
            lines.append(f"  <si><t{preserve}>{escaped}</t></si>")
        lines.append("</sst>")
        return "\n".join(lines) + "\n"
