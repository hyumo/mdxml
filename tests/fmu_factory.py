"""Generate large FMUs for performance tests and benchmarks; nothing here is ever committed.

The XML is streamed straight into the zip entry, so generating a model with a
million variables never holds it in memory.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def _fmi2(count: int) -> tuple[str, str, str]:
    header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<fmiModelDescription fmiVersion="2.0" modelName="Big{count}" guid="{{00000000-0000-0000-0000-{count:012d}}}"'
        ' generationTool="mdxml fmu_factory" numberOfEventIndicators="0">\n'
        '  <CoSimulation modelIdentifier="Big" canHandleVariableCommunicationStepSize="true"/>\n'
        '  <UnitDefinitions><Unit name="m"><BaseUnit m="1"/></Unit></UnitDefinitions>\n'
        '  <TypeDefinitions><SimpleType name="Length"><Real unit="m"/></SimpleType></TypeDefinitions>\n'
        '  <LogCategories><Category name="logAll"/></LogCategories>\n'
        '  <DefaultExperiment startTime="0" stopTime="1"/>\n'
        "  <ModelVariables>\n"
    )
    variable = (
        '    <ScalarVariable name="plant.part{i}.x" valueReference="{i}" description="state {i}"'
        ' causality="{causality}" variability="continuous"{initial}>'
        '<Real declaredType="Length" unit="m"{start}/></ScalarVariable>\n'
    )
    footer = "  </ModelVariables>\n  <ModelStructure>\n    <Outputs>\n{outputs}    </Outputs>\n  </ModelStructure>\n"
    return header, variable, footer + "</fmiModelDescription>\n"


def _fmi3(count: int) -> tuple[str, str, str]:
    header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<fmiModelDescription fmiVersion="3.0" modelName="Big{count}"'
        f' instantiationToken="{{00000000-0000-0000-0000-{count:012d}}}" generationTool="mdxml fmu_factory">\n'
        '  <CoSimulation modelIdentifier="Big" canHandleVariableCommunicationStepSize="true"/>\n'
        '  <UnitDefinitions><Unit name="m"><BaseUnit m="1"/></Unit></UnitDefinitions>\n'
        '  <TypeDefinitions><Float64Type name="Length" unit="m"/></TypeDefinitions>\n'
        '  <LogCategories><Category name="logAll"/></LogCategories>\n'
        '  <DefaultExperiment startTime="0" stopTime="1"/>\n'
        "  <ModelVariables>\n"
    )
    variable = (
        '    <Float64 name="plant.part{i}.x" valueReference="{i}" description="state {i}"'
        ' causality="{causality}" variability="continuous" declaredType="Length" unit="m"{initial}{start}/>\n'
    )
    footer = "  </ModelVariables>\n  <ModelStructure>\n{outputs}  </ModelStructure>\n"
    return header, variable, footer + "</fmiModelDescription>\n"


OUTPUT_EVERY = 10
"""Every tenth generated variable is an output, listed in the Model Structure."""

_TIME = {
    2: '    <ScalarVariable name="time" valueReference="{vr}" causality="independent"><Real/></ScalarVariable>\n',
    3: '    <Float64 name="time" valueReference="{vr}" causality="independent"/>\n',
}


def model_description(version: int, count: int, out: io.TextIOBase) -> None:
    """Write a valid Model Description with ``count`` variables to ``out``.

    The first variable is the independent variable ``time`` (FMI 3 requires one);
    the others are numbered from 0, and every tenth of them is an output.
    """
    header, variable, footer = _fmi2(count) if version == 2 else _fmi3(count)
    out.write(header)
    out.write(_TIME[version].format(vr=count))
    outputs: list[str] = []
    for i in range(count - 1):
        output = i % OUTPUT_EVERY == 0
        out.write(
            variable.format(
                i=i,
                causality="output" if output else "local",
                initial=' initial="exact"' if output else "",
                start=f' start="{i}.5"' if output else "",
            )
        )
        if output:
            outputs.append(
                f'      <Unknown index="{i + 2}" dependencies=""/>\n'  # time is Variable Index 1
                if version == 2
                else f'    <Output valueReference="{i}" dependencies=""/>\n'
            )
    out.write(footer.format(outputs="".join(outputs)))


def write_fmu(path: Path, version: int, count: int) -> Path:
    """Write a zipped ``.fmu`` whose Model Description has ``count`` variables."""
    with (
        zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive,
        archive.open("modelDescription.xml", "w", force_zip64=True) as entry,
        io.TextIOWrapper(entry, encoding="utf-8", write_through=False) as text,
    ):
        model_description(version, count, text)
    return path
