"""Reading the Model Header: parse up to ``<ModelVariables>`` and stop."""

from __future__ import annotations

from mdxml import _reader
from mdxml._errors import UnsupportedFmiVersion
from mdxml._grammar import Grammar, TreeHandler
from mdxml._schema import Frame
from mdxml._source import Source, open_source
from mdxml.fmi2._header import HEADER_GRAMMAR as FMI2_HEADER_GRAMMAR
from mdxml.fmi2._header import ModelHeader as Fmi2ModelHeader

ROOT = "fmiModelDescription"


def _choose_header_grammar(root: Frame) -> Grammar[Fmi2ModelHeader]:
    if root.tag != ROOT:
        raise root.error(f"root element is <{root.tag}>, expected <{ROOT}>")
    fmi_version = root.attrs.get("fmiVersion")
    if fmi_version is None:
        raise root.error(f"<{ROOT}> has no fmiVersion attribute")
    major = fmi_version.strip().split(".", 1)[0]
    if major == "2":
        return FMI2_HEADER_GRAMMAR
    if major == "3":
        raise UnsupportedFmiVersion(fmi_version, "FMI 3 support is not implemented yet")
    raise UnsupportedFmiVersion(fmi_version)


def read_header(
    src: Source,
    *,
    member: str | None = None,
    strict: bool = False,
    max_xml_bytes: int = _reader.DEFAULT_MAX_XML_BYTES,
) -> Fmi2ModelHeader:
    """Read the Model Header of an FMU.

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

    Hostile input raises :class:`~mdxml.UnsafeInput` in both modes: any
    ``DOCTYPE`` or entity declaration, or XML larger than ``max_xml_bytes``
    (256 MB by default; for a zip, the decompressed size counts).
    """
    _reader.check_max_xml_bytes(max_xml_bytes)
    position: list[_reader.Position] = []
    handler = TreeHandler(_choose_header_grammar, position, strict=strict)
    with open_source(src, member, max_xml_bytes) as stream:
        _reader.run(stream, handler, position, max_xml_bytes=max_xml_bytes)
    return handler.finish()
