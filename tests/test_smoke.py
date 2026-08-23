"""Smoke tests: package imports and the console script answers --help."""

import subprocess


def test_package_imports():
    import dataform_context_mcp

    assert dataform_context_mcp.__version__


def test_cli_help_exits_zero():
    result = subprocess.run(
        ["uv", "run", "dataform-context", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert "index" in result.stdout
