"""Infer the pipeline layer of an action from its definition file path.

Layers are discovered dynamically (repo-agnostic): the subdirectory under
definitions/transforms/ (e.g. 01_staging, 03_metrics), else the top-level
directory under definitions/ (sources, assertions, archives...).
"""

from __future__ import annotations

import re

_TRANSFORMS_RE = re.compile(r"(?:^|/)definitions/transforms/([^/]+)/")
_TOP_RE = re.compile(r"(?:^|/)definitions/([^/]+)/")


def infer_layer(file_name: str | None) -> str | None:
    if not file_name:
        return None
    match = _TRANSFORMS_RE.search(file_name)
    if match:
        return match.group(1)
    match = _TOP_RE.search(file_name)
    if match and match.group(1) != "transforms":
        return match.group(1)
    return None
