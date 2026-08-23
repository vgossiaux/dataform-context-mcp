"""Run `dataform compile --json` and load the CompiledGraph into the typed model."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .model import Action, ColumnDoc, CompiledGraphData, Target

_STDERR_CAP = 4000

# enumType of entries in the `tables` array; anything unexpected degrades to "table".
_ENUM_TYPES = {"TABLE": "table", "VIEW": "view", "INCREMENTAL": "incremental"}


class CompileError(Exception):
    def __init__(self, message: str, exit_code: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


def run_dataform_compile(repo: Path, timeout: float = 120.0) -> dict:
    repo = Path(repo)
    if not repo.is_dir():
        raise CompileError(f"repo not found: {repo}", stderr=f"not a directory: {repo}")
    try:
        proc = subprocess.run(
            ["dataform", "compile", "--json"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as err:
        raise CompileError("dataform CLI not found on PATH", stderr=str(err)) from err
    except subprocess.TimeoutExpired as err:
        raise CompileError(f"dataform compile timed out after {timeout}s", stderr=str(err)) from err
    if proc.returncode != 0:
        raise CompileError(
            f"dataform compile failed (exit {proc.returncode})",
            exit_code=proc.returncode,
            stderr=(proc.stderr or proc.stdout)[-_STDERR_CAP:],
        )
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as err:
        raise CompileError("dataform compile produced invalid JSON", stderr=str(err)) from err
    compilation_errors = (raw.get("graphErrors") or {}).get("compilationErrors") or []
    if compilation_errors:
        raise CompileError(
            f"dataform compilation errors ({len(compilation_errors)})",
            stderr=json.dumps(compilation_errors)[:_STDERR_CAP],
        )
    return raw


def load_graph(raw: dict) -> CompiledGraphData:
    actions: list[Action] = []
    for entry in raw.get("tables") or []:
        actions.append(_load_action(entry, _ENUM_TYPES.get(entry.get("enumType", ""), "table")))
    for entry in raw.get("declarations") or []:
        actions.append(_load_action(entry, "declaration"))
    for entry in raw.get("operations") or []:
        actions.append(_load_action(entry, "operations"))
    for entry in raw.get("assertions") or []:
        actions.append(_load_action(entry, "assertion"))
    return CompiledGraphData(actions=actions, dataform_version=raw.get("dataformCoreVersion"))


def _load_target(entry: dict) -> Target:
    return Target(
        database=entry.get("database", ""),
        schema=entry.get("schema", ""),
        name=entry.get("name", ""),
    )


def _load_action(entry: dict, action_type: str) -> Action:
    descriptor = entry.get("actionDescriptor") or {}
    columns = [
        ColumnDoc(name=".".join(col["path"]), description=col.get("description"))
        for col in descriptor.get("columns") or []
        if col.get("path")
    ]
    # operations carry a `queries` array instead of `query`
    query = entry.get("query")
    if not query and entry.get("queries"):
        query = ";\n".join(q for q in entry["queries"] if q)
    return Action(
        target=_load_target(entry.get("target") or {}),
        action_type=action_type,
        file_name=entry.get("fileName"),
        tags=list(entry.get("tags") or []),
        description=descriptor.get("description"),
        columns=columns,
        dependency_targets=[_load_target(t) for t in entry.get("dependencyTargets") or []],
        query=query,
        incremental_query=entry.get("incrementalQuery"),
        unique_key=list(entry.get("uniqueKey") or []),
        disabled=bool(entry.get("disabled", False)),
    )
