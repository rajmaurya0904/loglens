import tomllib
from pathlib import Path


def test_ruff_config_exists():
    """Assert that pyproject.toml contains a [tool.ruff] table."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    assert "tool" in data, "Missing [tool] section in pyproject.toml"
    assert "ruff" in data["tool"], "Missing [tool.ruff] section in pyproject.toml"