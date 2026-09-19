"""Contracts for the public distribution metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_distribution_metadata_matches_public_identity() -> None:
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["description"] == (
        "Serializable, runtime-neutral contracts for market data, artifacts, strategy "
        "lifecycles, and execution across ML4T libraries."
    )
    assert project["authors"] == [{"name": "Stefan Jansen", "email": "stefan@applied-ai.com"}]
    assert project["maintainers"] == [{"name": "Stefan Jansen", "email": "pm@ml4trading.io"}]
    assert set(project["keywords"]) == {
        "finance",
        "quantitative-finance",
        "algorithmic-trading",
        "trading",
        "market-data",
        "schemas",
        "data-contracts",
        "serialization",
        "backtesting",
        "live-trading",
    }
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["urls"] == {
        "Homepage": "https://www.ml4trading.io/",
        "Documentation": "https://www.ml4trading.io/docs/specs/",
        "Repository": "https://github.com/ml4t/specs",
        "Issues": "https://github.com/ml4t/specs/issues",
        "Changelog": "https://github.com/ml4t/specs/releases",
    }
