"""StructureLLMCaller — lightweight Anthropic SDK wrapper for structure analysis.

Single-shot non-streaming call to analyze Excel file structure.
Separate from the main LLMProvider to avoid pulling in agent dependencies.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any


_SYSTEM_PROMPT = """\
You are an Excel file structure analyst. Your job is to analyze raw spreadsheet data \
and produce a precise structural description.

For each sheet, identify:
1. **Layout type**: one of:
   - `single_table`: one contiguous data table starting from row 1 or a known header row
   - `multi_table`: multiple distinct tables/regions separated by blank rows or section headers
   - `form`: key-value pairs (label in one column, value in adjacent column), not tabular
   - `mixed`: combination of tables, forms, headers, and other elements

2. For each detected **region**:
   - `type`: `table`, `form`, `mixed`, or `blank`
   - `name`: a short descriptive name (e.g. "Sales Data", "Company Info")
   - `startCell` / `endCell`: Excel coordinates (e.g. "A1", "F20"), must be accurate
   - `headerRow`: row number of the header (1-based), null if no clear header
   - `rowCount` / `colCount`
   - For tables: `columns` list with `{name, col_letter, dtype}` for each column
   - For forms: `fields` list with `{label, valueCell}` for each key-value pair
   - `notes`: brief description of what this region contains

3. A `description` field for the sheet summarizing its overall layout.

**Important rules**:
- Row numbers are 1-based (Excel convention). The first row of data you see is row 1.
- Column letters start from A. Column index 0 = A, 1 = B, etc.
- Blank/empty rows are structural separators — they indicate boundaries between regions.
- Merged cells spanning multiple columns in a single row are usually titles or section headers.
- A "form" has 2+ columns where the left columns are short string labels and right columns are values.
- If data starts after some header rows, account for the offset in startCell.

Output strict JSON matching this schema:
{
  "sheets": [
    {
      "name": "Sheet1",
      "layout": "single_table|multi_table|form|mixed",
      "description": "...",
      "regions": [
        {
          "type": "table|form|mixed|blank",
          "name": "...",
          "startCell": "A1",
          "endCell": "F20",
          "headerRow": 1,
          "rowCount": 20,
          "colCount": 6,
          "columns": [{"name": "...", "col_letter": "A", "dtype": "string|number|date|boolean"}],
          "fields": [{"label": "...", "valueCell": "B1"}],
          "notes": "..."
        }
      ]
    }
  ]
}

Output ONLY the JSON object, no markdown fences, no explanation."""


_USER_PROMPT_TEMPLATE = """\
Analyze this Excel file structure.

Sheet: {sheet_name}
Merged cells: {merged_cells}
Schema summary: {schema_summary}

Raw data (first {max_rows} rows, row 1 = Excel row 1):
{raw_data}"""


def _col_letter(idx: int) -> str:
    """Convert 0-based column index to Excel column letter."""
    result = ""
    idx += 1  # 1-based
    while idx > 0:
        idx -= 1
        result = chr(65 + idx % 26) + result
        idx //= 26
    return result


def _infer_dtype(value: Any) -> str:
    """Infer data type from a cell value."""
    if value is None:
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        # Check if it looks like a date
        if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", value):
            return "date"
        return "string"
    return "string"


class StructureLLMCaller:
    """Lightweight LLM caller for structure analysis."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def analyze(
        self,
        raw_sheets: dict[str, list[list[Any]]],
        merged_cells_map: dict[str, list[str]],
        schema_summary: dict[str, dict],
        max_rows: int = 200,
    ) -> dict | None:
        """Run structure analysis via LLM.

        Args:
            raw_sheets: {sheet_name: list of rows (list of cell values)}
            merged_cells_map: {sheet_name: ["A1:C3", ...]}
            schema_summary: {sheet_name: {columns: [{name, dtype}], row_count, col_count}}
            max_rows: max rows to analyze per sheet

        Returns:
            Parsed JSON dict with sheets/regions, or None on failure.
        """
        import anthropic

        # Build user prompt
        sheet_prompts: list[str] = []
        for sheet_name, rows in raw_sheets.items():
            truncated = rows[:max_rows]

            # Format raw data as a readable table
            lines: list[str] = []
            for row_idx, row in enumerate(truncated, start=1):
                cells = []
                for col_idx, val in enumerate(row):
                    if val is None:
                        cells.append("")
                    else:
                        cells.append(str(val))
                line = f"Row {row_idx}: {cells}"
                lines.append(line)
            raw_data = "\n".join(lines) if lines else "(empty sheet)"

            merged = merged_cells_map.get(sheet_name, [])
            merged_str = ", ".join(merged) if merged else "(none)"

            summary = schema_summary.get(sheet_name, {})
            cols = summary.get("columns", [])
            col_str = ", ".join(f"{c.get('name','?')}({c.get('dtype','?')})" for c in cols)
            schema_str = f"columns=[{col_str}], rows={summary.get('row_count','?')}, cols={summary.get('col_count','?')}"

            sheet_prompts.append(
                _USER_PROMPT_TEMPLATE.format(
                    sheet_name=sheet_name,
                    merged_cells=merged_str,
                    schema_summary=schema_str,
                    max_rows=max_rows,
                    raw_data=raw_data,
                )
            )

        user_content = "\n\n---\n\n".join(sheet_prompts)

        try:
            client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )

            # Extract text from response
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            # Parse JSON from response
            return self._parse_json(text)

        except Exception:
            return None

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Parse JSON from LLM response, handling markdown fences."""
        # Try direct parse
        text = text.strip()
        if text.startswith("```"):
            # Strip markdown fences
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            return None
