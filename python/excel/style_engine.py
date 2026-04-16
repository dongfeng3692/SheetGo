"""Style engine: 13-slot financial format system."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import EditResult, StyleConfig, StyleSlot
from .writer import ExcelWriter

# ---------------------------------------------------------------------------
# Predefined style slots matching templates/minimal_xlsx/xl/styles.xml
# ---------------------------------------------------------------------------

STYLE_SLOTS: list[StyleSlot] = [
    # idx 0: default
    StyleSlot(index=0, role="default", font_color=None, numfmt_type="general"),
    # idx 1: input (blue text, no numfmt)
    StyleSlot(index=1, role="input", font_color="blue", numfmt_type="general"),
    # idx 2: input currency
    StyleSlot(index=2, role="input", font_color="blue", numfmt_type="currency"),
    # idx 3: input percent
    StyleSlot(index=3, role="input", font_color="blue", numfmt_type="percent"),
    # idx 4: input integer
    StyleSlot(index=4, role="input", font_color="blue", numfmt_type="integer"),
    # idx 5: formula (black text)
    StyleSlot(index=5, role="formula", font_color="black", numfmt_type="general"),
    # idx 6: formula currency
    StyleSlot(index=6, role="formula", font_color="black", numfmt_type="currency"),
    # idx 7: formula percent
    StyleSlot(index=7, role="formula", font_color="black", numfmt_type="percent"),
    # idx 8: formula integer
    StyleSlot(index=8, role="formula", font_color="black", numfmt_type="integer"),
    # idx 9: cross-sheet (green text)
    StyleSlot(index=9, role="cross_sheet", font_color="green", numfmt_type="general"),
    # idx 10: cross-sheet currency
    StyleSlot(index=10, role="cross_sheet", font_color="green", numfmt_type="currency"),
    # idx 11: header (bold black)
    StyleSlot(index=11, role="header", font_color="black_bold", numfmt_type="general"),
    # idx 12: highlight (yellow background)
    StyleSlot(index=12, role="highlight", font_color=None, numfmt_type="highlight"),
]

# Semantic colors
COLORS = {
    "input_blue": "0000FF",
    "formula_black": "000000",
    "cross_sheet_green": "008000",
    "external_red": "FF0000",
    "attention_yellow": "FFFF00",
}

# Custom numfmt IDs (164+ are user-defined in OOXML)
NUM_FORMATS = {
    "currency": ("164", '#,##0.00'),
    "percentage": ("165", "0.0%"),
    "multiple": ("166", '#,##0.00"x"'),
    "integer_comma": ("167", '#,##0'),
}


class StyleEngine:
    """Financial format style system using 13 predefined slots."""

    def __init__(self) -> None:
        self._writer = ExcelWriter()
        self._slots = {s.index: s for s in STYLE_SLOTS}

    def get_style_index(
        self, role: str, numfmt_type: str | None = None
    ) -> int:
        """Find a style slot matching role and optional numfmt type.

        Returns the best-matching slot index, or 0 (default) if no match.
        """
        # Exact match
        for slot in STYLE_SLOTS:
            if slot.role == role:
                if numfmt_type is None or slot.numfmt_type == numfmt_type:
                    return slot.index

        # Fallback: match role with general numfmt
        for slot in STYLE_SLOTS:
            if slot.role == role and slot.numfmt_type == "general":
                return slot.index

        return 0

    def get_financial_style(self, role: str) -> dict[str, Any]:
        """Return style configuration for a given role."""
        color_map = {
            "input": COLORS["input_blue"],
            "formula": COLORS["formula_black"],
            "cross_sheet": COLORS["cross_sheet_green"],
            "header": COLORS["formula_black"],
        }
        return {
            "font_color": color_map.get(role, COLORS["formula_black"]),
            "bold": role == "header",
        }

    def apply_financial_format(
        self,
        file_path: str | Path,
        sheet: str,
        start_col: str,
        start_row: int,
        end_col: str,
        end_row: int,
        role: str = "input",
        numfmt_type: str | None = None,
    ) -> EditResult:
        """Apply a financial format style to a cell range."""
        from .models import CellRange

        style_index = self.get_style_index(role, numfmt_type)
        rng = CellRange(
            sheet=sheet,
            start_col=start_col,
            start_row=start_row,
            end_col=end_col,
            end_row=end_row,
        )
        return self._writer.apply_style(file_path, sheet, rng, style_index)
