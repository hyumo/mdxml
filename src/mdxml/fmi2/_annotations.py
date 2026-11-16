"""FMI 2.0 Tool Annotations: ``<Tool name="…">`` elements, kept as raw XML."""

from __future__ import annotations

from dataclasses import dataclass

from mdxml._grammar import Collect, Raw
from mdxml._schema import Frame, attributes, required_text, table


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolAnnotation:
    """A ``<Tool>`` element of ``VendorAnnotations`` or a variable's ``Annotations``.

    ``xml`` is the element's content exactly as written in the file, so it can
    be parsed again by the caller; mdxml doesn't interpret it.
    """

    name: str
    xml: str


TOOL_ATTRS = table(required_text("name", "name"))


def _build_tool(frame: Frame, xml: str, *, strict: bool) -> ToolAnnotation:
    return ToolAnnotation(**attributes(frame, TOOL_ATTRS, strict=strict), xml=xml)


TOOL = Raw(_build_tool)
"""Rule for a ``<Tool>`` element."""

CONTAINER = Collect("Tool")
"""Rule for ``VendorAnnotations`` / ``Annotations``: the tuple of its Tool Annotations."""
