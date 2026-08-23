"""SQLite graph store: schema, rebuild, name resolution, recursive traversals."""

from __future__ import annotations

import difflib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .layers import infer_layer
from .lineage import extract_for_graph
from .model import CompiledGraphData

_DDL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS actions(
  id INTEGER PRIMARY KEY,
  canonical TEXT UNIQUE NOT NULL,
  database TEXT NOT NULL, schema TEXT NOT NULL, name TEXT NOT NULL,
  action_type TEXT NOT NULL,
  file_name TEXT, layer TEXT,
  description TEXT, tags TEXT NOT NULL DEFAULT '[]',
  disabled INTEGER NOT NULL DEFAULT 0,
  unique_key TEXT NOT NULL DEFAULT '[]',
  query TEXT, incremental_query TEXT
);
CREATE TABLE IF NOT EXISTS columns(
  action_id INTEGER NOT NULL REFERENCES actions(id),
  name TEXT NOT NULL, description TEXT, data_type TEXT,
  PRIMARY KEY(action_id, name)
);
CREATE TABLE IF NOT EXISTS table_edges(
  upstream_id INTEGER NOT NULL REFERENCES actions(id),
  downstream_id INTEGER NOT NULL REFERENCES actions(id),
  PRIMARY KEY(upstream_id, downstream_id)
);
CREATE TABLE IF NOT EXISTS column_edges(
  upstream_action INTEGER NOT NULL, upstream_column TEXT NOT NULL,
  downstream_action INTEGER NOT NULL, downstream_column TEXT NOT NULL,
  expression TEXT,
  PRIMARY KEY(upstream_action, upstream_column, downstream_action, downstream_column)
);
CREATE TABLE IF NOT EXISTS extraction_status(
  action_id INTEGER PRIMARY KEY REFERENCES actions(id),
  status TEXT NOT NULL,
  reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_down ON table_edges(downstream_id);
CREATE INDEX IF NOT EXISTS idx_actions_name ON actions(name);
"""

_TRAVERSE_SQL = {
    "up": """
        WITH RECURSIVE walk(id, depth) AS (
          SELECT upstream_id, 1 FROM table_edges WHERE downstream_id = :start
          UNION
          SELECT e.upstream_id, walk.depth + 1
          FROM table_edges e JOIN walk ON e.downstream_id = walk.id
          WHERE walk.depth < :max_depth
        )
        SELECT a.canonical, a.action_type AS type, a.layer, MIN(walk.depth) AS depth
        FROM walk JOIN actions a ON a.id = walk.id
        GROUP BY walk.id ORDER BY depth, a.canonical
    """,
    "down": """
        WITH RECURSIVE walk(id, depth) AS (
          SELECT downstream_id, 1 FROM table_edges WHERE upstream_id = :start
          UNION
          SELECT e.downstream_id, walk.depth + 1
          FROM table_edges e JOIN walk ON e.upstream_id = walk.id
          WHERE walk.depth < :max_depth
        )
        SELECT a.canonical, a.action_type AS type, a.layer, MIN(walk.depth) AS depth
        FROM walk JOIN actions a ON a.id = walk.id
        GROUP BY walk.id ORDER BY depth, a.canonical
    """,
}


class NotFoundError(Exception):
    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.suggestions = suggestions or []


class AmbiguousError(Exception):
    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


def open_db(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def rebuild(conn: sqlite3.Connection, graph: CompiledGraphData, source_hash: str) -> None:
    """Full drop-and-rebuild in a single transaction (idempotent)."""
    with conn:
        for table in ("column_edges", "extraction_status", "columns", "table_edges", "actions"):
            conn.execute(f"DELETE FROM {table}")
        ids: dict[str, int] = {}
        for action in graph.actions:
            canonical = action.target.canonical()
            cursor = conn.execute(
                """INSERT INTO actions(canonical, database, schema, name, action_type,
                                       file_name, layer, description, tags, disabled,
                                       unique_key, query, incremental_query)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    canonical,
                    action.target.database,
                    action.target.schema,
                    action.target.name,
                    action.action_type,
                    action.file_name,
                    infer_layer(action.file_name),
                    action.description,
                    json.dumps(action.tags),
                    int(action.disabled),
                    json.dumps(action.unique_key),
                    action.query,
                    action.incremental_query,
                ),
            )
            ids[canonical] = cursor.lastrowid
            for column in action.columns:
                conn.execute(
                    "INSERT OR REPLACE INTO columns(action_id, name, description) VALUES(?,?,?)",
                    (cursor.lastrowid, column.name, column.description),
                )
        for action in graph.actions:
            downstream_id = ids[action.target.canonical()]
            for dep in action.dependency_targets:
                upstream_id = ids.get(dep.canonical())
                if upstream_id is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO table_edges(upstream_id, downstream_id) VALUES(?,?)",
                        (upstream_id, downstream_id),
                    )
        edge_pairs = {
            (row[0], row[1])
            for row in conn.execute("SELECT upstream_id, downstream_id FROM table_edges")
        }
        for canonical, result in extract_for_graph(graph).items():
            action_id = ids[canonical]
            status, reason = result.status, result.reason
            rejected = 0
            for edge in result.edges:
                upstream_id = ids.get(edge.up_table)
                if upstream_id is None or (upstream_id, action_id) not in edge_pairs:
                    rejected += 1  # invariant: column edges must project onto table edges
                    continue
                conn.execute(
                    """INSERT OR REPLACE INTO column_edges
                       (upstream_action, upstream_column, downstream_action,
                        downstream_column, expression)
                       VALUES(?,?,?,?,?)""",
                    (upstream_id, edge.up_column, action_id, edge.down_column, edge.expression),
                )
            if rejected and status == "ok":
                status, reason = "partial", f"inconsistent_edge: {rejected} rejected"
            conn.execute(
                "INSERT OR REPLACE INTO extraction_status(action_id, status, reason) VALUES(?,?,?)",
                (action_id, status, reason),
            )
        indexed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for key, value in (
            ("source_hash", source_hash),
            ("indexed_at", indexed_at),
            ("dataform_version", graph.dataform_version or ""),
        ):
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, value))


def resolve(conn: sqlite3.Connection, name: str) -> int:
    """Resolve a user-supplied name to an action id (rule D6)."""
    name = name.strip()
    lookups = [
        ("canonical = ?", (name,)),
        ("schema || '.' || name = ?", (name,)),
        ("name = ?", (name,)),
        (
            "LOWER(canonical) = LOWER(?) OR LOWER(schema || '.' || name) = LOWER(?) "
            "OR LOWER(name) = LOWER(?)",
            (name, name, name),
        ),
        ("file_name = ?", (name,)),
    ]
    for predicate, params in lookups:
        rows = conn.execute(
            f"SELECT id, canonical FROM actions WHERE {predicate}", params
        ).fetchall()
        if len(rows) == 1:
            return rows[0]["id"]
        if len(rows) > 1:
            raise AmbiguousError(
                f"'{name}' matches {len(rows)} actions",
                candidates=sorted(row["canonical"] for row in rows),
            )
    raise NotFoundError(f"no action matches '{name}'", suggestions=_suggestions(conn, name))


def _suggestions(conn: sqlite3.Connection, name: str) -> list[str]:
    by_short: dict[str, list[str]] = {}
    canonicals: list[str] = []
    for row in conn.execute("SELECT canonical, name FROM actions"):
        canonicals.append(row["canonical"])
        by_short.setdefault(row["name"], []).append(row["canonical"])
    matches = difflib.get_close_matches(name, canonicals + list(by_short), n=5, cutoff=0.5)
    suggestions: list[str] = []
    for match in matches:
        for canonical in by_short.get(match, [match]):
            if canonical not in suggestions:
                suggestions.append(canonical)
    return suggestions[:5]


def get_action(conn: sqlite3.Connection, action_id: int) -> dict:
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"no action with id {action_id}")
    action = dict(row)
    action["tags"] = json.loads(action["tags"])
    action["unique_key"] = json.loads(action["unique_key"])
    action["disabled"] = bool(action["disabled"])
    action["columns"] = [
        dict(col)
        for col in conn.execute(
            "SELECT name, description, data_type FROM columns WHERE action_id = ? ORDER BY name",
            (action_id,),
        )
    ]
    return action


def traverse(
    conn: sqlite3.Connection, action_id: int, direction: str, max_depth: int
) -> list[dict]:
    rows = conn.execute(
        _TRAVERSE_SQL[direction], {"start": action_id, "max_depth": max_depth}
    ).fetchall()
    levels: dict[int, list[dict]] = {}
    for row in rows:
        levels.setdefault(row["depth"], []).append(
            {"canonical": row["canonical"], "type": row["type"], "layer": row["layer"]}
        )
    return [{"depth": depth, "nodes": nodes} for depth, nodes in sorted(levels.items())]


def available_layers(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT layer FROM actions WHERE layer IS NOT NULL ORDER BY layer"
        )
    ]


def tables_by_layer(conn: sqlite3.Connection, layer: str) -> list[dict]:
    layers = available_layers(conn)
    matches = [candidate for candidate in layers if candidate == layer]
    if not matches:
        matches = [candidate for candidate in layers if candidate.endswith(layer)]
    if not matches:
        raise NotFoundError(f"no layer matches '{layer}'", suggestions=layers)
    if len(matches) > 1:
        raise AmbiguousError(f"'{layer}' matches several layers", candidates=matches)
    rows = conn.execute(
        """SELECT canonical, action_type AS type, description, tags
           FROM actions WHERE layer = ? ORDER BY canonical""",
        (matches[0],),
    ).fetchall()
    return [{**dict(row), "tags": json.loads(row["tags"])} for row in rows]


def downstream_closure(conn: sqlite3.Connection, action_id: int) -> list[dict]:
    levels = traverse(conn, action_id, "down", max_depth=1_000_000)
    return [{**node, "depth": level["depth"]} for level in levels for node in level["nodes"]]


def known_columns(conn: sqlite3.Connection, action_id: int) -> list[str]:
    """Documented columns plus every column seen at an edge endpoint of this action."""
    rows = conn.execute(
        """SELECT name FROM columns WHERE action_id = :id
           UNION SELECT downstream_column FROM column_edges WHERE downstream_action = :id
           UNION SELECT upstream_column FROM column_edges WHERE upstream_action = :id
           ORDER BY 1""",
        {"id": action_id},
    )
    return [row[0] for row in rows]


def column_lineage(
    conn: sqlite3.Connection, action_id: int, column: str, direction: str, max_depth: int
) -> dict:
    """BFS over column_edges; returns edges plus the table-level actions visited."""
    queries = {
        "upstream": """SELECT upstream_action AS na, upstream_column AS nc,
                              upstream_action, upstream_column,
                              downstream_action, downstream_column, expression
                       FROM column_edges
                       WHERE downstream_action = ? AND downstream_column = ?""",
        "downstream": """SELECT downstream_action AS na, downstream_column AS nc,
                                upstream_action, upstream_column,
                                downstream_action, downstream_column, expression
                         FROM column_edges
                         WHERE upstream_action = ? AND upstream_column = ?""",
    }
    frontier = {(action_id, column)}
    seen = set(frontier)
    edges: list[dict] = []
    edge_keys: set[tuple] = set()
    for _ in range(max_depth):
        next_frontier: set[tuple[int, str]] = set()
        for node_action, node_column in frontier:
            for row in conn.execute(queries[direction], (node_action, node_column)).fetchall():
                key = (
                    row["upstream_action"],
                    row["upstream_column"],
                    row["downstream_action"],
                    row["downstream_column"],
                )
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append(dict(row))
                neighbor = (row["na"], row["nc"])
                if neighbor not in seen:
                    seen.add(neighbor)
                    next_frontier.add(neighbor)
        if not next_frontier:
            break
        frontier = next_frontier
    canonical_of = dict(
        conn.execute(
            f"SELECT id, canonical FROM actions WHERE id IN "
            f"({','.join('?' * len({a for a, _ in seen}))})",
            sorted({a for a, _ in seen}),
        )
    )
    return {
        "edges": [
            {
                "from": {
                    "table": canonical_of[e["upstream_action"]],
                    "column": e["upstream_column"],
                },
                "to": {
                    "table": canonical_of[e["downstream_action"]],
                    "column": e["downstream_column"],
                },
                "expression": e["expression"],
            }
            for e in edges
        ],
        "visited_action_ids": sorted({a for a, _ in seen}),
    }


def extraction_warnings(
    conn: sqlite3.Connection, action_ids: list[int], direction: str
) -> list[dict]:
    """Non-ok extraction statuses among the given actions and their direction-wise
    table-level neighbors — the opacity boundary of a column traversal."""
    if not action_ids:
        return []
    placeholders = ",".join("?" * len(action_ids))
    neighbor_sql = (
        f"SELECT upstream_id FROM table_edges WHERE downstream_id IN ({placeholders})"
        if direction == "upstream"
        else f"SELECT downstream_id FROM table_edges WHERE upstream_id IN ({placeholders})"
    )
    scope = set(action_ids) | {row[0] for row in conn.execute(neighbor_sql, action_ids)}
    rows = conn.execute(
        f"""SELECT a.canonical, s.status, s.reason
            FROM extraction_status s JOIN actions a ON a.id = s.action_id
            WHERE s.action_id IN ({",".join("?" * len(scope))})
              AND s.status NOT IN ('ok', 'source')
            ORDER BY a.canonical""",
        sorted(scope),
    )
    return [dict(row) for row in rows]


def get_meta(conn: sqlite3.Connection) -> dict:
    meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
    meta["counts"] = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("actions", "table_edges", "column_edges")
    }
    meta["column_extraction"] = dict(
        conn.execute("SELECT status, COUNT(*) FROM extraction_status GROUP BY status")
    )
    return meta
