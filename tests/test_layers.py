"""Layer inference from definition file paths (dynamic, repo-agnostic)."""

import pytest

from dataform_context_mcp.layers import infer_layer


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("definitions/transforms/01_staging/x.sqlx", "01_staging"),
        ("definitions/transforms/03_metrics/y.sqlx", "03_metrics"),
        ("definitions/sources/z.sqlx", "sources"),
        ("definitions/assertions/a.sqlx", "assertions"),
        ("definitions/x.sqlx", None),
        (None, None),
    ],
)
def test_infer_layer(file_name, expected):
    assert infer_layer(file_name) == expected
