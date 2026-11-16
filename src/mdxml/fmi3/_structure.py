"""The FMI 3.0 Model Structure: outputs, state derivatives, clocked states, initial unknowns and event indicators.

Every entry refers to a Model Variable by value reference, exactly as
written; nothing is resolved (ADR 0002).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from mdxml import _convert as c
from mdxml._grammar import SKIP, Grammar
from mdxml._schema import EMPTY, Attr, Frame, attributes, table


class DependenciesKind(str, Enum):
    """How an unknown depends on one of its ``dependencies``."""

    DEPENDENT = "dependent"
    CONSTANT = "constant"
    FIXED = "fixed"
    TUNABLE = "tunable"
    DISCRETE = "discrete"


@dataclass(frozen=True, slots=True, kw_only=True)
class Unknown:
    """One entry of the Model Structure.

    ``dependencies`` is ``None`` when the attribute is absent, which the
    standard defines as "may depend on all knowns", and ``()`` when it's
    present but empty ("depends on none").
    """

    value_reference: int
    """Value reference of the unknown."""
    dependencies: tuple[int, ...] | None = None
    """Value references of the knowns it depends on."""
    dependencies_kind: tuple[DependenciesKind | str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelStructure:
    """The ``ModelStructure`` element."""

    outputs: tuple[Unknown, ...] = ()
    continuous_state_derivatives: tuple[Unknown, ...] = ()
    clocked_states: tuple[Unknown, ...] = ()
    initial_unknowns: tuple[Unknown, ...] = ()
    event_indicators: tuple[Unknown, ...] = ()


UNKNOWN_ATTRS = table(
    Attr("valueReference", "value_reference", c.UNSIGNED_INT, required=True),
    Attr("dependencies", "dependencies", c.ListOf(c.UNSIGNED_INT)),
    Attr("dependenciesKind", "dependencies_kind", c.ListOf(c.EnumConverter(DependenciesKind))),
)

_ELEMENTS: Mapping[str, str] = MappingProxyType(
    {
        "Output": "outputs",
        "ContinuousStateDerivative": "continuous_state_derivatives",
        "ClockedState": "clocked_states",
        "InitialUnknown": "initial_unknowns",
        "EventIndicator": "event_indicators",
    }
)


def build_unknown(frame: Frame, *, strict: bool) -> Unknown:
    """Build an entry; in strict mode its two lists must have the same length."""
    unknown = Unknown(**attributes(frame, UNKNOWN_ATTRS, strict=strict))
    if strict and unknown.dependencies_kind is not None:
        count = len(unknown.dependencies or ())
        if unknown.dependencies is None or len(unknown.dependencies_kind) != count:
            raise frame.error(
                f"<{frame.tag} valueReference={unknown.value_reference}> has {len(unknown.dependencies_kind)} "
                f"dependenciesKind entries for {count} dependencies"
            )
    return unknown


def build_model_structure(frame: Frame, *, strict: bool) -> ModelStructure:
    """Build the ``ModelStructure`` from its entries, grouped by element in document order."""
    attributes(frame, EMPTY, strict=strict)
    return ModelStructure(**{field: tuple(frame.all(tag)) for tag, field in _ELEMENTS.items()})


STRUCTURE_GRAMMAR = Grammar(
    root="ModelStructure",
    stop_at="",
    build_root=build_model_structure,
    children={
        "ModelStructure": dict.fromkeys(_ELEMENTS, build_unknown),
        **{tag: {"Annotations": SKIP} for tag in _ELEMENTS},
    },
)

AFTER_MODEL_STRUCTURE = frozenset({"Annotations"})
"""Root elements allowed after ``ModelStructure``; skipped."""
