"""Content-hash staleness: stable, sensitive to watched files only."""

import os
import shutil

import pytest

from dataform_context_mcp.staleness import source_hash
from tests.conftest import MINI_REPO


@pytest.fixture()
def repo_copy(tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(
        MINI_REPO, dest, ignore=shutil.ignore_patterns("node_modules", ".dataform", ".gitignore")
    )
    return dest


def test_hash_is_stable(repo_copy):
    assert source_hash(repo_copy) == source_hash(repo_copy)


def test_hash_changes_on_sqlx_content_change(repo_copy):
    before = source_hash(repo_copy)
    target = repo_copy / "definitions/transforms/04_marts/mart_kpis.sqlx"
    target.write_text(target.read_text() + "\n-- edited\n")
    assert source_hash(repo_copy) != before


def test_hash_changes_on_includes_change(repo_copy):
    before = source_hash(repo_copy)
    target = repo_copy / "includes/utils.js"
    target.write_text(target.read_text() + "\n// edited\n")
    assert source_hash(repo_copy) != before


def test_hash_ignores_files_outside_watched_set(repo_copy):
    before = source_hash(repo_copy)
    (repo_copy / "README.md").write_text("# not watched\n")
    assert source_hash(repo_copy) == before


def test_hash_ignores_touch_without_content_change(repo_copy):
    before = source_hash(repo_copy)
    target = repo_copy / "definitions/transforms/04_marts/mart_kpis.sqlx"
    target.touch()
    assert source_hash(repo_copy) == before


def test_symlinked_directory_is_not_followed(tmp_path):
    repo = tmp_path / "repo"
    (repo / "definitions").mkdir(parents=True)
    (repo / "definitions" / "a.sqlx").write_text("select 1")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "huge.sqlx").write_text("select 2")
    before = source_hash(repo)
    os.symlink(outside, repo / "definitions" / "linked", target_is_directory=True)
    assert source_hash(repo) == before
    (outside / "huge.sqlx").write_text("select 3")
    assert source_hash(repo) == before


def test_symlinked_file_is_skipped(tmp_path):
    repo = tmp_path / "repo"
    (repo / "includes").mkdir(parents=True)
    (repo / "includes" / "a.js").write_text("const a = 1")
    target = tmp_path / "target.js"
    target.write_text("const b = 2")
    before = source_hash(repo)
    os.symlink(target, repo / "includes" / "b.js")
    assert source_hash(repo) == before
