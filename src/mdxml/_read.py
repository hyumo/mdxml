"""Reading a whole Model Description into memory."""

from __future__ import annotations

from typing import cast

from mdxml import _reader
from mdxml._errors import ParseError
from mdxml._source import Source
from mdxml._variables import VariableFilter, VariableIterator
from mdxml.fmi2._header import ModelHeader as Fmi2ModelHeader
from mdxml.fmi2._model import ModelDescription as Fmi2ModelDescription
from mdxml.fmi2._structure import ModelStructure as Fmi2ModelStructure
from mdxml.fmi2._variables import Variable as Fmi2Variable
from mdxml.fmi3._header import ModelHeader as Fmi3ModelHeader
from mdxml.fmi3._model import ModelDescription as Fmi3ModelDescription
from mdxml.fmi3._structure import ModelStructure as Fmi3ModelStructure
from mdxml.fmi3._variables import Variable as Fmi3Variable

AnyModelDescription = Fmi2ModelDescription | Fmi3ModelDescription
"""The Model Description of either FMI Version."""


def read(
    src: Source,
    *,
    member: str | None = None,
    strict: bool = False,
    max_xml_bytes: int = _reader.DEFAULT_MAX_XML_BYTES,
) -> AnyModelDescription:
    """Read an FMU's whole Model Description: Model Header, Model Variables and Model Structure.

    ``src``, ``member``, ``strict`` and ``max_xml_bytes`` work as for
    :func:`mdxml.read_header`. The document is read in one streaming pass and
    only the parsed objects are kept, never the XML. Annotations are skipped.

    Returns an :class:`mdxml.fmi2.ModelDescription` or
    :class:`mdxml.fmi3.ModelDescription`, depending on the FMI Version.
    """
    _reader.check_max_xml_bytes(max_xml_bytes)
    no_filter = VariableFilter(causality=None, variability=None, name_prefix=None)
    iterator = VariableIterator(
        src, member=member, strict=strict, max_xml_bytes=max_xml_bytes, variable_filter=no_filter, read_structure=True
    )
    with iterator:
        variables = tuple(iterator)
    header = iterator.header
    structure = iterator.model_structure
    if structure is None and strict:
        raise ParseError("<fmiModelDescription> has no <ModelStructure> element")

    if isinstance(header, Fmi2ModelHeader):
        return Fmi2ModelDescription(
            header=header,
            variables=cast("tuple[Fmi2Variable, ...]", variables),
            model_structure=structure or Fmi2ModelStructure(),
        )
    assert isinstance(header, Fmi3ModelHeader)  # noqa: S101 - read_header only returns these two
    return Fmi3ModelDescription(
        header=header,
        variables=cast("tuple[Fmi3Variable, ...]", variables),
        model_structure=structure or Fmi3ModelStructure(),
    )
