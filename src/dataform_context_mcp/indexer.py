"""Lazy re-indexing: compile + rebuild when the source content hash changes.

On compile failure the last good index is kept and served, with
compile_status="error" in index_meta — never an empty index (D3).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Callable

from .compile import CompileError, load_graph, run_dataform_compile
from .db import available_layers, get_meta, open_db, rebuild
from .staleness import source_hash

_ERROR_CAP = 2000


def default_db_path(repo: Path) -> Path:
    digest = hashlib.sha256(str(Path(repo).resolve()).encode()).hexdigest()[:12]
    return Path.home() / ".cache" / "dataform-context-mcp" / f"{digest}.db"


def ensure_fresh(
    repo: Path,
    db_path: Path | None = None,
    _compile_fn: Callable[[Path], dict] | None = None,
) -> tuple[sqlite3.Connection, dict]:
    repo = Path(repo)
    compile_fn = _compile_fn or run_dataform_compile
    conn = open_db(db_path or default_db_path(repo))
    current_hash = source_hash(repo)
    stored_hash = get_meta(conn).get("source_hash")
    compile_status, compile_error, stale = "ok", None, False
    if stored_hash != current_hash:
        try:
            graph = load_graph(compile_fn(repo))
            rebuild(conn, graph, source_hash=current_hash)
        except CompileError as err:
            compile_status = "error"
            compile_error = f"{err}\n{err.stderr}"[:_ERROR_CAP]
            stale = True  # index no longer matches the (broken) sources
    meta = get_meta(conn)
    index_meta = {
        "repo": str(repo.resolve()),
        "indexed_at": meta.get("indexed_at"),
        "source_hash": meta.get("source_hash"),
        "stale": stale,
        "compile_status": compile_status,
        "compile_error": compile_error,
        "counts": meta["counts"],
        "column_extraction": meta.get("column_extraction", {}),
        "available_layers": available_layers(conn),
        "dataform_version": meta.get("dataform_version"),
    }
    return conn, index_meta
