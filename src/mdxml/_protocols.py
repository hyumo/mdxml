"""Version-independent views of a Model Description.

These :class:`typing.Protocol` classes describe what FMI 2.0 and FMI 3.0
objects have in common, so code that doesn't care about the FMI Version can be
written (and type-checked) once. The concrete classes in :mod:`mdxml.fmi2` and
:mod:`mdxml.fmi3` satisfy them structurally; they don't inherit from them or
from each other.

Fixed-choice values (``causality``, ``variability``) are typed as ``str``:
each version's enums are ``str`` subclasses, and values outside the allowed
set stay plain strings in lenient mode.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class InterfaceType(Protocol):
    """What FMI 2.0 and FMI 3.0 Model Exchange and Co-Simulation Interface Types share."""

    @property
    def model_identifier(self) -> str:
        """Short name of the FMU's binaries and functions."""
        ...

    @property
    def needs_execution_tool(self) -> bool:
        """Whether the FMU needs its execution tool installed."""
        ...

    @property
    def can_be_instantiated_only_once_per_process(self) -> bool:
        """Whether only one instance per process is allowed."""
        ...

    @property
    def can_get_and_set_fmu_state(self) -> bool:
        """Whether the FMU state can be saved and restored."""
        ...

    @property
    def can_serialize_fmu_state(self) -> bool:
        """Whether the FMU state can be serialized."""
        ...


@runtime_checkable
class ModelHeader(Protocol):
    """What FMI 2.0 and FMI 3.0 Model Headers share.

    FMI 2.0's ``guid`` is available as ``instantiation_token``, its FMI 3.0 name.
    """

    @property
    def fmi_version(self) -> str:
        """The ``fmiVersion`` attribute, as written."""
        ...

    @property
    def model_name(self) -> str:
        """The ``modelName`` attribute."""
        ...

    @property
    def instantiation_token(self) -> str:
        """FMI 3.0's ``instantiationToken``, or FMI 2.0's ``guid``."""
        ...

    @property
    def description(self) -> str | None:
        """The model's description, if any."""
        ...

    @property
    def generation_tool(self) -> str | None:
        """The tool that generated the FMU, if given."""
        ...

    @property
    def generation_date_and_time(self) -> datetime | None:
        """When the FMU was generated, if given."""
        ...

    @property
    def model_exchange(self) -> InterfaceType | None:
        """The Model Exchange Interface Type, if the FMU supports it."""
        ...

    @property
    def co_simulation(self) -> InterfaceType | None:
        """The Co-Simulation Interface Type, if the FMU supports it."""
        ...


@runtime_checkable
class ModelVariable(Protocol):
    """What FMI 2.0 and FMI 3.0 Model Variables share."""

    @property
    def name(self) -> str:
        """The variable's name."""
        ...

    @property
    def value_reference(self) -> int:
        """The variable's value reference."""
        ...

    @property
    def causality(self) -> str:
        """The variable's causality, e.g. ``"output"``."""
        ...

    @property
    def variability(self) -> str:
        """The variable's variability, e.g. ``"continuous"``."""
        ...

    @property
    def description(self) -> str | None:
        """The variable's description, if any."""
        ...

    @property
    def index(self) -> int:
        """The Variable Index: 1-based position in ``ModelVariables``."""
        ...

    @property
    def type_name(self) -> str:
        """The variable's kind: ``"Real"`` in FMI 2.0, ``"Float64"`` in FMI 3.0, and so on."""
        ...
