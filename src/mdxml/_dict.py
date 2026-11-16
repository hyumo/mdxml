"""Turning parsed objects into data ``json.dumps`` can handle."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any


def to_dict(obj: Any) -> Any:
    """Convert a parsed mdxml object into plain JSON-ready data.

    Dataclasses become dicts keyed by field name, with ``None`` fields left
    out. Enums become their string value, tuples become lists, and datetimes
    become ISO 8601 strings.
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
    return obj
