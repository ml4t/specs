"""Shared artifact and schema specifications for ML4T libraries."""

from .base import (
    ArtifactKind,
    ArtifactProvenance,
    ArtifactSpec,
    ArtifactStorage,
    optional_str,
    serialize_artifact_value,
)
from .io import read_spec_payload, write_spec_payload
from .market_data import (
    FeedSpec,
    MarketDataSchema,
    MarketDataSemantics,
    MarketDataSpec,
    TimestampSemantics,
)

__version__ = "0.1.0b0"

__all__ = [
    "ArtifactKind",
    "ArtifactProvenance",
    "ArtifactSpec",
    "ArtifactStorage",
    "FeedSpec",
    "MarketDataSchema",
    "MarketDataSemantics",
    "MarketDataSpec",
    "TimestampSemantics",
    "optional_str",
    "read_spec_payload",
    "serialize_artifact_value",
    "write_spec_payload",
]
