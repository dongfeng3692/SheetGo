"""DuckDB SQL query engine with sqlglot validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

from .models import ColumnDesc, SQLError


class DuckDBQuery:
    """SQL query engine: validate with sqlglot, execute with DuckDB."""

    @staticmethod
    def validate_sql(sql: str) -> tuple[bool, str]:
        """Validate that SQL is a safe SELECT statement.

        Returns (is_valid, error_message).
        Only pure SELECT statements are allowed.
        """
        if not sql.strip():
            return False, "Empty SQL statement"

        try:
            parsed = sqlglot.parse(sql, dialect="duckdb")
        except sqlglot.errors.ParseError as e:
            return False, f"SQL parse error: {e}"

        if not parsed:
            return False, "Could not parse SQL statement"

        # Must be a single statement
        if len(parsed) > 1:
            return False, "Only single SQL statements are allowed"

        statement = parsed[0]

        # Must be a SELECT
        if not isinstance(statement, exp.Select):
            return False, f"Only SELECT statements are allowed, got {type(statement).__name__}"

        # Block subqueries that contain non-SELECT statements
        for node in statement.walk():
            if isinstance(node, (exp.Insert, exp.Update, exp.Delete,
                                exp.Drop, exp.Alter, exp.Create,
                                exp.TruncateTable)):
                return False, f"DDL/DML not allowed: {type(node).__name__}"

        return True, ""

    @staticmethod
    def execute(db_path: str | Path, sql: str) -> pd.DataFrame:
        """Validate and execute SQL, returning a DataFrame.

        Raises SQLError if validation fails.
        """
        is_valid, error = DuckDBQuery.validate_sql(sql)
        if not is_valid:
            raise SQLError(error)

        try:
            con = duckdb.connect(str(db_path), read_only=True)
            result = con.execute(sql).fetchdf()
            con.close()
            return result
        except duckdb.Error as e:
            raise SQLError(f"DuckDB execution error: {e}") from e

    @staticmethod
    def list_tables(db_path: str | Path) -> list[str]:
        """List all tables in the DuckDB database."""
        con = duckdb.connect(str(db_path), read_only=True)
        result = con.execute("SHOW TABLES").fetchall()
        con.close()
        return [row[0] for row in result]

    @staticmethod
    def describe_table(
        db_path: str | Path, table: str
    ) -> list[ColumnDesc]:
        """Describe columns of a table."""
        con = duckdb.connect(str(db_path), read_only=True)
        rows = con.execute(f"DESCRIBE \"{table}\"").fetchall()
        con.close()
        return [
            ColumnDesc(name=row[0], dtype=row[1], nullable=row[2] == "YES")
            for row in rows
        ]

    @staticmethod
    def register_dataframes(
        db_path: str | Path, tables: dict[str, pd.DataFrame]
    ) -> None:
        """Register DataFrames as persistent tables in DuckDB."""
        con = duckdb.connect(str(db_path))
        for name, df in tables.items():
            con.execute(
                f"CREATE OR REPLACE TABLE \"{name}\" AS SELECT * FROM df"
            )
        con.close()
