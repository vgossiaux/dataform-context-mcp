"""Command-line entry point: index | report | serve | validate-golden."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .compile import load_graph
from .db import (
    AmbiguousError,
    NotFoundError,
    column_lineage,
    extraction_warnings,
    get_action,
    get_meta,
    known_columns,
    open_db,
    rebuild,
    resolve,
    traverse,
)
from .indexer import default_db_path, ensure_fresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataform-context",
        description="Deterministic Dataform pipeline context: indexing CLI and MCP server.",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_index = subparsers.add_parser(
        "index", help="Compile the Dataform repo and (re)build the context index"
    )
    p_index.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to the Dataform repository (default: current directory)",
    )
    p_index.add_argument("--db", type=Path, help="Index database path (default: cache dir)")
    p_index.add_argument(
        "--from-json",
        dest="from_json",
        type=Path,
        help="Load a captured `dataform compile --json` output instead of compiling (tests)",
    )

    p_report = subparsers.add_parser("report", help="Print a summary of the indexed graph")
    p_report.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to the Dataform repository (default: current directory)",
    )
    p_report.add_argument("--db", type=Path, help="Index database path (default: cache dir)")
    p_report.add_argument("--table", help="Print the full context of one table as JSON")

    p_serve = subparsers.add_parser("serve", help="Run the MCP server (stdio)")
    p_serve.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to the Dataform repository (default: current directory — MCP clients "
        "launch project servers from the project root)",
    )
    p_serve.add_argument("--db", type=Path)

    p_golden = subparsers.add_parser(
        "validate-golden",
        help="Validate column lineage against a golden file "
        "(JSON list of {table, column, direction, depth, expected_edges, expect_complete})",
    )
    p_golden.add_argument("--repo", type=Path, default=Path("."))
    p_golden.add_argument("--db", type=Path)
    p_golden.add_argument(
        "--golden",
        type=Path,
        help="Golden file (default: <repo>/.dataform-context/golden_columns.json)",
    )
    return parser


def _resolve_db(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Path:
    if args.db:
        return args.db
    if args.repo:
        return default_db_path(args.repo)
    parser.error(f"{args.command}: --repo or --db is required")
    raise AssertionError  # unreachable


def cmd_index(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    db_path = _resolve_db(args, parser)
    started = time.perf_counter()
    if args.from_json:
        graph = load_graph(json.loads(args.from_json.read_text()))
        conn = open_db(db_path)
        rebuild(conn, graph, source_hash="manual")
        meta = get_meta(conn)
        counts = meta["counts"]
    else:
        if not args.repo:
            parser.error("index: --repo is required unless --from-json is given")
        conn, index_meta = ensure_fresh(args.repo, db_path)
        if index_meta["compile_status"] == "error":
            print(f"compile error:\n{index_meta['compile_error']}", file=sys.stderr)
            return 1
        counts = index_meta["counts"]
    elapsed = time.perf_counter() - started
    print(f"db: {db_path}")
    print(f"actions: {counts['actions']}")
    print(f"table_edges: {counts['table_edges']}")
    print(f"compile_seconds: {elapsed:.1f}")
    return 0


def cmd_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    db_path = _resolve_db(args, parser)
    if not Path(db_path).exists():
        print(f"no index at {db_path} — run `dataform-context index` first", file=sys.stderr)
        return 2
    conn = open_db(db_path)
    if args.table:
        try:
            action_id = resolve(conn, args.table)
        except NotFoundError as err:
            print(f"'{args.table}' not found. Suggestions: {err.suggestions}", file=sys.stderr)
            return 2
        except AmbiguousError as err:
            print(f"'{args.table}' is ambiguous. Candidates: {err.candidates}", file=sys.stderr)
            return 2
        action = get_action(conn, action_id)
        detail = {
            "canonical": action["canonical"],
            "type": action["action_type"],
            "layer": action["layer"],
            "file": action["file_name"],
            "description": action["description"],
            "tags": action["tags"],
            "columns": action["columns"],
            "upstream": [
                n["canonical"] for lvl in traverse(conn, action_id, "up", 1) for n in lvl["nodes"]
            ],
            "downstream": [
                n["canonical"] for lvl in traverse(conn, action_id, "down", 1) for n in lvl["nodes"]
            ],
        }
        print(json.dumps(detail, indent=2))
        return 0
    meta = get_meta(conn)
    print(f"indexed_at: {meta.get('indexed_at', '?')}")
    print(f"actions: {meta['counts']['actions']}")
    print(f"table_edges: {meta['counts']['table_edges']}")
    print("by layer:")
    for layer, count in conn.execute(
        "SELECT COALESCE(layer, '(none)'), COUNT(*) FROM actions GROUP BY layer ORDER BY layer"
    ):
        print(f"  {layer}: {count}")
    extraction = meta.get("column_extraction", {})
    if extraction:
        analyzable = sum(count for status, count in extraction.items() if status != "source")
        pct_ok = 100 * extraction.get("ok", 0) / analyzable if analyzable else 0.0
        print("column extraction:")
        for status in sorted(extraction):
            print(f"  {status}: {extraction[status]}")
        print(f"  pct_ok (hors source): {pct_ok:.0f}%")
    return 0


def cmd_validate_golden(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    db_path = _resolve_db(args, parser)
    if not Path(db_path).exists():
        print(f"no index at {db_path} — run `dataform-context index` first", file=sys.stderr)
        return 2
    golden_path = args.golden or (
        args.repo / ".dataform-context" / "golden_columns.json" if args.repo else None
    )
    if golden_path is None or not Path(golden_path).exists():
        print(f"golden file not found: {golden_path}", file=sys.stderr)
        return 2
    entries = json.loads(Path(golden_path).read_text())
    conn = open_db(db_path)
    failures = 0
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
            print(f"FAIL {label}: golden entry invalid — {err}")
            failures += 1
            continue
        direction = entry.get("direction", "upstream")
        result = column_lineage(conn, action_id, entry["column"], direction, entry.get("depth", 3))
        actual = {
            (e["from"]["table"], e["from"]["column"], e["to"]["table"], e["to"]["column"])
            for e in result["edges"]
        }
        complete = not extraction_warnings(conn, result["visited_action_ids"], direction)
        problems = []
        missing = expected - actual
        extra = actual - expected
        if missing:
            problems.append(f"missing: {sorted(missing)}")
        if extra:
            problems.append(f"extra: {sorted(extra)}")
        if "expect_complete" in entry and complete != entry["expect_complete"]:
            problems.append(f"complete={complete}, expected {entry['expect_complete']}")
        if problems:
            failures += 1
            print(f"FAIL {label}: " + " | ".join(problems))
        else:
            print(f"PASS {label} ({len(actual)} edges, complete={complete})")
    print(f"{len(entries) - failures}/{len(entries)} golden entries passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1
    if args.command == "index":
        return cmd_index(args, parser)
    if args.command == "report":
        return cmd_report(args, parser)
    if args.command == "serve":
        from .server import create_server

        create_server(args.repo, args.db).run("stdio")
        return 0
    if args.command == "validate-golden":
        return cmd_validate_golden(args, parser)
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
