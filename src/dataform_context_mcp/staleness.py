"""Content hash of the Dataform source files that determine the compiled graph.

Content-based (not mtime): git operations touch mtimes without changing content.
Watched set: definitions/**, includes/**, workflow_settings.yaml, dataform.json.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_WATCHED_DIRS = ("definitions", "includes")
_WATCHED_FILES = ("workflow_settings.yaml", "dataform.json")


def source_hash(repo: Path) -> str:
    repo = Path(repo)
    files: list[Path] = []
    for dirname in _WATCHED_DIRS:
        root = repo / dirname
        if root.is_dir():
            files.extend(p for p in root.rglob("*") if p.is_file())
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
