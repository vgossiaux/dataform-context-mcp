"""ensure_fresh contract: build when missing, skip when unchanged, rebuild on
change, keep the last good index when the compilation breaks."""

import shutil

import pytest

from dataform_context_mcp.compile import CompileError
from dataform_context_mcp.db import resolve
from dataform_context_mcp.indexer import ensure_fresh
from tests.conftest import MINI_REPO, requires_dataform


@pytest.fixture()
def repo_copy(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(
        MINI_REPO, dest, ignore=shutil.ignore_patterns("node_modules", ".dataform", ".gitignore")
    )
    return dest


@pytest.fixture()
def fake_compile(raw_graph):
    calls = []

    def compile_fn(repo):
        calls.append(repo)
        return raw_graph

    compile_fn.calls = calls
    return compile_fn


def test_builds_when_db_missing(repo_copy, tmp_path, fake_compile):
    conn, meta = ensure_fresh(repo_copy, tmp_path / "ix.db", _compile_fn=fake_compile)
    assert len(fake_compile.calls) == 1
    assert meta["compile_status"] == "ok"
    assert meta["stale"] is False
    assert meta["counts"]["actions"] == 10
    conn.close()


def test_skips_rebuild_when_hash_unchanged(repo_copy, tmp_path, fake_compile):
    db = tmp_path / "ix.db"
    conn, first = ensure_fresh(repo_copy, db, _compile_fn=fake_compile)
    conn.close()
    conn, second = ensure_fresh(repo_copy, db, _compile_fn=fake_compile)
    conn.close()
    assert len(fake_compile.calls) == 1  # no second compile
    assert second["indexed_at"] == first["indexed_at"]


def test_rebuilds_on_change(repo_copy, tmp_path, fake_compile):
    db = tmp_path / "ix.db"
    conn, _ = ensure_fresh(repo_copy, db, _compile_fn=fake_compile)
    conn.close()
    target = repo_copy / "definitions/transforms/04_marts/mart_kpis.sqlx"
    target.write_text(target.read_text() + "\n-- edited\n")
    conn, meta = ensure_fresh(repo_copy, db, _compile_fn=fake_compile)
    conn.close()
    assert len(fake_compile.calls) == 2
    assert meta["compile_status"] == "ok"


def test_keeps_last_good_index_on_compile_error(repo_copy, tmp_path, raw_graph):
    db = tmp_path / "ix.db"

    def good(repo):
        return raw_graph

    conn, _ = ensure_fresh(repo_copy, db, _compile_fn=good)
    good_hash_meta = conn.execute("SELECT value FROM meta WHERE key='source_hash'").fetchone()[0]
    conn.close()

    target = repo_copy / "definitions/transforms/04_marts/mart_kpis.sqlx"
    target.write_text("config { broken")

    def broken(repo):
        raise CompileError("boom", exit_code=1, stderr="syntax error")

    conn, meta = ensure_fresh(repo_copy, db, _compile_fn=broken)
    assert meta["compile_status"] == "error"
    assert "syntax error" in meta["compile_error"]
    assert meta["stale"] is True
    # last good index still answers
    assert resolve(conn, "mart_kpis") is not None
    assert meta["counts"]["actions"] == 10
    # stored hash untouched → next call retries the compile
    assert (
        conn.execute("SELECT value FROM meta WHERE key='source_hash'").fetchone()[0]
        == good_hash_meta
    )
    conn.close()


@requires_dataform
@pytest.mark.integration
def test_live_ensure_fresh(repo_copy, tmp_path):
    conn, meta = ensure_fresh(repo_copy, tmp_path / "ix.db")
    assert meta["compile_status"] == "ok"
    assert meta["counts"]["actions"] == 10
    conn.close()
