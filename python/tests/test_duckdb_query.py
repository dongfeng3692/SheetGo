"""Tests for DuckDBQuery: SQL validation and execution."""

import pytest
from python.excel.duckdb_query import DuckDBQuery
from python.excel.models import SQLError


class TestValidateSQL:
    def test_valid_select(self):
        ok, msg = DuckDBQuery.validate_sql("SELECT * FROM sheet1")
        assert ok

    def test_valid_select_where(self):
        ok, msg = DuckDBQuery.validate_sql(
            "SELECT name, amount FROM sheet1 WHERE region = 'East'"
        )
        assert ok

    def test_reject_drop(self):
        ok, msg = DuckDBQuery.validate_sql("DROP TABLE sheet1")
        assert not ok
        assert "SELECT" in msg

    def test_reject_update(self):
        ok, msg = DuckDBQuery.validate_sql("UPDATE sheet1 SET amount = 0")
        assert not ok

    def test_reject_insert(self):
        ok, msg = DuckDBQuery.validate_sql("INSERT INTO sheet1 VALUES (1,2,3)")
        assert not ok

    def test_reject_empty(self):
        ok, msg = DuckDBQuery.validate_sql("")
        assert not ok

    def test_reject_multiple(self):
        ok, msg = DuckDBQuery.validate_sql(
            "SELECT 1; DROP TABLE sheet1"
        )
        assert not ok


class TestExecute:
    def test_basic_query(self, duckdb_with_data):
        df = DuckDBQuery.execute(duckdb_with_data, "SELECT * FROM sheet1")
        assert len(df) == 4
        assert "name" in df.columns

    def test_filtered_query(self, duckdb_with_data):
        df = DuckDBQuery.execute(
            duckdb_with_data,
            "SELECT * FROM sheet1 WHERE region = 'East'"
        )
        assert len(df) == 2

    def test_reject_non_select(self, duckdb_with_data):
        with pytest.raises(SQLError):
            DuckDBQuery.execute(duckdb_with_data, "DELETE FROM sheet1")


class TestListTables:
    def test_basic(self, duckdb_with_data):
        tables = DuckDBQuery.list_tables(duckdb_with_data)
        assert "sheet1" in tables


class TestDescribeTable:
    def test_basic(self, duckdb_with_data):
        cols = DuckDBQuery.describe_table(duckdb_with_data, "sheet1")
        assert len(cols) == 3
        assert cols[0].name == "name"
