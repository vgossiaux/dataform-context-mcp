# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five findings of the 2026-09-21 security audit: document the `--repo` trust boundary, restrict cache file permissions, harden golden-file parsing, pin CI actions by SHA, and stop following symlinks when hashing sources.

**Architecture:** Five independent, surgical changes. No new module. Each task touches one source file (or one doc/config file) and its test file. Tasks 2 to 5 are disjoint in files and can run in parallel; Task 1 is documentation only.

**Tech Stack:** Python >= 3.12, sqlite3 stdlib, pytest 9, ruff, `uv` for running everything (`uv run pytest`, `uv run ruff check .`).

**Spec:** The audit findings listed in the conversation of 2026-09-21 (summarised in the "Findings" section below). No separate spec file.

## Global Constraints

- Python floor: `requires-python = ">=3.12"` (pyproject.toml). No 3.13+-only APIs.
- No new runtime dependency. Only `mcp` and `sqlglot` are allowed at runtime.
- Line length 100, ruff rules `E4 E7 E9 F I` (pyproject.toml). Run `uv run ruff check . && uv run ruff format --check .` before finishing any task.
- Tests must pass without the `dataform` CLI installed: `uv run pytest -m "not integration"`.
- Do NOT commit. The main session reviews and commits after all tasks pass. Do not touch files outside the ones listed in your task.
- README is written in French. Keep technical terms in English.

## Findings (from the audit)

1. `compile.py:29` shells out to `dataform compile`, which executes the target repo's JavaScript (`includes/`, `*.js`). Any repo passed to `--repo` runs code as the user. Inherent, must be documented.
2. `db.py` stores full `query` / `incremental_query` of client pipelines in `~/.cache/dataform-context-mcp/<hash>.db` with default umask permissions.
3. `golden.py:45-48` reads `entry["table"]` / `entry["column"]` without a guard: a golden entry missing a key raises `KeyError` and crashes `check_setup` and `validate-golden` instead of returning a structured "invalid entry" result.
4. `.github/workflows/ci.yml` pins actions by major tag (`@v4`, `@v5`), not by commit SHA.
5. `staleness.py:22` uses `Path.rglob("*")` under `definitions/` and `includes/`. Whether symlinked directories are followed depends on the Python version; a symlink to a large tree in a client repo would slow every tool call. Make the behaviour explicit: never follow symlinks.

---

### Task 1: Document the trust boundary and the cache location in the README

**Files:**
- Modify: `README.md` (the `<details><summary><strong>Gouvernance & audit</strong></summary>` block, around lines 302-317)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (docs only).

- [ ] **Step 1: Locate the block**

Run: `grep -n "Gouvernance & audit" README.md`
Expected: one line number (around 303).

- [ ] **Step 2: Add two bullets to the existing list**

Insert the following two bullets right after the bullet that starts with `- **Données locales uniquement**` and before `- **Ce repo ne contient aucune métadonnée client**`:

```markdown
- **Frontière de confiance = le repo indexé** : `dataform compile` exécute le JavaScript
  du repo cible (`includes/`, `*.js`) avec les droits de l'utilisateur, à chaque
  ré-indexation. N'indexer que des repos Dataform de confiance ; ne jamais pointer
  `--repo` sur un clone non revu.
- **Contenu du cache** : l'index SQLite contient le SQL compilé de chaque action
  (`query`, `incremental_query`). Le fichier est créé en mode `0600` (lecture par
  l'utilisateur seul). Pour purger : `rm -rf ~/.cache/dataform-context-mcp/`.
```

- [ ] **Step 3: Verify rendering**

Run: `sed -n '/Gouvernance & audit/,/<\/details>/p' README.md`
Expected: the list shows 7 bullets, the two new ones in the position described above, no broken `<details>` tags.

---

### Task 2: Create the cache database with 0600 permissions

**Files:**
- Modify: `src/dataform_context_mcp/db.py:93-99` (`open_db`)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `open_db(path: Path) -> sqlite3.Connection` (existing).
- Produces: same signature; the file at `path` now has mode `0o600` after the call on POSIX.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
def test_open_db_creates_file_readable_by_owner_only(tmp_path):
    import os
    import stat

    path = tmp_path / "cache" / "ix.db"
    connection = open_db(path)
    connection.close()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_db.py::test_open_db_creates_file_readable_by_owner_only -v`
Expected: FAIL with `expected 0600, got 0o644` (or whatever the umask gives).

- [ ] **Step 3: Implement**

Replace `open_db` in `src/dataform_context_mcp/db.py` with:

```python
def open_db(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    # The index stores the compiled SQL of every action: owner-only on disk.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # non-POSIX filesystems: best effort, never fail the open
    return conn
```

Add `import os` to the stdlib import block at the top of `db.py` (keep imports sorted: `difflib`, `json`, `os`, `sqlite3`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: all tests in the file PASS, including the new one.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/dataform_context_mcp/db.py tests/test_db.py && uv run ruff format --check src/dataform_context_mcp/db.py tests/test_db.py`
Expected: no output / "All checks passed".

---

### Task 3: Return a structured result for malformed golden entries

**Files:**
- Modify: `src/dataform_context_mcp/golden.py:43-67` (`validate_entries`)
- Create: `tests/test_golden.py`

**Interfaces:**
- Consumes: `validate_entries(conn, entries: list[dict]) -> dict` (existing), `open_db`, `rebuild` from `db.py`, `graph` fixture from `tests/conftest.py`.
- Produces: same signature. An entry missing `table` or `column`, or not being a dict, yields `{"label": ..., "ok": False, "problems": ["golden entry invalid — ..."]}` instead of raising.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_golden.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_golden.py -v`
Expected: the three "reported_not_raised" tests FAIL with `KeyError` / `TypeError`; `test_valid_entry_still_passes` may PASS or FAIL depending on the fixture lineage. If it fails on `missing:`/`extra:` edges, replace `"expected_edges": []` with the actual edges printed in the failure (the fixture is deterministic) so that the test asserts current behaviour. Do not change `golden.py` to make it pass.

- [ ] **Step 3: Implement**

In `src/dataform_context_mcp/golden.py`, replace the beginning of the loop in `validate_entries` (from `for entry in entries:` down to and including the `except (...) as err:` block) with:

```python
for entry in entries:
    if not isinstance(entry, dict):
        results.append(
            {
                "label": repr(entry)[:80],
                "ok": False,
                "problems": [
                    f"golden entry invalid — expected an object, got {type(entry).__name__}"
                ],
            }
        )
        continue
    label = f"{entry.get('table', '?')}.{entry.get('column', '?')}"
    try:
        for required in ("table", "column"):
            if required not in entry:
                raise NotFoundError(f"missing required key '{required}'")
        action_id = resolve(conn, entry["table"])
        if entry["column"] not in known_columns(conn, action_id):
            raise NotFoundError(f"unknown column '{entry['column']}'")
        expected = set()
        for spec in entry.get("expected_edges", []):
            up_spec, down_spec = (side.strip() for side in spec.split("->"))
            up_table, up_column = up_spec.rsplit(".", 1)
            down_table, down_column = down_spec.rsplit(".", 1)
            expected.add(
                (
                    get_action(conn, resolve(conn, up_table))["canonical"],
                    up_column,
                    get_action(conn, resolve(conn, down_table))["canonical"],
                    down_column,
                )
            )
    except (NotFoundError, AmbiguousError, ValueError, TypeError, AttributeError) as err:
        results.append({"label": label, "ok": False, "problems": [f"golden entry invalid — {err}"]})
        continue
```

The rest of the function (from `direction = entry.get("direction", "upstream")` onwards) is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_golden.py tests/test_server.py -m "not integration" -v`
Expected: all PASS. `test_server.py` is included because `check_setup` calls `validate_entries`.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/dataform_context_mcp/golden.py tests/test_golden.py && uv run ruff format --check src/dataform_context_mcp/golden.py tests/test_golden.py`
Expected: clean. If `ruff format --check` complains, run `uv run ruff format src/dataform_context_mcp/golden.py tests/test_golden.py`.

---

### Task 4: Pin GitHub Actions by commit SHA

**Files:**
- Modify: `.github/workflows/ci.yml:13-15`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Resolve the SHA of each tag currently used**

Run, for each of `actions/checkout v4`, `astral-sh/setup-uv v5`, `actions/setup-node v4`:

```bash
for spec in "actions/checkout v4" "astral-sh/setup-uv v5" "actions/setup-node v4"; do
  set -- $spec
  sha=$(git ls-remote --tags "https://github.com/$1" | grep -E "refs/tags/$2(\^\{\})?$" | tail -1 | cut -f1)
  echo "$1 $2 $sha"
done
```

Expected: three lines, each ending with a 40-hex-character SHA. If a SHA is empty, the tag name changed upstream: stop and report instead of guessing.

- [ ] **Step 2: Edit the workflow**

Replace lines 13-15 of `.github/workflows/ci.yml` with the resolved SHAs, keeping the tag as a trailing comment (Dependabot and humans read it):

```yaml
      - uses: actions/checkout@<SHA_CHECKOUT> # v4
      - uses: astral-sh/setup-uv@<SHA_SETUP_UV> # v5
      - uses: actions/setup-node@<SHA_SETUP_NODE> # v4
```

`<SHA_...>` must be the exact 40-character values printed in Step 1.

- [ ] **Step 3: Validate the YAML**

Run: `uv run python -c "import yaml" 2>/dev/null && uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')" || python3 -c "import json,re; t=open('.github/workflows/ci.yml').read(); assert len(re.findall(r'uses: [^@]+@[0-9a-f]{40} # v', t))==3; print('3 pinned uses')"`
Expected: `yaml ok` or `3 pinned uses`.

---

### Task 5: Never follow symlinks when hashing source files

**Files:**
- Modify: `src/dataform_context_mcp/staleness.py:16-33` (`source_hash`)
- Test: `tests/test_staleness.py`

**Interfaces:**
- Consumes: `source_hash(repo: Path) -> str` (existing).
- Produces: same signature. Symlinked directories under `definitions/` and `includes/` are not descended into; symlinked files are skipped. Regular files hash exactly as before (same digest for the same tree).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_staleness.py` (the file already imports `source_hash`; add `import os` at the top if missing):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_staleness.py -v`
Expected: at least `test_symlinked_file_is_skipped` FAILS (rglob yields the symlinked file and `is_file()` follows it). `test_symlinked_directory_is_not_followed` may pass or fail depending on the Python version: the point of the task is to make it pass on every supported version.

- [ ] **Step 3: Implement**

Replace `source_hash` in `src/dataform_context_mcp/staleness.py` with:

```python
def source_hash(repo: Path) -> str:
    repo = Path(repo)
    files: list[Path] = []
    for dirname in _WATCHED_DIRS:
        root = repo / dirname
        if not root.is_dir():
            continue
        # followlinks=False: a symlink to a large tree in a client repo must not
        # make every tool call re-hash it. Symlinked files are skipped too.
        for current, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for filename in filenames:
                path = Path(current) / filename
                if not path.is_symlink() and path.is_file():
                    files.append(path)
    for filename in _WATCHED_FILES:
        path = repo / filename
        if path.is_file():
            files.append(path)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: str(p.relative_to(repo))):
        digest.update(str(path.relative_to(repo)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
```

Add `import os` to the import block (order: `hashlib`, `os`, then `from pathlib import Path`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_staleness.py tests/test_indexer.py -v`
Expected: all PASS. `test_indexer.py` is included because `ensure_fresh` relies on the hash being stable across calls.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/dataform_context_mcp/staleness.py tests/test_staleness.py && uv run ruff format --check src/dataform_context_mcp/staleness.py tests/test_staleness.py`
Expected: clean.

---

## Final verification (main session, after all tasks)

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pytest -v` (integration tests included if `dataform` is on PATH)
- [ ] `git diff --stat` shows only: `README.md`, `.github/workflows/ci.yml`, `src/dataform_context_mcp/{db,golden,staleness}.py`, `tests/{test_db,test_golden,test_staleness}.py`, and this plan.
- [ ] One commit per task, messages: `docs: document repo trust boundary and cache contents`, `fix(db): create cache index with 0600 permissions`, `fix(golden): report malformed entries instead of raising`, `ci: pin actions by commit SHA`, `fix(staleness): never follow symlinks when hashing sources`.
