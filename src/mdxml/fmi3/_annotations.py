"""FMI 3.0 annotations: ``<Annotation type="…">`` elements, kept as raw XML."""

from __future__ import annotations

from dataclasses import dataclass

from mdxml._grammar import Collect, Grammar, Raw
from mdxml._schema import Frame, attributes, required_text, table


@dataclass(frozen=True, slots=True, kw_only=True)
class Annotation:
    """An ``<Annotation>`` element of an ``Annotations`` list.

    ``type`` identifies the tool or extension the annotation is for. ``xml`` is
    the element's content (elements and text) exactly as written in the file, so
    it can be parsed again by the caller; mdxml doesn't interpret it.
    """

    type: str
    xml: str


ANNOTATION_ATTRS = table(required_text("type", "type"))


def _build_annotation(frame: Frame, xml: str, *, strict: bool) -> Annotation:
    return Annotation(**attributes(frame, ANNOTATION_ATTRS, strict=strict), xml=xml)


ANNOTATION = Raw(_build_annotation)
"""Rule for an ``<Annotation>`` element."""

CONTAINER = Collect("Annotation")
"""Rule for an ``Annotations`` element: the tuple of its annotations."""

MODEL_ANNOTATIONS_GRAMMAR = Grammar(
    root="Annotations",
    stop_at="",
    build_root=CONTAINER,
    children={"Annotations": {"Annotation": ANNOTATION}},
)
"""Grammar for the model-level ``<Annotations>`` after ``<ModelStructure>``."""
