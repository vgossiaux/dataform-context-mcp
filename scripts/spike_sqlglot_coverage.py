"""Spike: measure real sqlglot coverage on a compiled Dataform graph.

Usage: python spike_sqlglot_coverage.py <compiled_graph.json> <output_dir>

Emits <output_dir>/coverage.json and <output_dir>/coverage.md containing ONLY
aggregated counts, categories, timings and versions — never SQL text nor
table/column names (data governance: reports must stay shareable).
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.lineage import lineage

DIALECT = "bigquery"

# Category priority: first match wins.
PARSE_ERROR = "PARSE_ERROR"
MULTI_STATEMENT = "MULTI_STATEMENT"
MERGE_OR_DML = "MERGE_OR_DML"
EMPTY_PROJECTION = "EMPTY_PROJECTION"
OK = "OK"

DML_NODES = (exp.Merge, exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter)


def iter_actions(graph: dict):
    """Yield (kind, action) for every action carrying SQL."""
    for kind in ("tables", "operations", "assertions"):
        for action in graph.get(kind, []):
            yield kind, action


def action_queries(action: dict) -> list[str]:
    queries: list[str] = []
    if action.get("query"):
        queries.append(action["query"])
    for q in action.get("queries", []):
        if q:
            queries.append(q)
    if action.get("incrementalQuery"):
        queries.append(action["incrementalQuery"])
    return queries


def classify(sql: str) -> tuple[str, bool, list[str]]:
    """Return (category, has_unnest_or_struct, projected_column_names)."""
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except Exception:
        return PARSE_ERROR, False, []
    if not statements:
        return PARSE_ERROR, False, []
    if len(statements) > 1:
        return MULTI_STATEMENT, False, []
    stmt = statements[0]
    flagged = bool(list(stmt.find_all(exp.Unnest))) or bool(list(stmt.find_all(exp.Struct)))
    if isinstance(stmt, DML_NODES) or list(stmt.find_all(exp.Merge)):
        return MERGE_OR_DML, flagged, []
    select = stmt if isinstance(stmt, exp.Select) else stmt.find(exp.Select)
    if select is None:
        return MERGE_OR_DML, flagged, []
    names = [n for n in stmt.named_selects if n and n != "*"]
    if not names:
        return EMPTY_PROJECTION, flagged, []
    return OK, flagged, names


def main() -> int:
    graph_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = json.loads(graph_path.read_text())

    categories: Counter[str] = Counter()
    per_kind: Counter[str] = Counter()
    unnest_or_struct = 0
    lineage_cols_ok = 0
    lineage_cols_failed = 0
    actions_with_sql = 0
    incremental_queries = 0

    t0 = time.perf_counter()
    for kind, action in iter_actions(graph):
        queries = action_queries(action)
        if not queries:
            continue
        actions_with_sql += 1
        per_kind[kind] += 1
        if action.get("incrementalQuery"):
            incremental_queries += 1
        # Classify on the primary query; worst category across queries wins.
        results = [classify(q) for q in queries]
        order = [PARSE_ERROR, MULTI_STATEMENT, MERGE_OR_DML, EMPTY_PROJECTION, OK]
        category = min((r[0] for r in results), key=order.index)
        categories[category] += 1
        if any(r[1] for r in results):
            unnest_or_struct += 1
        if category == OK:
            sql, names = queries[0], results[0][2]
            for name in names:
                try:
                    lineage(name, sql, dialect=DIALECT)
                    lineage_cols_ok += 1
                except Exception:
                    lineage_cols_failed += 1
    elapsed = time.perf_counter() - t0

    # Graph stats (doc density, camelCase sanity) — counts only.
    all_actions = [a for _, a in iter_actions(graph)] + list(graph.get("declarations", []))
    documented = sum(1 for a in all_actions if (a.get("actionDescriptor") or {}).get("columns"))
    camel_keys = {"fileName", "dependencyTargets", "target"}
    camel_ok = sum(1 for a in all_actions if camel_keys & set(a.keys()))

    report = {
        "input": graph_path.name,
        "sqlglot_version": sqlglot.__version__,
        "actions_with_sql": actions_with_sql,
        "actions_by_kind": dict(per_kind),
        "categories": dict(categories),
        "pct_parse_ok": round(100 * categories[OK] / actions_with_sql, 1)
        if actions_with_sql
        else 0,
        "actions_with_unnest_or_struct": unnest_or_struct,
        "incremental_queries": incremental_queries,
        "lineage_columns_ok": lineage_cols_ok,
        "lineage_columns_failed": lineage_cols_failed,
        "graph_stats": {
            "tables": len(graph.get("tables", [])),
            "declarations": len(graph.get("declarations", [])),
            "operations": len(graph.get("operations", [])),
            "assertions": len(graph.get("assertions", [])),
            "actions_with_documented_columns": documented,
            "actions_with_camelcase_keys": camel_ok,
        },
        "parse_seconds": round(elapsed, 2),
    }

    (out_dir / "coverage.json").write_text(json.dumps(report, indent=2))
    lines = [f"# sqlglot coverage — {graph_path.name}", ""]
    lines += [f"- {k}: {v}" for k, v in report.items() if k != "graph_stats"]
    lines += ["", "## graph_stats"] + [f"- {k}: {v}" for k, v in report["graph_stats"].items()]
    (out_dir / "coverage.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
