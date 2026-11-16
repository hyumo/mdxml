"""The FMI 2.0 Model Header: everything in ``fmiModelDescription`` before ``ModelVariables``.

Classes mirror the FMI 2.0 XSD (``schema/fmi2``): one per element, field
names are the XSD attribute names in snake_case, and defaults are the XSD
defaults. ``SourceFiles/File`` elements, which only carry a name, become a
tuple of file names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, cast

from mdxml import _convert as c
from mdxml._grammar import SKIP, Grammar
from mdxml._lookup import Named
from mdxml._schema import EMPTY, Attr, Frame, attributes, double, flag, required_text, table, text

# --- Enums ----------------------------------------------------------------------------------


class VariableNamingConvention(str, Enum):
    """``variableNamingConvention`` on ``fmiModelDescription``."""

    FLAT = "flat"
    STRUCTURED = "structured"


# --- Interface Types ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelExchange:
    """The ``ModelExchange`` Interface Type."""

    model_identifier: str
    needs_execution_tool: bool = False
    completed_integrator_step_not_needed: bool = False
    can_be_instantiated_only_once_per_process: bool = False
    can_not_use_memory_management_functions: bool = False
    can_get_and_set_fmu_state: bool = False
    can_serialize_fmu_state: bool = False
    provides_directional_derivative: bool = False
    source_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CoSimulation:
    """The ``CoSimulation`` Interface Type."""

    model_identifier: str
    needs_execution_tool: bool = False
    can_handle_variable_communication_step_size: bool = False
    can_interpolate_inputs: bool = False
    max_output_derivative_order: int = 0
    can_run_asynchronuously: bool = False  # sic: the XSD's spelling
    can_be_instantiated_only_once_per_process: bool = False
    can_not_use_memory_management_functions: bool = False
    can_get_and_set_fmu_state: bool = False
    can_serialize_fmu_state: bool = False
    provides_directional_derivative: bool = False
    source_files: tuple[str, ...] = ()


# --- Units ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseUnit:
    """A unit's exponents of the SI base units, plus ``factor`` and ``offset`` to convert to them.

    Field names keep the XSD's case-sensitive SI symbols (``A`` is ampere, ``K`` is kelvin).
    """

    kg: int = 0
    m: int = 0
    s: int = 0
    A: int = 0
    K: int = 0
    mol: int = 0
    cd: int = 0
    rad: int = 0
    factor: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class DisplayUnit:
    """A unit to display values in, converted from the unit by ``factor`` and ``offset``."""

    name: str
    factor: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class Unit:
    """A ``Unit`` in ``UnitDefinitions``."""

    name: str
    base_unit: BaseUnit | None = None
    display_units: tuple[DisplayUnit, ...] = ()


# --- Type definitions -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class RealType:
    """A ``SimpleType`` with a ``Real`` element."""

    name: str
    description: str | None = None
    quantity: str | None = None
    unit: str | None = None
    display_unit: str | None = None
    relative_quantity: bool = False
    min: float | None = None
    max: float | None = None
    nominal: float | None = None
    unbounded: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class IntegerType:
    """A ``SimpleType`` with an ``Integer`` element."""

    name: str
    description: str | None = None
    quantity: str | None = None
    min: int | None = None
    max: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BooleanType:
    """A ``SimpleType`` with a ``Boolean`` element."""

    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StringType:
    """A ``SimpleType`` with a ``String`` element."""

    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Item:
    """One allowed value of an ``Enumeration`` type."""

    name: str
    value: int
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EnumerationType:
    """A ``SimpleType`` with an ``Enumeration`` element."""

    name: str
    description: str | None = None
    quantity: str | None = None
    items: tuple[Item, ...] = ()


TypeDefinition = RealType | IntegerType | BooleanType | StringType | EnumerationType
"""Any ``SimpleType`` in ``TypeDefinitions``."""


# --- Log categories and default experiment --------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Category:
    """A log category in ``LogCategories``."""

    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DefaultExperiment:
    """Default simulation settings suggested by the FMU."""

    start_time: float | None = None
    stop_time: float | None = None
    tolerance: float | None = None
    step_size: float | None = None


# --- Model Header ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelHeader:
    """Everything in an FMI 2.0 Model Description before ``ModelVariables``.

    Annotations (``VendorAnnotations``) aren't part of the Model Header.
    """

    fmi_version: str
    model_name: str
    guid: str
    description: str | None = None
    author: str | None = None
    version: str | None = None
    copyright: str | None = None
    license: str | None = None
    generation_tool: str | None = None
    generation_date_and_time: datetime | None = None
    variable_naming_convention: VariableNamingConvention | str = VariableNamingConvention.FLAT
    number_of_event_indicators: int | None = None
    model_exchange: ModelExchange | None = None
    co_simulation: CoSimulation | None = None
    unit_definitions: Named[Unit] = field(default_factory=Named)
    type_definitions: Named[TypeDefinition] = field(default_factory=Named)
    log_categories: Named[Category] = field(default_factory=Named)
    default_experiment: DefaultExperiment | None = None

    @property
    def instantiation_token(self) -> str:
        """The ``guid``, under its FMI 3.0 name, so version-independent code can use one name."""
        return self.guid

    def __post_init__(self) -> None:
        """Accept plain tuples for the definition lists, so headers can be built by hand."""
        for name in ("unit_definitions", "type_definitions", "log_categories"):
            value = getattr(self, name)
            if not isinstance(value, Named):
                object.__setattr__(self, name, Named(value))


# --- Attribute tables -----------------------------------------------------------------------


def _int(xml: str, field: str) -> Attr:
    return Attr(xml, field, c.INT)


ROOT_ATTRS = table(
    required_text("fmiVersion", "fmi_version"),
    required_text("modelName", "model_name"),
    required_text("guid", "guid"),
    text("description", "description"),
    text("author", "author"),
    text("version", "version"),
    text("copyright", "copyright"),
    text("license", "license"),
    text("generationTool", "generation_tool"),
    Attr("generationDateAndTime", "generation_date_and_time", c.to_datetime),
    Attr("variableNamingConvention", "variable_naming_convention", c.EnumConverter(VariableNamingConvention)),
    Attr("numberOfEventIndicators", "number_of_event_indicators", c.UNSIGNED_INT),
)

_COMMON_INTERFACE_ATTRS = (
    required_text("modelIdentifier", "model_identifier"),
    flag("needsExecutionTool", "needs_execution_tool"),
    flag("canBeInstantiatedOnlyOncePerProcess", "can_be_instantiated_only_once_per_process"),
    flag("canNotUseMemoryManagementFunctions", "can_not_use_memory_management_functions"),
    flag("canGetAndSetFMUstate", "can_get_and_set_fmu_state"),
    flag("canSerializeFMUstate", "can_serialize_fmu_state"),
    flag("providesDirectionalDerivative", "provides_directional_derivative"),
)

MODEL_EXCHANGE_ATTRS = table(
    *_COMMON_INTERFACE_ATTRS,
    flag("completedIntegratorStepNotNeeded", "completed_integrator_step_not_needed"),
)

CO_SIMULATION_ATTRS = table(
    *_COMMON_INTERFACE_ATTRS,
    flag("canHandleVariableCommunicationStepSize", "can_handle_variable_communication_step_size"),
    flag("canInterpolateInputs", "can_interpolate_inputs"),
    Attr("maxOutputDerivativeOrder", "max_output_derivative_order", c.UNSIGNED_INT),
    flag("canRunAsynchronuously", "can_run_asynchronuously"),
)

FILE_ATTRS = table(required_text("name", "name"))

UNIT_ATTRS = table(required_text("name", "name"))

BASE_UNIT_ATTRS = table(
    *(_int(symbol, symbol) for symbol in ("kg", "m", "s", "A", "K", "mol", "cd", "rad")),
    double("factor", "factor"),
    double("offset", "offset"),
)

DISPLAY_UNIT_ATTRS = table(
    required_text("name", "name"),
    double("factor", "factor"),
    double("offset", "offset"),
)

SIMPLE_TYPE_ATTRS = table(
    required_text("name", "name"),
    text("description", "description"),
)

REAL_ATTRS = table(
    text("quantity", "quantity"),
    text("unit", "unit"),
    text("displayUnit", "display_unit"),
    flag("relativeQuantity", "relative_quantity"),
    double("min", "min"),
    double("max", "max"),
    double("nominal", "nominal"),
    flag("unbounded", "unbounded"),
)

INTEGER_ATTRS = table(
    text("quantity", "quantity"),
    _int("min", "min"),
    _int("max", "max"),
)

ENUMERATION_ATTRS = table(text("quantity", "quantity"))

ITEM_ATTRS = table(
    required_text("name", "name"),
    Attr("value", "value", c.INT, required=True),
    text("description", "description"),
)

CATEGORY_ATTRS = table(
    required_text("name", "name"),
    text("description", "description"),
)

DEFAULT_EXPERIMENT_ATTRS = table(
    double("startTime", "start_time"),
    double("stopTime", "stop_time"),
    double("tolerance", "tolerance"),
    double("stepSize", "step_size"),
)


# --- Builders -------------------------------------------------------------------------------


def _source_files(frame: Frame, *, strict: bool) -> tuple[str, ...]:
    files = frame.one("SourceFiles", strict=strict)
    return tuple(files) if files else ()


def _build_model_exchange(frame: Frame, *, strict: bool) -> ModelExchange:
    return ModelExchange(
        **attributes(frame, MODEL_EXCHANGE_ATTRS, strict=strict), source_files=_source_files(frame, strict=strict)
    )


def _build_co_simulation(frame: Frame, *, strict: bool) -> CoSimulation:
    return CoSimulation(
        **attributes(frame, CO_SIMULATION_ATTRS, strict=strict), source_files=_source_files(frame, strict=strict)
    )


def _build_source_files(frame: Frame, *, strict: bool) -> tuple[str, ...]:
    attributes(frame, EMPTY, strict=strict)
    return tuple(frame.all("File"))


def _build_file(frame: Frame, *, strict: bool) -> str:
    name: str = attributes(frame, FILE_ATTRS, strict=strict)["name"]
    return name


def _build_unit(frame: Frame, *, strict: bool) -> Unit:
    return Unit(
        **attributes(frame, UNIT_ATTRS, strict=strict),
        base_unit=frame.one("BaseUnit", strict=strict),
        display_units=tuple(frame.all("DisplayUnit")),
    )


def _build_base_unit(frame: Frame, *, strict: bool) -> BaseUnit:
    return BaseUnit(**attributes(frame, BASE_UNIT_ATTRS, strict=strict))


def _build_display_unit(frame: Frame, *, strict: bool) -> DisplayUnit:
    return DisplayUnit(**attributes(frame, DISPLAY_UNIT_ATTRS, strict=strict))


def _build_simple_type(frame: Frame, *, strict: bool) -> TypeDefinition:
    common = attributes(frame, SIMPLE_TYPE_ATTRS, strict=strict)
    kinds = [(tag, obj) for tag, obj in frame.children if tag in _TYPE_KINDS]
    if not kinds:
        raise frame.error(f"<SimpleType name={common['name']!r}> has no Real, Integer, Boolean, String or Enumeration")
    if len(kinds) > 1 and strict:
        raise frame.error(f"<SimpleType name={common['name']!r}> has {len(kinds)} type elements, expected one")
    tag, kind_fields = kinds[0]
    return _TYPE_KINDS[tag](**common, **cast("dict[str, Any]", kind_fields))


def _build_real(frame: Frame, *, strict: bool) -> dict[str, object]:
    return attributes(frame, REAL_ATTRS, strict=strict)


def _build_integer(frame: Frame, *, strict: bool) -> dict[str, object]:
    return attributes(frame, INTEGER_ATTRS, strict=strict)


def _build_no_attributes(frame: Frame, *, strict: bool) -> dict[str, object]:
    return attributes(frame, EMPTY, strict=strict)


def _build_enumeration(frame: Frame, *, strict: bool) -> dict[str, object]:
    return {**attributes(frame, ENUMERATION_ATTRS, strict=strict), "items": tuple(frame.all("Item"))}


def _build_item(frame: Frame, *, strict: bool) -> Item:
    return Item(**attributes(frame, ITEM_ATTRS, strict=strict))


def _build_category(frame: Frame, *, strict: bool) -> Category:
    return Category(**attributes(frame, CATEGORY_ATTRS, strict=strict))


def _build_default_experiment(frame: Frame, *, strict: bool) -> DefaultExperiment:
    return DefaultExperiment(**attributes(frame, DEFAULT_EXPERIMENT_ATTRS, strict=strict))


def _build_unit_definitions(frame: Frame, *, strict: bool) -> tuple[Unit, ...]:
    attributes(frame, EMPTY, strict=strict)
    return tuple(frame.all("Unit"))


def _build_type_definitions(frame: Frame, *, strict: bool) -> tuple[TypeDefinition, ...]:
    attributes(frame, EMPTY, strict=strict)
    return tuple(frame.all("SimpleType"))


def _build_log_categories(frame: Frame, *, strict: bool) -> tuple[Category, ...]:
    attributes(frame, EMPTY, strict=strict)
    return tuple(frame.all("Category"))


def build_header(frame: Frame, *, strict: bool) -> ModelHeader:
    """Build the :class:`ModelHeader` from the root element and the children read so far."""
    units = frame.one("UnitDefinitions", strict=strict)
    types = frame.one("TypeDefinitions", strict=strict)
    categories = frame.one("LogCategories", strict=strict)
    return ModelHeader(
        **attributes(frame, ROOT_ATTRS, strict=strict),
        model_exchange=frame.one("ModelExchange", strict=strict),
        co_simulation=frame.one("CoSimulation", strict=strict),
        unit_definitions=Named(units or ()),
        type_definitions=Named(types or ()),
        log_categories=Named(categories or ()),
        default_experiment=frame.one("DefaultExperiment", strict=strict),
    )


_TYPE_KINDS: Mapping[str, type[TypeDefinition]] = MappingProxyType(
    {
        "Real": RealType,
        "Integer": IntegerType,
        "Boolean": BooleanType,
        "String": StringType,
        "Enumeration": EnumerationType,
    }
)

HEADER_GRAMMAR = Grammar(
    root="fmiModelDescription",
    stop_at="ModelVariables",
    build_root=build_header,
    children={
        "fmiModelDescription": {
            "ModelExchange": _build_model_exchange,
            "CoSimulation": _build_co_simulation,
            "UnitDefinitions": _build_unit_definitions,
            "TypeDefinitions": _build_type_definitions,
            "LogCategories": _build_log_categories,
            "DefaultExperiment": _build_default_experiment,
            "VendorAnnotations": SKIP,
        },
        "ModelExchange": {"SourceFiles": _build_source_files},
        "CoSimulation": {"SourceFiles": _build_source_files},
        "SourceFiles": {"File": _build_file},
        "UnitDefinitions": {"Unit": _build_unit},
        "Unit": {"BaseUnit": _build_base_unit, "DisplayUnit": _build_display_unit},
        "TypeDefinitions": {"SimpleType": _build_simple_type},
        "SimpleType": {
            "Real": _build_real,
            "Integer": _build_integer,
            "Boolean": _build_no_attributes,
            "String": _build_no_attributes,
            "Enumeration": _build_enumeration,
        },
        "Enumeration": {"Item": _build_item},
        "LogCategories": {"Category": _build_category},
    },
)
