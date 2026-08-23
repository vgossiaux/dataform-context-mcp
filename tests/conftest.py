"""Shared fixtures: compiled fixture graph, typed model, anyio backend."""

import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MINI_REPO = FIXTURES / "mini_repo"

requires_dataform = pytest.mark.skipif(
    shutil.which("dataform") is None, reason="dataform CLI not installed"
)


@pytest.fixture(scope="session")
def raw_graph() -> dict:
    return json.loads((FIXTURES / "compiled_graph.json").read_text())


@pytest.fixture(scope="session")
def graph(raw_graph):
    from dataform_context_mcp.compile import load_graph

    return load_graph(raw_graph)


@pytest.fixture
def anyio_backend():
    return "asyncio"
