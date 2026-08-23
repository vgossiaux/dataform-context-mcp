"""SQLite graph store: rebuild integrity, name resolution, traversals."""

import pytest

from dataform_context_mcp import db as dbmod
from dataform_context_mcp.db import (
    AmbiguousError,
    NotFoundError,
    available_layers,
    downstream_closure,
    get_action,
    open_db,
    rebuild,
    resolve,
    tables_by_layer,
    traverse,
)

CANON = {
    "stg_events": "fixture-project.staging.stg_events",
    "stg_customers": "fixture-project.staging.stg_customers",
    "int_sessions": "fixture-project.intermediate.int_sessions",
    "ops_merge_snapshot": "fixture-project.intermediate.ops_merge_snapshot",
    "mart_kpis": "fixture-project.marts.mart_kpis",
    "mart_ops": "fixture-project.marts.mart_ops",
    "assert": "fixture-project.fixture_assertions.assert_mart_kpis_positive",
    "raw_events": "fixture-project.raw.events",
    "raw_customers": "fixture-project.raw.customers",
    "legacy_events": "fixture-project.legacy.events",
}


@pytest.fixture(scope="module")
def conn(graph, tmp_path_factory):
    connection = open_db(tmp_path_factory.mktemp("db") / "ix.db")
    rebuild(connection, graph, source_hash="hash0")
    return connection


def canonicals(levels):
    return {node["canonical"] for level in levels for node in level["nodes"]}


def test_rebuild_counts(conn):
    assert conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM table_edges").fetchone()[0] == 8


def test_rebuild_integrity_edges_match_dependency_targets(conn, graph):
    stored = {
        (row[0], row[1])
        for row in conn.execute(
            """SELECT up.canonical, down.canonical
               FROM table_edges e
               JOIN actions up ON up.id = e.upstream_id
               JOIN actions down ON down.id = e.downstream_id"""
        )
    }
    expected = {
        (dep.canonical(), action.target.canonical())
        for action in graph.actions
        for dep in action.dependency_targets
    }
    assert stored == expected


def test_rebuild_idempotent(conn, graph):
    rebuild(conn, graph, source_hash="hash1")
    assert conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM table_edges").fetchone()[0] == 8


def test_layers_stored(conn):
    rows = dict(conn.execute("SELECT canonical, layer FROM actions"))
    assert rows[CANON["stg_events"]] == "01_staging"
    assert rows[CANON["raw_events"]] == "sources"


def test_columns_stored(conn):
    action = get_action(conn, resolve(conn, "mart_kpis"))
    docs = {c["name"]: c["description"] for c in action["columns"]}
    assert docs["total_amount"] == "Total session amount per customer"
    assert len(docs) == 5
    assert action["unique_key"] == []
    assert action["tags"] == ["marts", "kpi"]


def test_resolve_bare_name(conn):
    assert get_action(conn, resolve(conn, "mart_kpis"))["canonical"] == CANON["mart_kpis"]


def test_resolve_qualified_forms(conn):
    full = resolve(conn, "fixture-project.staging.stg_events")
    assert resolve(conn, "staging.stg_events") == full


def test_resolve_ambiguous(conn):
    with pytest.raises(AmbiguousError) as excinfo:
        resolve(conn, "events")
    assert set(excinfo.value.candidates) == {CANON["raw_events"], CANON["legacy_events"]}
    assert resolve(conn, "raw.events") is not None


def test_resolve_not_found_with_suggestions(conn):
    with pytest.raises(NotFoundError) as excinfo:
        resolve(conn, "mart_kpi")
    assert CANON["mart_kpis"] in excinfo.value.suggestions


def test_resolve_by_file_name(conn):
    action_id = resolve(conn, "definitions/transforms/04_marts/mart_kpis.sqlx")
    assert get_action(conn, action_id)["canonical"] == CANON["mart_kpis"]


def test_upstream_by_depth(conn):
    root = resolve(conn, "mart_kpis")
    depth1 = traverse(conn, root, "up", 1)
    assert canonicals(depth1) == {CANON["int_sessions"], CANON["stg_customers"]}
    depth2 = traverse(conn, root, "up", 2)
    assert canonicals(depth2) == canonicals(depth1) | {
        CANON["stg_events"],
        CANON["raw_customers"],
    }
    depth3 = traverse(conn, root, "up", 3)
    assert canonicals(depth3) == canonicals(depth2) | {CANON["raw_events"]}


def test_downstream_full(conn):
    levels = traverse(conn, resolve(conn, "stg_events"), "down", 10)
    assert canonicals(levels) == {
        CANON["int_sessions"],
        CANON["ops_merge_snapshot"],
        CANON["mart_kpis"],
        CANON["mart_ops"],
        CANON["assert"],
    }
    by_depth = {level["depth"]: {n["canonical"] for n in level["nodes"]} for level in levels}
    assert by_depth[1] == {CANON["int_sessions"], CANON["ops_merge_snapshot"]}
    assert by_depth[2] == {CANON["mart_kpis"], CANON["mart_ops"]}
    assert by_depth[3] == {CANON["assert"]}


def test_isolated_node_has_empty_downstream(conn):
    assert traverse(conn, resolve(conn, "legacy.events"), "down", 10) == []


def test_tables_by_layer(conn):
    exact = {t["canonical"] for t in tables_by_layer(conn, "04_marts")}
    assert exact == {CANON["mart_kpis"], CANON["mart_ops"]}
    assert {t["canonical"] for t in tables_by_layer(conn, "marts")} == exact
    with pytest.raises(NotFoundError) as excinfo:
        tables_by_layer(conn, "nope")
    assert "01_staging" in excinfo.value.suggestions
    assert set(available_layers(conn)) == {
        "01_staging",
        "02_intermediate",
        "04_marts",
        "assertions",
        "sources",
    }


def test_downstream_closure(conn):
    nodes = {n["canonical"] for n in downstream_closure(conn, resolve(conn, "stg_events"))}
    assert nodes == {
        CANON["int_sessions"],
        CANON["ops_merge_snapshot"],
        CANON["mart_kpis"],
        CANON["mart_ops"],
        CANON["assert"],
    }


def test_meta_recorded(conn):
    meta = dbmod.get_meta(conn)
    assert meta["source_hash"] == "hash1"  # last rebuild in test_rebuild_idempotent
    assert meta["counts"]["actions"] == 10
    assert meta["counts"]["table_edges"] == 8
