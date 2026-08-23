"""Column-level lineage: fixture truth, explicit statuses, structural invariant."""

import pytest

from dataform_context_mcp.db import open_db, rebuild, resolve

CANON = {
    "stg_events": "fixture-project.staging.stg_events",
    "int_sessions": "fixture-project.intermediate.int_sessions",
    "ops": "fixture-project.intermediate.ops_merge_snapshot",
    "mart_kpis": "fixture-project.marts.mart_kpis",
    "raw_events": "fixture-project.raw.events",
}


@pytest.fixture(scope="module")
def conn(graph, tmp_path_factory):
    connection = open_db(tmp_path_factory.mktemp("lineage") / "ix.db")
    rebuild(connection, graph, source_hash="hash0")
    return connection


def edges_into(conn, canonical):
    return {
        (row[0], row[1], row[2], row[3]): row[4]
        for row in conn.execute(
            """SELECT up.canonical, ce.upstream_column, down.canonical, ce.downstream_column,
                      ce.expression
               FROM column_edges ce
               JOIN actions up ON up.id = ce.upstream_action
               JOIN actions down ON down.id = ce.downstream_action
               WHERE down.canonical = ?""",
            (canonical,),
        )
    }


def status_of(conn, name):
    return conn.execute(
        "SELECT status, reason FROM extraction_status WHERE action_id = ?",
        (resolve(conn, name),),
    ).fetchone()


def test_stg_events_edges_with_expression(conn):
    edges = edges_into(conn, CANON["stg_events"])
    key = (CANON["raw_events"], "event_name", CANON["stg_events"], "event_name")
    assert key in edges
    assert "LOWER(TRIM" in edges[key]
    assert (CANON["raw_events"], "amount", CANON["stg_events"], "amount") in edges


def test_full_chain_amount(conn):
    assert (
        CANON["int_sessions"],
        "amount",
        CANON["mart_kpis"],
        "total_amount",
    ) in edges_into(conn, CANON["mart_kpis"])
    assert (CANON["stg_events"], "amount", CANON["int_sessions"], "amount") in edges_into(
        conn, CANON["int_sessions"]
    )
    assert (CANON["raw_events"], "amount", CANON["stg_events"], "amount") in edges_into(
        conn, CANON["stg_events"]
    )


def test_snapshot_date_has_no_upstream_yet_status_ok(conn):
    edges = edges_into(conn, CANON["mart_kpis"])
    assert not any(down_col == "snapshot_date" for (_, _, _, down_col) in edges)
    assert status_of(conn, "mart_kpis")["status"] == "ok"


def test_operations_not_attempted(conn):
    row = status_of(conn, "ops_merge_snapshot")
    assert row["status"] == "not_attempted"
    assert row["reason"]
    assert edges_into(conn, CANON["ops"]) == {}


def test_unnest_resolves_to_array_column(conn):
    # Observed with sqlglot 30.17.0: UNNEST(e.items) traces item.qty back to
    # stg_events.items — status stays "ok" (documented fixture choice).
    assert status_of(conn, "int_sessions")["status"] == "ok"
    assert (CANON["stg_events"], "items", CANON["int_sessions"], "item_qty") in edges_into(
        conn, CANON["int_sessions"]
    )


def test_invariant_column_edges_subset_of_table_edges(conn):
    orphans = conn.execute(
        """SELECT COUNT(*) FROM column_edges ce
           WHERE NOT EXISTS (
             SELECT 1 FROM table_edges te
             WHERE te.upstream_id = ce.upstream_action
               AND te.downstream_id = ce.downstream_action)"""
    ).fetchone()[0]
    assert orphans == 0


def test_extraction_status_covers_every_action(conn):
    rows = dict(
        conn.execute(
            """SELECT a.canonical, s.status FROM extraction_status s
               JOIN actions a ON a.id = s.action_id"""
        )
    )
    assert len(rows) == 10
    for declaration in ("fixture-project.raw.events", "fixture-project.legacy.events"):
        assert rows[declaration] == "source"
    # assertion resolves through schema propagation (SELECT * expanded)
    assert rows["fixture-project.fixture_assertions.assert_mart_kpis_positive"] == "ok"


def test_self_reference_skipped_without_penalty():
    """${self()} row-preservation pattern: self-edges are expected lineage noise,
    not an inconsistency — status stays ok, no self edge emitted."""
    from dataform_context_mcp.lineage import extract_column_lineage
    from dataform_context_mcp.model import Action, Target

    action = Action(
        target=Target("p", "d", "t"),
        action_type="table",
        dependency_targets=[Target("p", "d", "src")],
        query=(
            "SELECT a, b FROM `p.d.src`\n"
            "UNION ALL\n"
            "SELECT a, b FROM `p.d.t` WHERE a NOT IN (SELECT a FROM `p.d.src`)"
        ),
    )
    result = extract_column_lineage(action, {})
    assert result.status == "ok"
    assert all(edge.up_table != "p.d.t" for edge in result.edges)
    assert ("p.d.src", "a", "p.d.t", "a") in {
        (e.up_table, e.up_column, e.down_table, e.down_column) for e in result.edges
    }
