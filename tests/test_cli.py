"""CLI tests: index and report against the fixture graph."""

import json

import pytest

from dataform_context_mcp.cli import main
from tests.conftest import FIXTURES, MINI_REPO, requires_dataform

GRAPH_JSON = str(FIXTURES / "compiled_graph.json")


@pytest.fixture()
def indexed_db(tmp_path):
    db = tmp_path / "ix.db"
    assert main(["index", "--from-json", GRAPH_JSON, "--db", str(db)]) == 0
    return db


def test_index_from_json(tmp_path, capsys):
    db = tmp_path / "ix.db"
    code = main(["index", "--from-json", GRAPH_JSON, "--db", str(db)])
    out = capsys.readouterr().out
    assert code == 0
    assert db.exists()
    assert "actions: 10" in out
    assert "table_edges: 8" in out


@requires_dataform
@pytest.mark.integration
def test_index_compiles_repo(tmp_path, capsys):
    db = tmp_path / "ix.db"
    code = main(["index", "--repo", str(MINI_REPO), "--db", str(db)])
    out = capsys.readouterr().out
    assert code == 0
    assert "actions: 10" in out
    assert "table_edges: 8" in out
    assert "compile_seconds:" in out


def test_report_layer_counts(indexed_db, capsys):
    assert main(["report", "--db", str(indexed_db)]) == 0
    out = capsys.readouterr().out
    for line in (
        "01_staging: 2",
        "02_intermediate: 2",
        "04_marts: 2",
        "sources: 3",
        "assertions: 1",
    ):
        assert line in out


def test_report_table_detail(indexed_db, capsys):
    assert main(["report", "--db", str(indexed_db), "--table", "mart_kpis"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["canonical"] == "fixture-project.marts.mart_kpis"
    assert payload["layer"] == "04_marts"
    assert len(payload["upstream"]) == 2
    assert len(payload["downstream"]) == 1
    assert {c["name"] for c in payload["columns"]} >= {"total_amount", "snapshot_date"}


def test_report_unknown_table_exits_2(indexed_db, capsys):
    assert main(["report", "--db", str(indexed_db), "--table", "nope_table"]) == 2
    err = capsys.readouterr().err
    assert "nope_table" in err


def test_report_missing_db_exits_2(tmp_path, capsys):
    assert main(["report", "--db", str(tmp_path / "absent.db")]) == 2
    assert "index" in capsys.readouterr().err


GOLDEN_OK = [
    {
        "table": "marts.mart_kpis",
        "column": "total_amount",
        "direction": "upstream",
        "depth": 3,
        "expected_edges": [
            "intermediate.int_sessions.amount -> marts.mart_kpis.total_amount",
            "staging.stg_events.amount -> intermediate.int_sessions.amount",
            "raw.events.amount -> staging.stg_events.amount",
        ],
        "expect_complete": True,
    },
    {
        "table": "marts.mart_kpis",
        "column": "snapshot_date",
        "expected_edges": [],
        "expect_complete": True,
    },
]


def test_validate_golden_passes(indexed_db, tmp_path, capsys):
    golden = tmp_path / "golden.json"
    golden.write_text(json.dumps(GOLDEN_OK))
    assert main(["validate-golden", "--db", str(indexed_db), "--golden", str(golden)]) == 0
    out = capsys.readouterr().out
    assert "2/2 golden entries passed" in out


def test_validate_golden_fails_with_readable_diff(indexed_db, tmp_path, capsys):
    wrong = [
        {
            "table": "marts.mart_kpis",
            "column": "total_amount",
            "depth": 1,
            "expected_edges": ["staging.stg_customers.amount -> marts.mart_kpis.total_amount"],
        }
    ]
    golden = tmp_path / "golden.json"
    golden.write_text(json.dumps(wrong))
    assert main(["validate-golden", "--db", str(indexed_db), "--golden", str(golden)]) == 1
    out = capsys.readouterr().out
    assert "missing" in out and "extra" in out


def test_validate_golden_points_at_misplaced_file(indexed_db, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "golden_columns.json").write_text(json.dumps(GOLDEN_OK))
    assert main(["validate-golden", "--db", str(indexed_db), "--repo", str(repo)]) == 2
    err = capsys.readouterr().err
    assert str(repo / "golden_columns.json") in err
    assert "move it to" in err


def test_all_commands_default_repo_to_cwd():
    from pathlib import Path

    from dataform_context_mcp.cli import build_parser

    parser = build_parser()
    for command in ("index", "report", "serve", "validate-golden"):
        assert parser.parse_args([command]).repo == Path(".")
