"""Column-level lineage extraction with sqlglot (explicit statuses, never silent).

Statuses: ok | partial | failed | not_attempted (declarations get "source",
assigned by the caller). An empty edge list with status "ok" means a real
absence of upstream (e.g. CURRENT_DATE()); anything not analyzable is
surfaced through status + reason — never presented as "no dependency".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.lineage import lineage as sqlglot_lineage
from sqlglot.optimizer.qualify import qualify

from .model import Action, CompiledGraphData

_DIALECT = "bigquery"
_EXPRESSION_CAP = 200
_ACTION_TIME_BUDGET = 10.0  # seconds; soft guard between columns

_DML_NODES = (exp.Merge, exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter)


@dataclass(frozen=True)
class ColumnEdge:
    up_table: str  # canonical
    up_column: str
    down_table: str  # canonical
    down_column: str
    expression: str | None = None


@dataclass
class ExtractionResult:
    status: str  # ok|partial|failed|not_attempted
    reason: str | None = None
    edges: list[ColumnEdge] = field(default_factory=list)
    output_columns: list[str] = field(default_factory=list)


def extract_column_lineage(action: Action, schemas: dict[str, list[str]]) -> ExtractionResult:
    """Extract column edges for one action given upstream schemas
    (canonical name -> known column names)."""
    if action.action_type == "operations":
        return ExtractionResult("not_attempted", "operations action (MERGE/DML not analyzed)")
    if not action.query:
        return ExtractionResult("not_attempted", "no query")
    try:
        statements = [s for s in sqlglot.parse(action.query, read=_DIALECT) if s is not None]
    except Exception as err:  # sqlglot raises many error types; classify, don't crash
        return ExtractionResult("failed", f"parse error: {type(err).__name__}")
    if not statements:
        return ExtractionResult("failed", "parse error: empty result")
    if len(statements) > 1:
        return ExtractionResult("not_attempted", "multi-statement script")
    statement = statements[0]
    if isinstance(statement, _DML_NODES) or statement.find(exp.Merge):
        return ExtractionResult("not_attempted", "MERGE/DML statement")
    if statement.find(exp.Select) is None:
        return ExtractionResult("not_attempted", "no SELECT to analyze")

    # Only the schemas of THIS action's upstream tables are relevant; a partial
    # schema with strict validation would reject legitimately unresolvable columns.
    upstream = {d.canonical() for d in action.dependency_targets}
    nested_schema = _nested_schema({c: schemas[c] for c in upstream if c in schemas})
    qualified = statement
    try:
        qualified = qualify(
            statement.copy(),
            schema=nested_schema,
            dialect=_DIALECT,
            validate_qualify_columns=False,
            infer_schema=True,
            allow_partial_qualification=True,
        )
    except Exception:
        pass  # fall back to the raw statement; per-column failures surface below

    names = [n for n in qualified.named_selects if n]
    star_unresolved = "*" in names
    names = [n for n in names if n != "*"]

    down_canonical = action.target.canonical()
    edges: list[ColumnEdge] = []
    unresolved: list[str] = []
    reason = None
    started = time.perf_counter()
    for column in names:
        if time.perf_counter() - started > _ACTION_TIME_BUDGET:
            unresolved.extend(names[names.index(column) :])
            reason = f"timeout after {_ACTION_TIME_BUDGET:.0f}s"
            break
        try:
            node = sqlglot_lineage(column, qualified, schema=nested_schema, dialect=_DIALECT)
        except Exception as err:
            unresolved.append(f"{column} ({type(err).__name__})")
            continue
        expression = node.expression.sql(dialect=_DIALECT)[:_EXPRESSION_CAP]
        for leaf in node.walk():
            if not isinstance(leaf.source, exp.Table):
                continue
            table = leaf.source
            if not (table.catalog and table.db and table.name):
                unresolved.append(f"{column} (unqualified table)")
                continue
            up_canonical = f"{table.catalog}.{table.db}.{table.name}"
            if up_canonical == down_canonical:
                # Self-referencing pattern (${self()} row preservation, incremental):
                # expected, carries no cross-table lineage — skip without penalty.
                continue
            up_column = leaf.name.split(".")[-1].strip('"`')
            edges.append(ColumnEdge(up_canonical, up_column, down_canonical, column, expression))

    if star_unresolved:
        status = "partial"
        reason = reason or "select_star_unresolved"
    elif unresolved:
        status = "partial" if edges else "failed"
        reason = reason or f"unresolved columns: {', '.join(unresolved[:5])}"
    else:
        status = "ok"
    deduped = list(dict.fromkeys(edges))
    return ExtractionResult(status, reason, deduped, output_columns=names)


def extract_for_graph(graph: CompiledGraphData) -> dict[str, ExtractionResult]:
    """Extract lineage for every action, walking the table-level DAG in
    topological order so downstream actions see upstream output schemas."""
    by_canonical = {a.target.canonical(): a for a in graph.actions}
    order = _topological(graph)
    # seed schemas with documented columns (actionDescriptor)
    schemas: dict[str, list[str]] = {
        canonical: [c.name for c in action.columns]
        for canonical, action in by_canonical.items()
        if action.columns
    }
    results: dict[str, ExtractionResult] = {}
    for canonical in order:
        action = by_canonical[canonical]
        if action.action_type == "declaration":
            results[canonical] = ExtractionResult("source", None)
            continue
        result = extract_column_lineage(action, schemas)
        results[canonical] = result
        if result.output_columns:
            schemas[canonical] = result.output_columns
    return results


def _nested_schema(schemas: dict[str, list[str]]) -> dict:
    nested: dict = {}
    for canonical, columns in schemas.items():
        if not columns:
            continue
        parts = canonical.split(".")
        if len(parts) != 3:
            continue
        catalog, db, table = parts
        nested.setdefault(catalog, {}).setdefault(db, {})[table] = {
            column: "UNKNOWN" for column in columns if "." not in column
        }
    return {k: v for k, v in nested.items() if v}


def _topological(graph: CompiledGraphData) -> list[str]:
    known = {a.target.canonical() for a in graph.actions}
    pending = {
        a.target.canonical(): {
            d.canonical() for d in a.dependency_targets if d.canonical() in known
        }
        for a in graph.actions
    }
    order: list[str] = []
    while pending:
        ready = sorted(name for name, deps in pending.items() if not deps)
        if not ready:  # cycle safety: dataform enforces a DAG, but never hang
            order.extend(sorted(pending))
            break
        for name in ready:
            order.append(name)
            del pending[name]
        for deps in pending.values():
            deps.difference_update(ready)
    return order
