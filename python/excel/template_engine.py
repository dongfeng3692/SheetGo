"""Template engine: create xlsx files from the minimal template."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .xml_helpers import XMLHelpers, _tag, _write_tree
from .models import col_letter

import xml.etree.ElementTree as ET


class TemplateEngine:
    """Create new xlsx files from the minimal template."""

    def __init__(self) -> None:
        self._templates_dir = os.path.join(
            os.path.dirname(__file__), "templates", "minimal_xlsx"
        )
        self._xml = XMLHelpers()

    def create_minimal(
        self,
        output_path: str | Path,
        sheets: list[str] | None = None,
    ) -> None:
        """Create a minimal xlsx file at *output_path*.

        If *sheets* is provided, customize sheet names.
        Default: single sheet named "Sheet1".
        """
        output_path = str(output_path)
        work_dir = output_path + ".tmp"

        # Copy template
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        shutil.copytree(self._templates_dir, work_dir)

        if sheets and len(sheets) != 1 or (sheets and sheets[0] != "Sheet1"):
            self._customize_sheets(work_dir, sheets or ["Sheet1"])

        # Pack
        self._xml.pack(work_dir, output_path)

        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)

    def _customize_sheets(self, work_dir: str, sheets: list[str]) -> None:
        """Customize the template for multiple/renamed sheets."""
        # Update workbook.xml
        wb_path = os.path.join(work_dir, "xl", "workbook.xml")
        wb_tree = ET.parse(wb_path)
        wb_root = wb_tree.getroot()
        sheets_el = wb_root.find(_tag("sheets"))

        if sheets_el is None:
            return

        # Clear existing sheets
        for s in list(sheets_el):
            sheets_el.remove(s)

        for i, name in enumerate(sheets, 1):
            s = ET.SubElement(sheets_el, _tag("sheet"))
            s.set("name", name)
            s.set("sheetId", str(i))
            s.set(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
                f"rId{i + 2}",  # rId1/rId2 are usually taken
            )

        _write_tree(wb_tree, wb_path)

        # Create additional worksheet XMLs if needed
        ws_dir = os.path.join(work_dir, "xl", "worksheets")
        for i in range(2, len(sheets) + 1):
            src = os.path.join(ws_dir, "sheet1.xml")
            dst = os.path.join(ws_dir, f"sheet{i}.xml")
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

        # Update rels
        rels_path = os.path.join(work_dir, "xl", "_rels", "workbook.xml.rels")
        rels_tree = ET.parse(rels_path)
        rels_root = rels_tree.getroot()

        # Clear and rebuild
        for r in list(rels_root):
            rels_root.remove(r)

        # Add rels for each sheet
        for i in range(1, len(sheets) + 1):
            r = ET.SubElement(rels_root, "Relationship")
            r.set("Id", f"rId{i + 2}")
            r.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet")
            r.set("Target", f"worksheets/sheet{i}.xml")

        _write_tree(rels_tree, rels_path)

    @staticmethod
    def get_style_slot(slot_name: str) -> int:
        """Look up a style slot index by name."""
        from .style_engine import STYLE_SLOTS
        for slot in STYLE_SLOTS:
            if slot.role == slot_name:
                return slot.index
        return 0
