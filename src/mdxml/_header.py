"""Reading the Model Header: parse up to ``<ModelVariables>`` and stop."""

from __future__ import annotations

from collections.abc import Callable

from mdxml import _reader
from mdxml._errors import UnsupportedFmiVersion
from mdxml._grammar import Grammar, TreeHandler
from mdxml._schema import Frame
from mdxml._source import Source, open_source
from mdxml.fmi2._header import HEADER_GRAMMAR as FMI2_HEADER_GRAMMAR
from mdxml.fmi2._header import HEADER_GRAMMAR_WITH_ANNOTATIONS as FMI2_HEADER_GRAMMAR_WITH_ANNOTATIONS
from mdxml.fmi2._header import ModelHeader as Fmi2ModelHeader
from mdxml.fmi3._header import HEADER_GRAMMAR as FMI3_HEADER_GRAMMAR
from mdxml.fmi3._header import ModelHeader as Fmi3ModelHeader

ROOT = "fmiModelDescription"

AnyModelHeader = Fmi2ModelHeader | Fmi3ModelHeader
"""The Model Header of either FMI Version."""


def header_grammar_chooser(*, annotations: bool) -> Callable[[Frame], Grammar[AnyModelHeader]]:
    """Return a function picking the Model Header grammar for the root element's FMI Version."""
    fmi2_grammar = FMI2_HEADER_GRAMMAR_WITH_ANNOTATIONS if annotations else FMI2_HEADER_GRAMMAR

    def choose(root: Frame) -> Grammar[AnyModelHeader]:
        return _choose_header_grammar(root, fmi2_grammar)

    return choose


def _choose_header_grammar(root: Frame, fmi2_grammar: Grammar[Fmi2ModelHeader]) -> Grammar[AnyModelHeader]:
    if root.tag != ROOT:
        raise root.error(f"root element is <{root.tag}>, expected <{ROOT}>")
    fmi_version = root.attrs.get("fmiVersion")
    if fmi_version is None:
        raise root.error(f"<{ROOT}> has no fmiVersion attribute")
    major = fmi_version.strip().split(".", 1)[0]
    grammar: Grammar[AnyModelHeader]
    if major == "2":
        grammar = fmi2_grammar
    elif major == "3":
        grammar = FMI3_HEADER_GRAMMAR
    else:
        raise UnsupportedFmiVersion(fmi_version)
    return grammar


def read_header(
    src: Source,
    *,
    member: str | None = None,
    strict: bool = False,
    annotations: bool = False,
    max_xml_bytes: int = _reader.DEFAULT_MAX_XML_BYTES,
) -> AnyModelHeader:
    """Read the Model Header of an FMU.

    Returns an :class:`mdxml.fmi2.ModelHeader` or :class:`mdxml.fmi3.ModelHeader`,
    depending on the FMI Version declared in the Model Description.

    ``src`` is a path to a ``.fmu`` zip, an unzipped FMU directory or a
    ``modelDescription.xml`` file; a binary file-like object; or bytes. Zips
    are recognised by their content, not their extension. ``member`` overrides
    where the Model Description lives inside a zip or directory.

    Parsing stops at ``<ModelVariables>``, so the cost doesn't depend on how
    many Model Variables the FMU has.

    By default parsing is lenient (ADR 0003): unknown elements and attributes
    are ignored, booleans may be written in any case, out-of-range enum values
    stay plain strings, and optional values that can't be read are left at
    their default. With ``strict=True`` all of those raise
    :class:`~mdxml.ParseError`, as do missing required attributes.

    With ``annotations=True``, an FMI 2 header's ``vendor_annotations`` holds
    its Tool Annotations as raw XML; otherwise they're skipped and left as
    ``None``. (FMI 3's model-level annotations come after the Model Structure,
    so only :func:`mdxml.read` reaches them.)

    Hostile input raises :class:`~mdxml.UnsafeInput` in both modes: any
    ``DOCTYPE`` or entity declaration, or XML larger than ``max_xml_bytes``
    (256 MB by default; for a zip, the decompressed size counts).
    """
    _reader.check_max_xml_bytes(max_xml_bytes)
    position: list[_reader.Position] = []
    handler = TreeHandler(header_grammar_chooser(annotations=annotations), position, strict=strict)
    with open_source(src, member, max_xml_bytes) as stream:
        _reader.run(stream, handler, position, max_xml_bytes=max_xml_bytes)
    return handler.finish()
