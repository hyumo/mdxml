"""Turning parsed objects into data ``json.dumps`` can handle."""

from __future__ import annotations

import dataclasses
import math
from datetime import datetime
from enum import Enum
from typing import Any


def to_dict(obj: Any) -> Any:
    """Convert a parsed mdxml object into plain JSON-ready data.

    Dataclasses become dicts keyed by field name, with ``None`` fields left
    out. Enums become their string value, tuples become lists, datetimes
    become ISO 8601 strings, and infinite or NaN floats become the XSD
    spellings ``"INF"``, ``"-INF"`` and ``"NaN"`` (JSON has no such numbers).
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            field.name: to_dict(value)
            for field in dataclasses.fields(obj)
            if (value := getattr(obj, field.name)) is not None
        }
    if isinstance(obj, Enum):
        return to_dict(obj.value)
    if isinstance(obj, (tuple, list)):
        return [to_dict(item) for item in obj]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float) and not math.isfinite(obj):
        return "NaN" if math.isnan(obj) else ("INF" if obj > 0 else "-INF")
    return obj
