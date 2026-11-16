"""The complete FMI 3.0 Model Description, as returned by :func:`mdxml.read`."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from mdxml.fmi3._annotations import Annotation
from mdxml.fmi3._header import ModelHeader
from mdxml.fmi3._structure import ModelStructure
from mdxml.fmi3._variables import Variable


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelDescription:
    """An FMI 3.0 Model Description: the Model Header, every Model Variable and the Model Structure.

    References are kept as written (ADR 0002). The ``variable_by_*`` helpers
    look them up; each raises :class:`KeyError` when nothing matches.
    """

    header: ModelHeader
    variables: tuple[Variable, ...] = ()
    model_structure: ModelStructure = field(default_factory=ModelStructure)
    annotations: tuple[Annotation, ...] | None = None
    """The model-level ``<Annotations>``; ``None`` unless read with ``annotations=True``."""

    _by_name: Mapping[str, Variable] = field(init=False, repr=False, compare=False)
    _by_value_reference: Mapping[int, Variable] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Index the variables for lookups; when keys repeat, the first variable in file order wins."""
        by_name: dict[str, Variable] = {}
        by_vr: dict[int, Variable] = {}
        for variable in self.variables:
            by_name.setdefault(variable.name, variable)
            by_vr.setdefault(variable.value_reference, variable)
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))
        object.__setattr__(self, "_by_value_reference", MappingProxyType(by_vr))

    def __reduce__(self) -> tuple[Any, ...]:
        """Pickle only the fields; the lookup indexes are rebuilt when unpickled."""
        fields = {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.init}
        return (_unpickle, (type(self), fields))

    def variable_by_name(self, name: str) -> Variable:
        """Return the variable with this name (aliases aren't included)."""
        return self._by_name[name]

    def variable_by_value_reference(self, value_reference: int) -> Variable:
        """Return the variable with this value reference, as the Model Structure refers to it."""
        return self._by_value_reference[value_reference]


def _unpickle(cls: type[ModelDescription], fields: dict[str, Any]) -> ModelDescription:
    return cls(**fields)
