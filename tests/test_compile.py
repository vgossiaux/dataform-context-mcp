"""Loader tests against the captured compiled graph of the fixture mini_repo."""

from collections import Counter
from pathlib import Path

import pytest

from tests.conftest import MINI_REPO, requires_dataform


def by_name(graph, name):
    matches = [a for a in graph.actions if a.target.name == name]
    assert len(matches) == 1, f"expected exactly one action named {name}, got {len(matches)}"
    return matches[0]


def test_action_counts(graph):
    assert len(graph.actions) == 10
    counts = Counter(a.action_type for a in graph.actions)
    assert counts == {
        "declaration": 3,
        "view": 2,  # stg_events, mart_ops
        "table": 2,  # stg_customers, mart_kpis
        "incremental": 1,  # int_sessions
        "operations": 1,  # ops_merge_snapshot
        "assertion": 1,  # assert_mart_kpis_positive
    }


def test_mart_kpis_dependency_targets(graph):
    mart = by_name(graph, "mart_kpis")
    deps = {t.canonical() for t in mart.dependency_targets}
    assert deps == {
        "fixture-project.intermediate.int_sessions",
        "fixture-project.staging.stg_customers",
    }


def test_incremental_fields(graph):
    ints = by_name(graph, "int_sessions")
    assert ints.action_type == "incremental"
    assert ints.incremental_query
    assert ints.unique_key == ["session_id"]


def test_column_docs(graph):
    mart = by_name(graph, "mart_kpis")
    docs = {c.name: c.description for c in mart.columns}
    assert docs["total_amount"] == "Total session amount per customer"
    assert len(docs) == 5
    assert by_name(graph, "stg_customers").columns == []


def test_target_canonical(graph):
    stg = by_name(graph, "stg_events")
    assert stg.target.canonical() == "fixture-project.staging.stg_events"


def test_operations_have_query_and_not_disabled(graph):
    ops = by_name(graph, "ops_merge_snapshot")
    assert ops.query and "MERGE" in ops.query
    assert ops.disabled is False


def test_compile_error_on_missing_repo():
    from dataform_context_mcp.compile import CompileError, run_dataform_compile

    with pytest.raises(CompileError) as excinfo:
        run_dataform_compile(Path("/nonexistent-dataform-repo"))
    assert excinfo.value.stderr


@requires_dataform
@pytest.mark.integration
def test_live_compile_matches_capture(graph):
    from dataform_context_mcp.compile import load_graph, run_dataform_compile

    live = load_graph(run_dataform_compile(MINI_REPO))
    assert Counter(a.action_type for a in live.actions) == Counter(
        a.action_type for a in graph.actions
    )
    assert {a.target.canonical() for a in live.actions} == {
        a.target.canonical() for a in graph.actions
    }
