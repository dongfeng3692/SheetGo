"""Tests for structure_analyzer and structure_llm modules."""

import json
import pytest

from python.preload.structure_analyzer import (
    Region,
    SheetStructure,
    StructureResult,
    StructureAnalyzer,
)
from python.preload.structure_llm import StructureLLMCaller


# ---------------------------------------------------------------------------
# Region serialization
# ---------------------------------------------------------------------------


class TestRegionSerialization:
    def test_to_dict_table(self):
        r = Region(
            type="table",
            name="Sales",
            start_cell="A1",
            end_cell="D10",
            header_row=1,
            row_count=10,
            col_count=4,
            columns=[
                {"name": "Month", "col_letter": "A", "dtype": "string"},
                {"name": "Revenue", "col_letter": "B", "dtype": "number"},
            ],
        )
        d = r.to_dict()
        assert d["type"] == "table"
        assert d["startCell"] == "A1"
        assert d["endCell"] == "D10"
        assert d["headerRow"] == 1
        assert len(d["columns"]) == 2

    def test_to_dict_form(self):
        r = Region(
            type="form",
            name="Info",
            start_cell="A1",
            end_cell="B5",
            header_row=None,
            row_count=5,
            col_count=2,
            fields=[
                {"label": "Name", "valueCell": "B1"},
                {"label": "Date", "valueCell": "B2"},
            ],
        )
        d = r.to_dict()
        assert d["type"] == "form"
        assert "headerRow" not in d
        assert len(d["fields"]) == 2

    def test_roundtrip(self):
        r = Region(
            type="table",
            name="Test",
            start_cell="A1",
            end_cell="C5",
            header_row=1,
            row_count=5,
            col_count=3,
            columns=[{"name": "A", "col_letter": "A", "dtype": "string"}],
        )
        d = r.to_dict()
        r2 = Region.from_dict(d)
        assert r2.type == r.type
        assert r2.name == r.name
        assert r2.start_cell == r.start_cell
        assert r2.end_cell == r.end_cell
        assert r2.header_row == r.header_row


# ---------------------------------------------------------------------------
# SheetStructure serialization
# ---------------------------------------------------------------------------


class TestSheetStructureSerialization:
    def test_to_dict(self):
        ss = SheetStructure(
            name="Sheet1",
            layout="multi_table",
            description="Contains 2 tables",
            regions=[
                Region(type="table", name="T1", start_cell="A1", end_cell="C5",
                       header_row=1, row_count=5, col_count=3),
            ],
        )
        d = ss.to_dict()
        assert d["name"] == "Sheet1"
        assert d["layout"] == "multi_table"
        assert len(d["regions"]) == 1

    def test_roundtrip(self):
        ss = SheetStructure(
            name="Sheet1",
            layout="single_table",
            description="Test",
            regions=[
                Region(type="table", name="T1", start_cell="A1", end_cell="B2",
                       header_row=1, row_count=2, col_count=2),
            ],
        )
        d = ss.to_dict()
        ss2 = SheetStructure.from_dict(d)
        assert ss2.name == ss.name
        assert ss2.layout == ss.layout
        assert len(ss2.regions) == 1


# ---------------------------------------------------------------------------
# StructureResult serialization
# ---------------------------------------------------------------------------


class TestStructureResultSerialization:
    def test_ok_result(self):
        sr = StructureResult(
            file_id="test123",
            status="ok",
            sheets=[
                SheetStructure(
                    name="Sheet1",
                    layout="single_table",
                    description="One table",
                    regions=[],
                ),
            ],
            analysis_source="llm",
            timestamp="2026-04-16T00:00:00Z",
        )
        d = sr.to_dict()
        assert d["fileId"] == "test123"
        assert d["status"] == "ok"
        assert d["analysisSource"] == "llm"
        assert len(d["sheets"]) == 1

    def test_skipped_result(self):
        sr = StructureResult(
            file_id="test456",
            status="skipped",
            timestamp="2026-04-16T00:00:00Z",
        )
        d = sr.to_dict()
        assert d["status"] == "skipped"
        assert d["sheets"] == []

    def test_roundtrip(self):
        sr = StructureResult(
            file_id="abc",
            status="ok",
            sheets=[
                SheetStructure(
                    name="S1",
                    layout="multi_table",
                    description="test",
                    regions=[
                        Region(type="table", name="T1", start_cell="A1",
                               end_cell="D10", header_row=1, row_count=10, col_count=4),
                        Region(type="form", name="F1", start_cell="F1",
                               end_cell="G5", header_row=None, row_count=5, col_count=2),
                    ],
                ),
            ],
            analysis_source="llm",
            timestamp="2026-04-16T00:00:00Z",
        )
        d = sr.to_dict()
        sr2 = StructureResult.from_dict(d)
        assert sr2.file_id == sr.file_id
        assert sr2.status == sr.status
        assert len(sr2.sheets) == 1
        assert len(sr2.sheets[0].regions) == 2
        assert sr2.sheets[0].regions[0].type == "table"
        assert sr2.sheets[0].regions[1].type == "form"

    def test_json_serializable(self):
        sr = StructureResult(
            file_id="test",
            status="ok",
            sheets=[
                SheetStructure(
                    name="S1",
                    layout="single_table",
                    description="test",
                    regions=[
                        Region(type="table", name="T1", start_cell="A1",
                               end_cell="C3", header_row=1, row_count=3, col_count=3),
                    ],
                ),
            ],
            analysis_source="llm",
            timestamp="2026-04-16T00:00:00Z",
        )
        # Should not raise
        json_str = json.dumps(sr.to_dict(), ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["fileId"] == "test"


# ---------------------------------------------------------------------------
# StructureLLMCaller JSON parsing
# ---------------------------------------------------------------------------


class TestStructureLLMCallerParsing:
    def test_parse_plain_json(self):
        text = '{"sheets": [{"name": "Sheet1", "layout": "single_table"}]}'
        result = StructureLLMCaller._parse_json(text)
        assert result is not None
        assert result["sheets"][0]["name"] == "Sheet1"

    def test_parse_json_with_markdown_fences(self):
        text = '```json\n{"sheets": []}\n```'
        result = StructureLLMCaller._parse_json(text)
        assert result is not None
        assert result["sheets"] == []

    def test_parse_json_with_surrounding_text(self):
        text = 'Here is the analysis:\n{"sheets": []}\nDone.'
        result = StructureLLMCaller._parse_json(text)
        assert result is not None
        assert result["sheets"] == []

    def test_parse_invalid_json_returns_none(self):
        text = "This is not JSON at all"
        result = StructureLLMCaller._parse_json(text)
        assert result is None

    def test_parse_empty_string_returns_none(self):
        result = StructureLLMCaller._parse_json("")
        assert result is None


# ---------------------------------------------------------------------------
# StructureAnalyzer — skipped results
# ---------------------------------------------------------------------------


class TestStructureAnalyzerSkipped:
    def test_no_api_key_returns_skipped(self):
        result = StructureAnalyzer.analyze(
            file_id="test",
            file_path="/nonexistent/file.xlsx",
            api_key="",
        )
        assert result.status == "skipped"
        assert result.sheets == []

    def test_nonexistent_file_returns_skipped(self):
        result = StructureAnalyzer.analyze(
            file_id="test",
            file_path="/nonexistent/file.xlsx",
            api_key="sk-ant-fake-key",
        )
        assert result.status == "skipped"


# ---------------------------------------------------------------------------
# Prompt builder — structure section formatting
# ---------------------------------------------------------------------------


class TestStructureFormatting:
    def test_format_empty_structures(self):
        from python.agent.prompt_builder import _format_structure_section
        assert _format_structure_section({}) == ""
        assert _format_structure_section(None) == ""

    def test_format_structure_with_regions(self):
        from python.agent.prompt_builder import _format_structure_section

        structures = {
            "file1": {
                "status": "ok",
                "sheets": [
                    {
                        "name": "Sheet1",
                        "layout": "multi_table",
                        "description": "Contains 2 tables",
                        "regions": [
                            {
                                "type": "table",
                                "name": "Revenue",
                                "startCell": "A1",
                                "endCell": "D25",
                                "rowCount": 25,
                                "colCount": 4,
                                "columns": [
                                    {"name": "Month", "dtype": "string"},
                                    {"name": "Revenue", "dtype": "number"},
                                ],
                            },
                            {
                                "type": "form",
                                "name": "Metadata",
                                "startCell": "F1",
                                "endCell": "G8",
                                "rowCount": 8,
                                "colCount": 2,
                                "fields": [
                                    {"label": "Title", "valueCell": "G1"},
                                ],
                            },
                        ],
                    },
                ],
            },
        }
        result = _format_structure_section(structures)
        assert "Revenue" in result
        assert "A1:D25" in result
        assert "Month(string)" in result
        assert "Metadata" in result
        assert "Title→G1" in result

    def test_format_skipped_structure(self):
        from python.agent.prompt_builder import _format_structure_section

        structures = {
            "file1": {"status": "skipped"},
        }
        result = _format_structure_section(structures)
        # Should be just the header, no analysis content
        assert result == "" or "structure_analysis" not in result
