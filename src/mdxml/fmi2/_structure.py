"""The FMI 2.0 Model Structure: outputs, derivatives and initial unknowns, with their dependencies.

Every entry refers to a Model Variable by its Variable Index (1-based
position in ``ModelVariables``), exactly as written; nothing is resolved
(ADR 0002).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mdxml import _convert as c
from mdxml._grammar import Collect, Grammar
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

    index: int
    """Variable Index of the unknown."""
    dependencies: tuple[int, ...] | None = None
    """Variable Indexes of the knowns it depends on."""
    dependencies_kind: tuple[DependenciesKind | str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelStructure:
    """The ``ModelStructure`` element."""

    outputs: tuple[Unknown, ...] = ()
    derivatives: tuple[Unknown, ...] = ()
    initial_unknowns: tuple[Unknown, ...] = ()


UNKNOWN_ATTRS = table(
    Attr("index", "index", c.UNSIGNED_INT, required=True),
    Attr("dependencies", "dependencies", c.ListOf(c.UNSIGNED_INT)),
    Attr("dependenciesKind", "dependencies_kind", c.ListOf(c.EnumConverter(DependenciesKind))),
)


def build_unknown(frame: Frame, *, strict: bool) -> Unknown:
    """Build an ``Unknown``; in strict mode its two lists must have the same length."""
    unknown = Unknown(**attributes(frame, UNKNOWN_ATTRS, strict=strict))
    if strict and unknown.dependencies_kind is not None:
        count = len(unknown.dependencies or ())
        if unknown.dependencies is None or len(unknown.dependencies_kind) != count:
            raise frame.error(
                f"<Unknown index={unknown.index}> has {len(unknown.dependencies_kind)} dependenciesKind entries "
                f"for {count} dependencies"
            )
    return unknown


def build_model_structure(frame: Frame, *, strict: bool) -> ModelStructure:
    """Build the ``ModelStructure`` from its three lists."""
    attributes(frame, EMPTY, strict=strict)
    return ModelStructure(
        outputs=frame.one("Outputs", strict=strict) or (),
        derivatives=frame.one("Derivatives", strict=strict) or (),
        initial_unknowns=frame.one("InitialUnknowns", strict=strict) or (),
    )


STRUCTURE_GRAMMAR = Grammar(
    root="ModelStructure",
    stop_at="",
    build_root=build_model_structure,
    children={
        "ModelStructure": {
            "Outputs": Collect("Unknown"),
            "Derivatives": Collect("Unknown"),
            "InitialUnknowns": Collect("Unknown"),
        },
        "Outputs": {"Unknown": build_unknown},
        "Derivatives": {"Unknown": build_unknown},
        "InitialUnknowns": {"Unknown": build_unknown},
    },
)

AFTER_MODEL_STRUCTURE: frozenset[str] = frozenset()
"""Root elements allowed after ``ModelStructure`` (none in FMI 2)."""
