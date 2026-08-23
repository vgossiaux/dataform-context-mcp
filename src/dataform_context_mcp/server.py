"""MCP server (stdio) exposing the Dataform context tools.

Every tool call starts with a staleness check (lazy reindex, D3), every
response embeds index_meta, and domain errors come back as structured
{"error": {code, message, suggestions}} payloads so agents see candidates.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable

from mcp.server import MCPServer

from . import db as store
from .db import AmbiguousError, NotFoundError
from .golden import validate_entries
from .indexer import ensure_fresh

_MAX_DEPTH = 10

_INSTRUCTIONS = (
    "Structured context for this Dataform pipeline, built deterministically from "
    "`dataform compile`. Query these tools instead of reading .sqlx files one by one: "
    "they are authoritative for the DAG. Call impact_analysis before refactoring any "
    "table. The index refreshes itself when source files change."
)


def _error(code: str, message: str, suggestions: list[str] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "suggestions": suggestions or []}}


def create_server(
    repo: Path,
    db_path: Path | None = None,
    _compile_fn: Callable[[Path], dict] | None = None,
) -> MCPServer:
    repo = Path(repo)
    mcp = MCPServer("dataform-context", instructions=_INSTRUCTIONS)

    def fresh() -> tuple[sqlite3.Connection, dict]:
        return ensure_fresh(repo, db_path, _compile_fn=_compile_fn)

    def resolve_or_error(conn: sqlite3.Connection, name: str) -> int | dict[str, Any]:
        try:
            return store.resolve(conn, name)
        except NotFoundError as err:
            return _error("not_found", str(err), err.suggestions)
        except AmbiguousError as err:
            return _error("ambiguous", str(err), err.candidates)

    def flat(levels: list[dict]) -> list[str]:
        return [node["canonical"] for level in levels for node in level["nodes"]]

    def clamp(depth: int) -> int:
        return max(1, min(int(depth), _MAX_DEPTH))

    def traversal(name: str, direction: str, depth: int) -> dict[str, Any]:
        conn, index_meta = fresh()
        try:
            resolved = resolve_or_error(conn, name)
            if isinstance(resolved, dict):
                return {**resolved, "index_meta": index_meta}
            depth = clamp(depth)
            levels = store.traverse(conn, resolved, direction, depth)
            beyond = store.traverse(conn, resolved, direction, depth + 1)
            return {
                "root": store.get_action(conn, resolved)["canonical"],
                "direction": "upstream" if direction == "up" else "downstream",
                "max_depth": depth,
                "levels": levels,
                "truncated": len(flat(beyond)) > len(flat(levels)),
                "index_meta": index_meta,
            }
        finally:
            conn.close()

    @mcp.tool()
    def get_table_context(name: str) -> dict[str, Any]:
        """Schema, layer, description, documented columns and direct neighbors of one
        table/view/declaration. Call this before reading or editing its .sqlx file."""
        conn, index_meta = fresh()
        try:
            resolved = resolve_or_error(conn, name)
            if isinstance(resolved, dict):
                return {**resolved, "index_meta": index_meta}
            action = store.get_action(conn, resolved)
            status_row = conn.execute(
                "SELECT status, reason FROM extraction_status WHERE action_id = ?", (resolved,)
            ).fetchone()
            return {
                "canonical": action["canonical"],
                "type": action["action_type"],
                "layer": action["layer"],
                "file": action["file_name"],
                "description": action["description"],
                "tags": action["tags"],
                "disabled": action["disabled"],
                "incremental": action["action_type"] == "incremental",
                "unique_key": action["unique_key"],
                "columns": action["columns"],
                "upstream": flat(store.traverse(conn, resolved, "up", 1)),
                "downstream": flat(store.traverse(conn, resolved, "down", 1)),
                "column_extraction": dict(status_row) if status_row else None,
                "index_meta": index_meta,
            }
        finally:
            conn.close()

    @mcp.tool()
    def get_upstream(name: str, depth: int = 3) -> dict[str, Any]:
        """Tables this action depends on, level by level (depth 1-10). Authoritative:
        call it before any refactor instead of grepping ref() calls."""
        return traversal(name, "up", depth)

    @mcp.tool()
    def get_downstream(name: str, depth: int = 3) -> dict[str, Any]:
        """Tables that depend on this action, level by level (depth 1-10)."""
        return traversal(name, "down", depth)

    @mcp.tool()
    def find_tables_by_layer(layer: str) -> dict[str, Any]:
        """List all actions of one pipeline layer (e.g. '01_staging', or a suffix
        like 'marts'). Layers are discovered from the repo's directory structure."""
        conn, index_meta = fresh()
        try:
            try:
                tables = store.tables_by_layer(conn, layer)
            except NotFoundError as err:
                return {
                    **_error("invalid_layer", str(err), err.suggestions),
                    "index_meta": index_meta,
                }
            except AmbiguousError as err:
                return {
                    **_error("invalid_layer", str(err), err.candidates),
                    "index_meta": index_meta,
                }
            return {
                "layer": layer,
                "tables": tables,
                "available_layers": store.available_layers(conn),
                "index_meta": index_meta,
            }
        finally:
            conn.close()

    def column_or_error(
        conn: sqlite3.Connection, action_id: int, column: str
    ) -> dict[str, Any] | None:
        candidates = store.known_columns(conn, action_id)
        if column in candidates:
            return None
        return _error(
            "not_found",
            f"no known column '{column}' on this action",
            candidates[:20],
        )

    @mcp.tool()
    def get_column_lineage(
        table: str, column: str, direction: str = "upstream", depth: int = 3
    ) -> dict[str, Any]:
        """Column-level lineage of one column (direction 'upstream' or 'downstream',
        depth 1-10). complete=false means the lineage is UNKNOWN beyond the nodes
        listed in warnings — NOT that there is no dependency."""
        if direction not in ("upstream", "downstream"):
            return _error("invalid_direction", "direction must be 'upstream' or 'downstream'")
        conn, index_meta = fresh()
        try:
            resolved = resolve_or_error(conn, table)
            if isinstance(resolved, dict):
                return {**resolved, "index_meta": index_meta}
            column_error = column_or_error(conn, resolved, column)
            if column_error:
                return {**column_error, "index_meta": index_meta}
            depth = clamp(depth)
            result = store.column_lineage(conn, resolved, column, direction, depth)
            warnings = store.extraction_warnings(conn, result["visited_action_ids"], direction)
            return {
                "table": store.get_action(conn, resolved)["canonical"],
                "column": column,
                "direction": direction,
                "depth": depth,
                "complete": not warnings,
                "edges": result["edges"],
                "warnings": warnings,
                "index_meta": index_meta,
            }
        finally:
            conn.close()

    @mcp.tool()
    def impact_analysis(name: str, column: str | None = None) -> dict[str, Any]:
        """Full downstream blast radius of a table or column (all depths, grouped by
        layer, affected assertions included). MANDATORY before renaming, dropping or
        changing the semantics of a table or column. With `column`, tables listed in
        possibly_affected have UNKNOWN column impact — never exclude them."""
        conn, index_meta = fresh()
        try:
            resolved = resolve_or_error(conn, name)
            if isinstance(resolved, dict):
                return {**resolved, "index_meta": index_meta}
            closure = store.downstream_closure(conn, resolved)
            by_layer: dict[str, list[str]] = {}
            for node in closure:
                by_layer.setdefault(node["layer"] or "(none)", []).append(node["canonical"])
            payload: dict[str, Any] = {
                "target": store.get_action(conn, resolved)["canonical"],
                "column": column,
                "direct_downstream": flat(store.traverse(conn, resolved, "down", 1)),
                "transitive_by_layer": by_layer,
                "affected_assertions": [
                    node["canonical"] for node in closure if node["type"] == "assertion"
                ],
                "counts": {"total_downstream": len(closure)},
                "index_meta": index_meta,
            }
            if column is not None:
                column_error = column_or_error(conn, resolved, column)
                if column_error:
                    return {**column_error, "index_meta": index_meta}
                lineage = store.column_lineage(conn, resolved, column, "downstream", _MAX_DEPTH)
                payload["affected_columns"] = [edge["to"] for edge in lineage["edges"]]
                # Any node whose extraction is opaque taints its own downstream cone:
                # column impact below it is unknown, never silently excluded.
                closure_names = {node["canonical"] for node in closure}
                non_ok = {
                    row[0]
                    for row in conn.execute(
                        """SELECT a.canonical FROM extraction_status s
                           JOIN actions a ON a.id = s.action_id
                           WHERE s.status NOT IN ('ok', 'source')"""
                    )
                }
                possibly: set[str] = set()
                for canonical in closure_names & non_ok:
                    possibly.add(canonical)
                    possibly.update(
                        node["canonical"]
                        for node in store.downstream_closure(conn, store.resolve(conn, canonical))
                    )
                payload["possibly_affected"] = sorted(possibly & closure_names)
            return payload
        finally:
            conn.close()

    @mcp.tool()
    def check_setup() -> dict[str, Any]:
        """End-to-end diagnostic of this installation: dataform CLI, compilation,
        index, column-lineage coverage and golden validation. Call it right after
        installing, or whenever the tools behave unexpectedly."""
        checks: list[dict[str, Any]] = []
        dataform_path = shutil.which("dataform")
        version = None
        if dataform_path:
            try:
                proc = subprocess.run(
                    ["dataform", "--version"], capture_output=True, text=True, timeout=30
                )
                version = proc.stdout.strip() or None
            except Exception:
                pass
        checks.append(
            {
                "name": "dataform_cli",
                "ok": dataform_path is not None,
                "detail": version or ("not found on PATH" if not dataform_path else dataform_path),
            }
        )
        conn, index_meta = fresh()
        try:
            checks.append(
                {
                    "name": "compile",
                    "ok": index_meta["compile_status"] == "ok",
                    "detail": index_meta["compile_error"]
                    or f"ok — dataform core {index_meta.get('dataform_version') or '?'}",
                }
            )
            counts = index_meta["counts"]
            checks.append(
                {
                    "name": "index",
                    "ok": counts["actions"] > 0,
                    "detail": (
                        f"actions={counts['actions']}, table_edges={counts['table_edges']}, "
                        f"column_edges={counts['column_edges']}, "
                        f"layers={len(index_meta['available_layers'])}"
                    ),
                }
            )
            extraction = index_meta.get("column_extraction", {})
            analyzable = sum(count for status, count in extraction.items() if status != "source")
            pct_ok = round(100 * extraction.get("ok", 0) / analyzable) if analyzable else 0
            checks.append(
                {
                    "name": "column_lineage",
                    "ok": analyzable > 0,
                    "detail": f"{extraction} — pct_ok={pct_ok}% (excluding sources)",
                }
            )
            golden_path = repo / ".dataform-context" / "golden_columns.json"
            if golden_path.exists():
                summary = validate_entries(conn, json.loads(golden_path.read_text()))
                failures = [r["label"] for r in summary["results"] if not r["ok"]]
                checks.append(
                    {
                        "name": "goldens",
                        "ok": summary["passed"] == summary["total"],
                        "detail": f"{summary['passed']}/{summary['total']} passed"
                        + (f" — failing: {failures[:5]}" if failures else ""),
                    }
                )
            else:
                checks.append(
                    {
                        "name": "goldens",
                        "ok": True,
                        "detail": "no golden file (optional) — .dataform-context/golden_columns.json",
                    }
                )
        finally:
            conn.close()
        return {
            "repo": str(repo.resolve()),
            "ok": all(check["ok"] for check in checks),
            "checks": checks,
            "index_meta": index_meta,
        }

    @mcp.tool()
    def refresh_index() -> dict[str, Any]:
        """Force a full recompile + reindex, even if no source file changed."""
        conn, _ = fresh()
        try:
            with conn:
                conn.execute("DELETE FROM meta WHERE key = 'source_hash'")
        finally:
            conn.close()
        conn, index_meta = fresh()
        conn.close()
        return index_meta

    return mcp
