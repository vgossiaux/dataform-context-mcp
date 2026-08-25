"""MCP server tests — in-process client against the fixture graph."""

import copy
import json
import shutil

import pytest
from mcp import Client

from dataform_context_mcp.server import create_server
from tests.conftest import MINI_REPO, requires_dataform

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "get_table_context",
    "get_upstream",
    "get_downstream",
    "find_tables_by_layer",
    "get_column_lineage",
    "impact_analysis",
    "check_setup",
    "refresh_index",
}

CANON = {
    "stg_events": "fixture-project.staging.stg_events",
    "stg_customers": "fixture-project.staging.stg_customers",
    "int_sessions": "fixture-project.intermediate.int_sessions",
    "ops": "fixture-project.intermediate.ops_merge_snapshot",
    "mart_kpis": "fixture-project.marts.mart_kpis",
    "mart_ops": "fixture-project.marts.mart_ops",
    "assert": "fixture-project.fixture_assertions.assert_mart_kpis_positive",
    "raw_events": "fixture-project.raw.events",
    "raw_customers": "fixture-project.raw.customers",
}


@pytest.fixture()
def repo_copy(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(
        MINI_REPO, dest, ignore=shutil.ignore_patterns("node_modules", ".dataform", ".gitignore")
    )
    return dest


@pytest.fixture()
def compile_calls():
    return []


@pytest.fixture()
def server(repo_copy, tmp_path, raw_graph, compile_calls):
    def compile_fn(repo):
        compile_calls.append(repo)
        return raw_graph

    return create_server(repo_copy, tmp_path / "ix.db", _compile_fn=compile_fn)


async def call(client, tool, **args):
    result = await client.call_tool(tool, args)
    assert result.structured_content is not None, f"{tool} returned no structured content"
    return result.structured_content


async def test_list_tools(server):
    async with Client(server) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == EXPECTED_TOOLS


async def test_get_table_context(server):
    async with Client(server) as client:
        ctx = await call(client, "get_table_context", name="mart_kpis")
        assert ctx["canonical"] == CANON["mart_kpis"]
        assert ctx["type"] == "table"
        assert ctx["layer"] == "04_marts"
        assert ctx["file"] == "definitions/transforms/04_marts/mart_kpis.sqlx"
        assert ctx["description"] == "Customer KPI mart"
        assert ctx["incremental"] is False
        assert {c["name"] for c in ctx["columns"]} >= {"total_amount", "snapshot_date"}
        assert set(ctx["upstream"]) == {CANON["int_sessions"], CANON["stg_customers"]}
        assert ctx["downstream"] == [CANON["assert"]]
        assert ctx["index_meta"]["compile_status"] == "ok"


async def test_get_upstream_depth_and_truncation(server):
    async with Client(server) as client:
        result = await call(client, "get_upstream", name="mart_kpis", depth=2)
        assert result["root"] == CANON["mart_kpis"]
        assert [level["depth"] for level in result["levels"]] == [1, 2]
        assert result["truncated"] is True  # raw.events sits at depth 3
        deeper = await call(client, "get_upstream", name="mart_kpis", depth=3)
        assert deeper["truncated"] is False


async def test_find_tables_by_layer(server):
    async with Client(server) as client:
        exact = await call(client, "find_tables_by_layer", layer="04_marts")
        suffix = await call(client, "find_tables_by_layer", layer="marts")
        names = {t["canonical"] for t in exact["tables"]}
        assert names == {CANON["mart_kpis"], CANON["mart_ops"]}
        assert {t["canonical"] for t in suffix["tables"]} == names
        bad = await call(client, "find_tables_by_layer", layer="nope")
        assert bad["error"]["code"] == "invalid_layer"
        assert "01_staging" in bad["error"]["suggestions"]


async def test_impact_analysis_table_level(server):
    async with Client(server) as client:
        impact = await call(client, "impact_analysis", name="stg_events")
        assert impact["target"] == CANON["stg_events"]
        assert set(impact["direct_downstream"]) == {CANON["int_sessions"], CANON["ops"]}
        assert set(impact["transitive_by_layer"]["04_marts"]) == {
            CANON["mart_kpis"],
            CANON["mart_ops"],
        }
        assert impact["affected_assertions"] == [CANON["assert"]]
        assert impact["counts"]["total_downstream"] == 5


async def test_resolution_errors(server):
    async with Client(server) as client:
        ambiguous = await call(client, "get_table_context", name="events")
        assert ambiguous["error"]["code"] == "ambiguous"
        assert len(ambiguous["error"]["suggestions"]) == 2
        missing = await call(client, "get_table_context", name="mart_kpi")
        assert missing["error"]["code"] == "not_found"
        assert CANON["mart_kpis"] in missing["error"]["suggestions"]


async def test_freshness_reflects_source_changes(repo_copy, tmp_path, raw_graph):
    modified = copy.deepcopy(raw_graph)
    mart_ops = next(t for t in modified["tables"] if t["target"]["name"] == "mart_ops")
    mart_ops["dependencyTargets"].append(
        {"database": "fixture-project", "schema": "staging", "name": "stg_customers"}
    )
    graphs = [raw_graph, modified]

    def compile_fn(repo):
        return graphs.pop(0)

    server = create_server(repo_copy, tmp_path / "ix.db", _compile_fn=compile_fn)
    async with Client(server) as client:
        first = await call(client, "get_table_context", name="mart_ops")
        assert first["upstream"] == [CANON["ops"]]
        target = repo_copy / "definitions/transforms/04_marts/mart_ops.sqlx"
        target.write_text(target.read_text() + "\n-- edited\n")
        second = await call(client, "get_table_context", name="mart_ops")
        assert set(second["upstream"]) == {CANON["ops"], CANON["stg_customers"]}
        assert second["index_meta"]["source_hash"] != first["index_meta"]["source_hash"]


async def test_refresh_index_forces_recompile(server, compile_calls):
    async with Client(server) as client:
        await call(client, "get_table_context", name="mart_kpis")
        calls_before = len(compile_calls)
        meta = await call(client, "refresh_index")
        assert len(compile_calls) == calls_before + 1  # recompiled without a file change
        assert meta["compile_status"] == "ok"
        assert meta["counts"]["actions"] == 10
        assert "01_staging" in meta["available_layers"]


async def test_column_lineage_full_chain(server):
    async with Client(server) as client:
        result = await call(client, "get_column_lineage", table="mart_kpis", column="total_amount")
        assert result["complete"] is True
        assert result["warnings"] == []
        chain = {
            (e["from"]["table"], e["from"]["column"], e["to"]["table"], e["to"]["column"])
            for e in result["edges"]
        }
        assert chain == {
            (CANON["int_sessions"], "amount", CANON["mart_kpis"], "total_amount"),
            (CANON["stg_events"], "amount", CANON["int_sessions"], "amount"),
            (CANON["raw_events"], "amount", CANON["stg_events"], "amount"),
        }


async def test_column_lineage_true_absence(server):
    async with Client(server) as client:
        result = await call(client, "get_column_lineage", table="mart_kpis", column="snapshot_date")
        assert result["edges"] == []
        assert result["complete"] is True  # real absence, not an extraction gap


async def test_column_lineage_surfaces_opaque_upstream(server):
    async with Client(server) as client:
        result = await call(client, "get_column_lineage", table="mart_ops", column="amount")
        assert result["complete"] is False
        assert any(
            w["canonical"] == CANON["ops"] and w["status"] == "not_attempted"
            for w in result["warnings"]
        )


async def test_column_lineage_downstream(server):
    async with Client(server) as client:
        result = await call(
            client,
            "get_column_lineage",
            table="stg_events",
            column="session_id",
            direction="downstream",
        )
        targets = {(e["to"]["table"], e["to"]["column"]) for e in result["edges"]}
        assert (CANON["int_sessions"], "session_id") in targets
        assert (CANON["mart_kpis"], "session_count") in targets


async def test_column_lineage_unknown_column(server):
    async with Client(server) as client:
        result = await call(client, "get_column_lineage", table="mart_kpis", column="amout")
        assert result["error"]["code"] == "not_found"
        assert "total_amount" in result["error"]["suggestions"]


async def test_impact_analysis_column_level(server):
    async with Client(server) as client:
        impact = await call(client, "impact_analysis", name="stg_events", column="amount")
        assert {"table": CANON["mart_kpis"], "column": "total_amount"} in impact["affected_columns"]
        assert CANON["ops"] in impact["possibly_affected"]
        assert CANON["mart_ops"] in impact["possibly_affected"]  # downstream of opaque node
        assert CANON["mart_kpis"] not in impact["possibly_affected"]


async def test_check_setup_without_goldens(server):
    async with Client(server) as client:
        result = await call(client, "check_setup")
        assert [c["name"] for c in result["checks"]] == [
            "dataform_cli",
            "compile",
            "index",
            "column_lineage",
            "goldens",
        ]
        by_name = {c["name"]: c for c in result["checks"]}
        assert by_name["compile"]["ok"] is True
        assert by_name["index"]["ok"] is True
        assert "actions=10" in by_name["index"]["detail"]
        assert by_name["column_lineage"]["ok"] is True
        assert by_name["goldens"]["ok"] is True
        assert "optional" in by_name["goldens"]["detail"]


async def test_check_setup_flags_misplaced_golden(server, repo_copy):
    """A golden file at the repo root is found but not where the tools look —
    check_setup must say so instead of reporting 'no golden file'."""
    (repo_copy / "golden_columns.json").write_text(
        json.dumps(
            [
                {
                    "table": "marts.mart_kpis",
                    "column": "snapshot_date",
                    "expected_edges": [],
                    "expect_complete": True,
                }
            ]
        )
    )
    async with Client(server) as client:
        result = await call(client, "check_setup")
        goldens = next(c for c in result["checks"] if c["name"] == "goldens")
        assert goldens["ok"] is False
        assert "golden_columns.json" in goldens["detail"]
        assert ".dataform-context/golden_columns.json" in goldens["detail"]
        assert "optional" not in goldens["detail"]


async def test_check_setup_runs_goldens(server, repo_copy):
    golden_dir = repo_copy / ".dataform-context"
    golden_dir.mkdir()
    (golden_dir / "golden_columns.json").write_text(
        json.dumps(
            [
                {
                    "table": "marts.mart_kpis",
                    "column": "snapshot_date",
                    "expected_edges": [],
                    "expect_complete": True,
                },
                {
                    "table": "marts.mart_kpis",
                    "column": "total_amount",
                    "depth": 1,
                    "expected_edges": [
                        "staging.stg_customers.oops -> marts.mart_kpis.total_amount"
                    ],
                },
            ]
        )
    )
    async with Client(server) as client:
        result = await call(client, "check_setup")
        goldens = next(c for c in result["checks"] if c["name"] == "goldens")
        assert goldens["ok"] is False
        assert "1/2 passed" in goldens["detail"]
        assert result["ok"] is False


@requires_dataform
@pytest.mark.integration
async def test_live_stdio_server(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="uv",
        args=[
            "run",
            "dataform-context",
            "serve",
            "--repo",
            str(MINI_REPO),
            "--db",
            str(tmp_path / "ix.db"),
        ],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == EXPECTED_TOOLS
            result = await session.call_tool("get_table_context", {"name": "mart_kpis"})
            assert result.structured_content["canonical"] == CANON["mart_kpis"]
