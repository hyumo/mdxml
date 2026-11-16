"""Issue #12: the hand-written data model must match the FMI XSDs (ADR 0001).

A small standard-library XSD resolver turns every element of the
``fmiModelDescription`` document into its effective attributes (following
extension, restriction, attribute groups and groups) and child elements. Each
element, identified by ``(parent, element)``, is checked against the attribute
table, dataclass defaults and grammar children that mdxml uses for it:

- the attribute names are exactly the XSD's,
- each attribute is required exactly when the XSD says so,
- each attribute's converter matches its XSD type (including enum values),
- each XSD default is the dataclass field's default, and attributes without
  one default to ``None``,
- the child elements mdxml accepts are exactly the XSD's.

Every element in the XSD must be checked or explicitly excluded with a reason.
"""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast

import pytest

from mdxml import _convert as c
from mdxml import fmi2, fmi3
from mdxml._grammar import Grammar
from mdxml._schema import EMPTY, Attr, AttrTable, table
from mdxml.fmi2 import _annotations as fmi2_annotations
from mdxml.fmi2 import _header as fmi2_header
from mdxml.fmi2 import _structure as fmi2_structure
from mdxml.fmi2 import _variables as fmi2_variables
from mdxml.fmi3 import _annotations as fmi3_annotations
from mdxml.fmi3 import _header as fmi3_header
from mdxml.fmi3 import _structure as fmi3_structure
from mdxml.fmi3 import _variables as fmi3_variables

SCHEMA = Path(__file__).parent.parent / "schema"
XS = "{http://www.w3.org/2001/XMLSchema}"
ROOT = "fmiModelDescription"

# FMI 3 XSDs for other documents in an FMU, not modelDescription.xml.
SEPARATE_FMI3_DOCUMENTS = frozenset(
    {
        "fmi3BuildDescription.xsd",  # buildDescription.xml
        "fmi3TerminalsAndIcons.xsd",  # terminalsAndIcons.xml
        "fmi3Terminal.xsd",  # included only by fmi3TerminalsAndIcons.xsd
        "fmi3LayeredStandardManifest.xsd",  # layered-standard manifests
    }
)

Key = tuple[str, str]
"""An element, identified by its parent element's name and its own name."""


# --- A minimal XSD resolver ------------------------------------------------------------------


@dataclass(frozen=True)
class XsdAttribute:
    name: str
    type: str
    """An XSD type like ``xs:double``, or ``enum``, ``pattern``, ``list:<item type>``."""
    required: bool
    default: str | None
    enum: tuple[str, ...] = ()


@dataclass
class XsdElement:
    attributes: dict[str, XsdAttribute] = field(default_factory=dict[str, XsdAttribute])
    children: dict[str, ET.Element] = field(default_factory=dict[str, ET.Element])


class Schema:
    """The global definitions of a set of XSD files."""

    def __init__(self, files: list[Path]) -> None:
        self.complex_types: dict[str, ET.Element] = {}
        self.attribute_groups: dict[str, ET.Element] = {}
        self.groups: dict[str, ET.Element] = {}
        self.elements: dict[str, ET.Element] = {}
        for path in files:
            for node in ET.parse(path).getroot():
                name = node.get("name", "")
                if node.tag == XS + "complexType":
                    self.complex_types[name] = node
                elif node.tag == XS + "attributeGroup":
                    self.attribute_groups[name] = node
                elif node.tag == XS + "group":
                    self.groups[name] = node
                elif node.tag == XS + "element":
                    self.elements[name] = node

    def resolve(self, declaration: ET.Element) -> XsdElement:
        """Return an element declaration's effective attributes and child elements."""
        out = XsdElement()
        complex_type = self._complex_type_of(declaration)
        if complex_type is not None:
            for node in complex_type:
                self._content(node, out)
        return out

    def _complex_type_of(self, declaration: ET.Element) -> ET.Element | None:
        ref = declaration.get("ref")
        if ref:
            declaration = self.elements[ref]
        inline = declaration.find(XS + "complexType")
        if inline is not None:
            return inline
        type_name = declaration.get("type")
        return self.complex_types.get(type_name) if type_name else None

    def _content(self, node: ET.Element, out: XsdElement) -> None:
        tag = node.tag.removeprefix(XS)
        if tag in {"annotation", "any", "anyAttribute"}:
            return
        handler = {
            "attribute": self._add_attribute,
            "attributeGroup": self._add_attribute_group,
            "group": self._add_group,
            "sequence": self._add_all_children,
            "choice": self._add_all_children,
            "complexContent": self._add_all_children,
            "element": self._add_element,
            "extension": self._add_extension,
            "restriction": self._add_restriction,
        }.get(tag)
        if handler is None:
            raise AssertionError(f"the resolver doesn't handle xs:{tag}")
        handler(node, out)

    def _add_attribute(self, node: ET.Element, out: XsdElement) -> None:
        attribute = self._attribute(node)
        out.attributes[attribute.name] = attribute

    def _add_attribute_group(self, node: ET.Element, out: XsdElement) -> None:
        self._add_all_children(self.attribute_groups[node.get("ref", "")], out)

    def _add_group(self, node: ET.Element, out: XsdElement) -> None:
        self._add_all_children(self.groups[node.get("ref", "")], out)

    def _add_all_children(self, node: ET.Element, out: XsdElement) -> None:
        for child in node:
            self._content(child, out)

    def _add_element(self, node: ET.Element, out: XsdElement) -> None:
        out.children[declared_name(node)] = node

    def _add_extension(self, node: ET.Element, out: XsdElement) -> None:
        base = self.complex_types.get(node.get("base", ""))
        if base is not None:
            self._add_all_children(base, out)
        self._add_all_children(node, out)

    def _add_restriction(self, node: ET.Element, out: XsdElement) -> None:
        # complexContent restriction: attributes are inherited unless redeclared; content is replaced.
        base = self.complex_types.get(node.get("base", ""))
        if base is not None:
            inherited = XsdElement()
            self._add_all_children(base, inherited)
            out.attributes.update(inherited.attributes)
        self._add_all_children(node, out)

    def _attribute(self, node: ET.Element) -> XsdAttribute:
        name = node.get("name", "")
        required = node.get("use") == "required"
        default = node.get("default")
        type_name = node.get("type")
        if type_name is not None:
            return XsdAttribute(name, type_name, required, default)
        simple = node.find(XS + "simpleType")
        assert simple is not None, name
        kind, enum = self._simple_type(simple)
        return XsdAttribute(name, kind, required, default, enum)

    def _simple_type(self, simple: ET.Element) -> tuple[str, tuple[str, ...]]:
        restriction = simple.find(XS + "restriction")
        if restriction is not None:
            enum = tuple(e.get("value", "") for e in restriction.findall(XS + "enumeration"))
            if enum:
                return "enum", enum
            if restriction.find(XS + "pattern") is not None:
                return "pattern", ()
            return restriction.get("base", ""), ()
        item_list = simple.find(XS + "list")
        assert item_list is not None
        item_type = item_list.get("itemType")
        if item_type is not None:
            return f"list:{item_type}", ()
        inner = item_list.find(XS + "simpleType")
        assert inner is not None
        kind, enum = self._simple_type(inner)
        return f"list:{kind}", enum


def declared_name(declaration: ET.Element) -> str:
    """The name an element declaration gives its element, directly or via ``ref``."""
    return declaration.get("name") or declaration.get("ref") or ""


def model_description_files(version: str) -> list[Path]:
    """The XSD files making up modelDescription.xml: the main file and everything it includes."""
    folder = SCHEMA / version
    todo = [folder / f"{version}ModelDescription.xsd"]
    seen: dict[str, Path] = {}
    while todo:
        path = todo.pop()
        if path.name in seen:
            continue
        seen[path.name] = path
        includes = ET.parse(path).getroot().iter(XS + "include")
        todo.extend(folder / include.get("schemaLocation", "") for include in includes)
    return sorted(seen.values())


def walk(schema: Schema) -> dict[Key, XsdElement]:
    """Every element reachable from the root, keyed by ``(parent, element)``."""
    found: dict[Key, XsdElement] = {}
    todo: list[tuple[str, ET.Element]] = [("", schema.elements[ROOT])]
    while todo:
        parent, declaration = todo.pop()
        name = declared_name(declaration)
        if (parent, name) in found:
            continue
        element = schema.resolve(declaration)
        found[(parent, name)] = element
        todo.extend((name, child) for child in element.children.values())
    return found


XSD: dict[str, dict[Key, XsdElement]] = {
    version: walk(Schema(model_description_files(version))) for version in ("fmi2", "fmi3")
}


# --- What mdxml does for each element --------------------------------------------------------


@dataclass(frozen=True)
class Covered:
    attrs: AttrTable
    defaults: Mapping[str, Any]
    """Dataclass field name -> default (``dataclasses.MISSING`` when there's none)."""
    children: frozenset[str]


def defaults_of(cls: type[Any] | None) -> Mapping[str, Any]:
    if cls is None:
        return {}
    return {f.name: f.default for f in dataclasses.fields(cls)}


def children_of(grammar: Grammar[Any] | Mapping[str, Mapping[str, Any]], tag: str) -> frozenset[str]:
    children = grammar.children if isinstance(grammar, Grammar) else grammar
    return frozenset(children.get(tag, {}))


def covered(attrs: AttrTable, cls: type[Any] | None, children: frozenset[str] = frozenset()) -> Covered:
    return Covered(attrs, defaults_of(cls), children)


def fmi2_model() -> dict[Key, Covered]:
    h, v, s = fmi2_header, fmi2_variables, fmi2_structure
    header = h.HEADER_GRAMMAR_WITH_ANNOTATIONS
    variable = v.VARIABLE_GRAMMARS_WITH_ANNOTATIONS["ScalarVariable"]
    tool = covered(fmi2_annotations.TOOL_ATTRS, fmi2.ToolAnnotation)
    model: dict[Key, Covered] = {
        ("", ROOT): covered(
            h.ROOT_ATTRS, fmi2.ModelHeader, children_of(header, ROOT) | {"ModelVariables", "ModelStructure"}
        ),
        (ROOT, "ModelExchange"): covered(
            h.MODEL_EXCHANGE_ATTRS, fmi2.ModelExchange, children_of(header, "ModelExchange")
        ),
        (ROOT, "CoSimulation"): covered(h.CO_SIMULATION_ATTRS, fmi2.CoSimulation, children_of(header, "CoSimulation")),
        ("ModelExchange", "SourceFiles"): covered(EMPTY, None, children_of(header, "SourceFiles")),
        ("CoSimulation", "SourceFiles"): covered(EMPTY, None, children_of(header, "SourceFiles")),
        ("SourceFiles", "File"): covered(h.FILE_ATTRS, None),
        (ROOT, "UnitDefinitions"): covered(EMPTY, None, children_of(header, "UnitDefinitions")),
        ("UnitDefinitions", "Unit"): covered(h.UNIT_ATTRS, fmi2.Unit, children_of(header, "Unit")),
        ("Unit", "BaseUnit"): covered(h.BASE_UNIT_ATTRS, fmi2.BaseUnit),
        ("Unit", "DisplayUnit"): covered(h.DISPLAY_UNIT_ATTRS, fmi2.DisplayUnit),
        (ROOT, "TypeDefinitions"): covered(EMPTY, None, children_of(header, "TypeDefinitions")),
        ("TypeDefinitions", "SimpleType"): covered(
            h.SIMPLE_TYPE_ATTRS, fmi2.RealType, children_of(header, "SimpleType")
        ),
        ("SimpleType", "Real"): covered(h.REAL_ATTRS, fmi2.RealType),
        ("SimpleType", "Integer"): covered(h.INTEGER_ATTRS, fmi2.IntegerType),
        ("SimpleType", "Boolean"): covered(EMPTY, fmi2.BooleanType),
        ("SimpleType", "String"): covered(EMPTY, fmi2.StringType),
        ("SimpleType", "Enumeration"): covered(
            h.ENUMERATION_ATTRS, fmi2.EnumerationType, children_of(header, "Enumeration")
        ),
        ("Enumeration", "Item"): covered(h.ITEM_ATTRS, fmi2.Item),
        (ROOT, "LogCategories"): covered(EMPTY, None, children_of(header, "LogCategories")),
        ("LogCategories", "Category"): covered(h.CATEGORY_ATTRS, fmi2.Category),
        (ROOT, "DefaultExperiment"): covered(h.DEFAULT_EXPERIMENT_ATTRS, fmi2.DefaultExperiment),
        (ROOT, "VendorAnnotations"): covered(EMPTY, None, children_of(header, "VendorAnnotations")),
        ("VendorAnnotations", "Tool"): tool,
        (ROOT, "ModelVariables"): covered(EMPTY, None, frozenset(v.VARIABLE_GRAMMARS)),
        ("ModelVariables", "ScalarVariable"): covered(
            v.SCALAR_VARIABLE_ATTRS, fmi2.RealVariable, children_of(variable, "ScalarVariable")
        ),
        ("ScalarVariable", "Annotations"): covered(EMPTY, None, children_of(variable, "Annotations")),
        ("Annotations", "Tool"): tool,
        (ROOT, "ModelStructure"): covered(EMPTY, None, children_of(s.STRUCTURE_GRAMMAR, "ModelStructure")),
    }
    for tag, (cls, attrs) in v.KINDS.items():
        model[("ScalarVariable", tag)] = covered(attrs, cls)
    for tag in ("Outputs", "Derivatives", "InitialUnknowns"):
        model[("ModelStructure", tag)] = covered(EMPTY, None, children_of(s.STRUCTURE_GRAMMAR, tag))
        model[(tag, "Unknown")] = covered(s.UNKNOWN_ATTRS, fmi2.Unknown)
    return model


# FMI 3 annotations inside these elements are skipped (outside issue #11's scope), so their
# <Annotations> children aren't modelled.
FMI3_SKIPPED_ANNOTATIONS = frozenset(
    {
        "ModelExchange",
        "CoSimulation",
        "ScheduledExecution",
        "Unit",
        "DisplayUnit",
        *fmi3_header.TYPE_DEFINITIONS,
        "Item",
        "Category",
        "DefaultExperiment",
        "Output",
        "ContinuousStateDerivative",
        "ClockedState",
        "InitialUnknown",
        "EventIndicator",
    }
)


def fmi3_model() -> dict[Key, Covered]:
    h, v, s = fmi3_header, fmi3_variables, fmi3_structure
    header = h.HEADER_GRAMMAR
    model: dict[Key, Covered] = {
        ("", ROOT): covered(
            h.ROOT_ATTRS,
            fmi3.ModelHeader,
            children_of(header, ROOT) | {"ModelVariables", "ModelStructure", "Annotations"},
        ),
        (ROOT, "ModelExchange"): covered(
            h.MODEL_EXCHANGE_ATTRS, fmi3.ModelExchange, children_of(header, "ModelExchange")
        ),
        (ROOT, "CoSimulation"): covered(h.CO_SIMULATION_ATTRS, fmi3.CoSimulation, children_of(header, "CoSimulation")),
        (ROOT, "ScheduledExecution"): covered(
            h.SCHEDULED_EXECUTION_ATTRS, fmi3.ScheduledExecution, children_of(header, "ScheduledExecution")
        ),
        (ROOT, "UnitDefinitions"): covered(EMPTY, None, children_of(header, "UnitDefinitions")),
        ("UnitDefinitions", "Unit"): covered(h.UNIT_ATTRS, fmi3.Unit, children_of(header, "Unit")),
        ("Unit", "BaseUnit"): covered(h.BASE_UNIT_ATTRS, fmi3.BaseUnit),
        ("Unit", "DisplayUnit"): covered(h.DISPLAY_UNIT_ATTRS, fmi3.DisplayUnit, children_of(header, "DisplayUnit")),
        (ROOT, "TypeDefinitions"): covered(EMPTY, None, children_of(header, "TypeDefinitions")),
        ("EnumerationType", "Item"): covered(h.ITEM_ATTRS, fmi3.Item, children_of(header, "Item")),
        (ROOT, "LogCategories"): covered(EMPTY, None, children_of(header, "LogCategories")),
        ("LogCategories", "Category"): covered(h.CATEGORY_ATTRS, fmi3.Category, children_of(header, "Category")),
        (ROOT, "DefaultExperiment"): covered(
            h.DEFAULT_EXPERIMENT_ATTRS, fmi3.DefaultExperiment, children_of(header, "DefaultExperiment")
        ),
        (ROOT, "ModelVariables"): covered(EMPTY, None, frozenset(v.VARIABLE_GRAMMARS)),
        (ROOT, "ModelStructure"): covered(EMPTY, None, children_of(s.STRUCTURE_GRAMMAR, "ModelStructure")),
        (ROOT, "Annotations"): covered(
            EMPTY, None, children_of(fmi3_annotations.MODEL_ANNOTATIONS_GRAMMAR, "Annotations")
        ),
        ("Annotations", "Annotation"): covered(fmi3_annotations.ANNOTATION_ATTRS, fmi3.Annotation),
    }
    for tag, (type_cls, type_attrs) in h.TYPE_DEFINITIONS.items():
        model[("TypeDefinitions", tag)] = covered(type_attrs, type_cls, children_of(header, tag))
    for tag, (variable_cls, variable_attrs) in v.VARIABLE_KINDS.items():
        grammar = v.VARIABLE_GRAMMARS_WITH_ANNOTATIONS[tag]
        model[("ModelVariables", tag)] = covered(variable_attrs, variable_cls, children_of(grammar, tag))
        model[(tag, "Alias")] = covered(v.FLOAT_ALIAS_ATTRS if tag.startswith("Float") else v.ALIAS_ATTRS, fmi3.Alias)
        model[(tag, "Annotations")] = covered(EMPTY, None, children_of(grammar, "Annotations"))
        if tag != "Clock":
            model[(tag, "Dimension")] = covered(v.DIMENSION_ATTRS, fmi3.Dimension)
    model[("String", "Start")] = covered(v.STRING_START_ATTRS, None)
    model[("Binary", "Start")] = covered(v.BINARY_START_ATTRS, None)
    for tag in ("Output", "ContinuousStateDerivative", "ClockedState", "InitialUnknown", "EventIndicator"):
        model[("ModelStructure", tag)] = covered(s.UNKNOWN_ATTRS, fmi3.Unknown, children_of(s.STRUCTURE_GRAMMAR, tag))
    return model


MODEL = {"fmi2": fmi2_model(), "fmi3": fmi3_model()}
EXCLUDED: dict[str, dict[Key, str]] = {
    "fmi2": {},
    "fmi3": {(parent, "Annotations"): "annotations here are skipped" for parent in FMI3_SKIPPED_ANNOTATIONS},
}

# Deliberate differences, each with its reason. Keyed by (version, element, attribute).
DEFAULT_EXCEPTIONS: dict[tuple[str, str, str], str] = {
    **{
        ("fmi3", tag, "variability"): "no XSD default; the standard's per-type default is applied when parsing"
        for tag in fmi3_variables.VARIABLE_KINDS
    },
    ("fmi2", "Enumeration", "declaredType"): "required, but the field is on the shared ScalarVariable base",
    ("fmi3", "Enumeration", "declaredType"): "required, but the field is on the shared AbstractVariable base",
}
CONVERTER_EXCEPTIONS: dict[tuple[str, str, str], str] = {
    ("fmi3", ROOT, "fmiVersion"): "an xs:pattern; checked by a dedicated converter in strict mode",
}


# --- The check -------------------------------------------------------------------------------

SIMPLE_CONVERTERS: dict[str, c.Converter[object]] = {
    "xs:string": c.to_text,
    "xs:normalizedString": c.to_text,
    "xs:boolean": c.to_bool,
    "xs:double": c.to_double,
    "xs:float": c.to_double,
    "xs:byte": c.BYTE,
    "xs:unsignedByte": c.UNSIGNED_BYTE,
    "xs:short": c.SHORT,
    "xs:unsignedShort": c.UNSIGNED_SHORT,
    "xs:int": c.INT,
    "xs:unsignedInt": c.UNSIGNED_INT,
    "xs:long": c.LONG,
    "xs:unsignedLong": c.UNSIGNED_LONG,
    "xs:nonNegativeInteger": c.to_unsigned_int,
    "xs:dateTime": c.to_datetime,
    "xs:hexBinary": c.to_hex_binary,
}


def converter_problem(xsd_type: str, enum: tuple[str, ...], converter: object) -> str | None:
    if xsd_type.startswith("list:"):
        if not isinstance(converter, c.ListOf):
            return f"is an xs:list but isn't converted with ListOf ({converter!r})"
        item: object = cast("c.ListOf[object]", converter).item
        return converter_problem(xsd_type.removeprefix("list:"), enum, item)
    if xsd_type == "enum":
        return _enum_problem(enum, converter)
    expected = SIMPLE_CONVERTERS.get(xsd_type)
    if expected is None:
        return f"has XSD type {xsd_type} that the check doesn't know"
    return None if converter is expected else f"is {xsd_type} but converted with {converter!r}"


def _enum_problem(enum: tuple[str, ...], converter: object) -> str | None:
    if not isinstance(converter, c.EnumConverter):
        return f"is an enumeration but isn't converted with EnumConverter ({converter!r})"
    members: type[Enum] = cast("c.EnumConverter[Enum]", converter).enum
    values = {str(member.value) for member in members}
    if values != set(enum):
        return f"enum values differ: XSD {sorted(enum)}, mdxml {sorted(values)}"
    return None


def problems(version: str, key: Key, xsd: XsdElement, model: Covered) -> Iterator[str]:
    """Yield every difference between an XSD element and how mdxml handles it."""
    element = key[1]
    where = f"{version} <{key[0]}/{element}>" if key[0] else f"{version} <{element}>"
    for name in sorted(xsd.attributes.keys() - model.attrs.keys()):
        yield f"{where}: attribute {name!r} is in the XSD but not handled"
    for name in sorted(model.attrs.keys() - xsd.attributes.keys()):
        yield f"{where}: attribute {name!r} is handled but not in the XSD"
    for name in sorted(xsd.attributes.keys() & model.attrs.keys()):
        expected, attr = xsd.attributes[name], model.attrs[name]
        if expected.required != attr.required:
            yield f"{where}: attribute {name!r} required={attr.required}, XSD says {expected.required}"
        if (version, element, name) not in CONVERTER_EXCEPTIONS:
            problem = converter_problem(expected.type, expected.enum, attr.convert)
            if problem:
                yield f"{where}: attribute {name!r} {problem}"
        if model.defaults and (version, element, name) not in DEFAULT_EXCEPTIONS:
            yield from _default_problems(where, name, expected, attr, model.defaults)
    if set(xsd.children) != set(model.children):
        yield f"{where}: children differ: XSD {sorted(xsd.children)}, mdxml {sorted(model.children)}"


def _default_problems(
    where: str, name: str, expected: XsdAttribute, attr: Attr, defaults: Mapping[str, Any]
) -> Iterator[str]:
    if attr.field not in defaults:
        yield f"{where}: attribute {name!r} fills field {attr.field!r}, which the class doesn't have"
        return
    actual = defaults[attr.field]
    if expected.default is not None:
        try:
            wanted = attr.convert(expected.default, strict=True)
        except ValueError as exc:
            yield f"{where}: attribute {name!r} can't convert its XSD default {expected.default!r}: {exc}"
            return
        if actual != wanted:
            yield f"{where}: field {attr.field!r} defaults to {actual!r}, XSD default is {wanted!r}"
    elif expected.required:
        if actual is not dataclasses.MISSING:
            yield f"{where}: field {attr.field!r} has default {actual!r} but the attribute is required"
    elif actual is not None:
        yield f"{where}: field {attr.field!r} defaults to {actual!r}; without an XSD default it should be None"


# --- Tests -----------------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["fmi2", "fmi3"])
def test_every_xsd_element_is_checked_or_excluded(version: str) -> None:
    xsd_keys = set(XSD[version])
    checked, excluded = set(MODEL[version]), set(EXCLUDED[version])
    assert not checked & excluded
    assert xsd_keys - checked - excluded == set(), "XSD elements nobody checks"
    assert (checked | excluded) - xsd_keys == set(), "checked or excluded elements the XSD doesn't have"


@pytest.mark.parametrize("version", ["fmi2", "fmi3"])
def test_the_data_model_matches_the_xsd(version: str) -> None:
    found = [
        problem
        for key, model in sorted(MODEL[version].items())
        for problem in problems(version, key, XSD[version][key], model)
    ]
    assert found == []


def test_the_check_covers_a_lot() -> None:
    counted = {version: sum(len(XSD[version][key].attributes) for key in MODEL[version]) for version in MODEL}
    assert len(MODEL["fmi2"]) >= 35
    assert len(MODEL["fmi3"]) >= 95
    assert counted["fmi2"] >= 100
    assert counted["fmi3"] >= 400


def test_separate_fmi3_documents_are_excluded() -> None:
    included = {path.name for path in model_description_files("fmi3")}
    everything = {path.name for path in (SCHEMA / "fmi3").glob("*.xsd")}
    assert everything - included == SEPARATE_FMI3_DOCUMENTS
    assert {path.name for path in (SCHEMA / "fmi2").glob("*.xsd")} == {p.name for p in model_description_files("fmi2")}


def test_exceptions_are_all_still_needed() -> None:
    attrs = {
        (version, key[1], name)
        for version, elements in XSD.items()
        for key, element in elements.items()
        for name in element.attributes
    }
    assert set(DEFAULT_EXCEPTIONS) <= attrs
    assert set(CONVERTER_EXCEPTIONS) <= attrs


# --- The check catches drift ----------------------------------------------------------------

CO_SIMULATION: Key = (ROOT, "CoSimulation")
SCALAR_VARIABLE: Key = ("ModelVariables", "ScalarVariable")


def drifted(version: str, key: Key, **changes: Any) -> list[str]:
    model = dataclasses.replace(MODEL[version][key], **changes)
    return list(problems(version, key, XSD[version][key], model))


def without(attrs: AttrTable, name: str) -> AttrTable:
    return table(*(attr for xml, attr in attrs.items() if xml != name))


def replaced(attrs: AttrTable, name: str, **changes: Any) -> AttrTable:
    return table(*(dataclasses.replace(attr, **changes) if xml == name else attr for xml, attr in attrs.items()))


def test_a_missing_attribute_is_caught() -> None:
    attrs = without(MODEL["fmi2"][CO_SIMULATION].attrs, "canInterpolateInputs")
    assert drifted("fmi2", CO_SIMULATION, attrs=attrs) == [
        "fmi2 <fmiModelDescription/CoSimulation>: attribute 'canInterpolateInputs' is in the XSD but not handled"
    ]


def test_an_extra_attribute_is_caught() -> None:
    attrs = table(*MODEL["fmi2"][CO_SIMULATION].attrs.values(), Attr("madeUp", "made_up", c.to_bool))
    assert any("'madeUp' is handled but not in the XSD" in p for p in drifted("fmi2", CO_SIMULATION, attrs=attrs))


def test_a_changed_default_is_caught() -> None:
    defaults = {**MODEL["fmi2"][CO_SIMULATION].defaults, "max_output_derivative_order": 1}
    assert drifted("fmi2", CO_SIMULATION, defaults=defaults) == [
        "fmi2 <fmiModelDescription/CoSimulation>: field 'max_output_derivative_order' defaults to 1, XSD default is 0"
    ]


def test_a_removed_field_is_caught() -> None:
    defaults = dict(MODEL["fmi3"][("", ROOT)].defaults)
    del defaults["generation_tool"]
    found = drifted("fmi3", ("", ROOT), defaults=defaults)
    assert found == [
        "fmi3 <fmiModelDescription>: attribute 'generationTool' fills field 'generation_tool', "
        "which the class doesn't have"
    ]


def test_a_required_mismatch_is_caught() -> None:
    attrs = replaced(MODEL["fmi2"][SCALAR_VARIABLE].attrs, "valueReference", required=False)
    assert any(
        "'valueReference' required=False, XSD says True" in p for p in drifted("fmi2", SCALAR_VARIABLE, attrs=attrs)
    )


def test_wrong_enum_values_are_caught() -> None:
    attrs = replaced(MODEL["fmi2"][SCALAR_VARIABLE].attrs, "causality", convert=c.EnumConverter(fmi2.Variability))
    assert any("enum values differ" in p for p in drifted("fmi2", SCALAR_VARIABLE, attrs=attrs))


def test_a_wrong_type_is_caught() -> None:
    attrs = replaced(MODEL["fmi2"][CO_SIMULATION].attrs, "maxOutputDerivativeOrder", convert=c.INT)
    assert any("is xs:unsignedInt but converted with" in p for p in drifted("fmi2", CO_SIMULATION, attrs=attrs))


def test_a_missing_child_element_is_caught() -> None:
    children = MODEL["fmi3"][(ROOT, "ModelVariables")].children - {"Clock"}
    assert any("children differ" in p for p in drifted("fmi3", (ROOT, "ModelVariables"), children=children))
