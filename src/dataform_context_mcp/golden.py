"""Golden-set validation: compare extracted column lineage against hand-traced truth."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import (
    AmbiguousError,
    NotFoundError,
    column_lineage,
    extraction_warnings,
    get_action,
    known_columns,
    resolve,
)

GOLDEN_RELPATH = Path(".dataform-context") / "golden_columns.json"


def locate_golden(repo: Path) -> tuple[Path, Path | None]:
    """Resolve the golden file for a repo.

    Returns (canonical_path, misplaced_path). `misplaced_path` is set when no file
    sits at the canonical location but one exists at the repo root — the spot users
    reach for first. Callers report it instead of claiming no golden set exists,
    which is a silently wrong diagnostic.
    """
    canonical = repo / GOLDEN_RELPATH
    if canonical.exists():
        return canonical, None
    root = repo / GOLDEN_RELPATH.name
    return canonical, root if root.exists() else None


def validate_entries(conn: sqlite3.Connection, entries: list[dict]) -> dict:
    """Validate golden entries against the index.

    Returns {"total": int, "passed": int, "results": [{"label", "ok", "problems",
    "edges", "complete"}]}. An entry passes when its edge set matches exactly and
    (if provided) expect_complete matches.
    """
    results: list[dict] = []
    for entry in entries:
        label = f"{entry['table']}.{entry['column']}"
        try:
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
        except (NotFoundError, AmbiguousError, ValueError) as err:
            results.append(
                {"label": label, "ok": False, "problems": [f"golden entry invalid — {err}"]}
            )
            continue
        direction = entry.get("direction", "upstream")
        lineage = column_lineage(conn, action_id, entry["column"], direction, entry.get("depth", 3))
        actual = {
            (e["from"]["table"], e["from"]["column"], e["to"]["table"], e["to"]["column"])
            for e in lineage["edges"]
        }
        complete = not extraction_warnings(conn, lineage["visited_action_ids"], direction)
        problems: list[str] = []
        missing = expected - actual
        extra = actual - expected
        if missing:
            problems.append(f"missing: {sorted(missing)}")
        if extra:
            problems.append(f"extra: {sorted(extra)}")
        if "expect_complete" in entry and complete != entry["expect_complete"]:
            problems.append(f"complete={complete}, expected {entry['expect_complete']}")
        results.append(
            {
                "label": label,
                "ok": not problems,
                "problems": problems,
                "edges": len(actual),
                "complete": complete,
            }
        )
    return {
        "total": len(entries),
        "passed": sum(1 for r in results if r["ok"]),
        "results": results,
    }
