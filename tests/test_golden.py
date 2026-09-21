"""Golden validation: malformed entries are reported, never raised."""

import pytest

from dataform_context_mcp.db import open_db, rebuild
from dataform_context_mcp.golden import validate_entries


@pytest.fixture(scope="module")
def conn(graph, tmp_path_factory):
    connection = open_db(tmp_path_factory.mktemp("db") / "ix.db")
    rebuild(connection, graph, source_hash="hash0")
    return connection


def test_entry_missing_column_is_reported_not_raised(conn):
    summary = validate_entries(conn, [{"table": "marts.mart_kpis"}])
    assert summary["total"] == 1
    assert summary["passed"] == 0
    result = summary["results"][0]
    assert result["ok"] is False
    assert result["problems"][0].startswith("golden entry invalid")
    assert "column" in result["problems"][0]


def test_entry_missing_table_is_reported_not_raised(conn):
    summary = validate_entries(conn, [{"column": "snapshot_date"}])
    result = summary["results"][0]
    assert result["ok"] is False
    assert "table" in result["problems"][0]


def test_entry_not_a_dict_is_reported_not_raised(conn):
    summary = validate_entries(conn, ["marts.mart_kpis.snapshot_date"])
    result = summary["results"][0]
    assert result["ok"] is False
    assert result["problems"][0].startswith("golden entry invalid")


def test_valid_entry_still_passes(conn):
    summary = validate_entries(
        conn,
        [
            {
                "table": "marts.mart_kpis",
                "column": "snapshot_date",
                "expected_edges": [],
                "expect_complete": True,
            }
        ],
    )
    assert summary["passed"] == summary["total"] == 1
