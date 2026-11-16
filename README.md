# mdxml

Fast, zero-dependency reader for the `modelDescription.xml` of FMI 2.0 and FMI 3.0 FMUs.

- **Read only what you need.** `read_header()` stops at `<ModelVariables>`, so it costs the same for 10 variables or 10 million. `iter_variables()` streams variables one at a time; `read()` loads everything.
- **Flat memory.** Streaming never holds the XML or more than one 64 KB chunk of it, however big the FMU is. That makes it safe to run on uploaded files in web backends, in parallel.
- **Safe on hostile input.** No `DOCTYPE`, no entities, no external resources, a size limit, and zip bombs are refused before they're decompressed.
- **Faithful, typed results.** Frozen dataclasses mirror the FMI XSDs field for field, with real Python types, the XSD's defaults and enums. They're fully type-hinted (`py.typed`).
- **Zero dependencies.** Pure standard library (`xml.parsers.expat`, `zipfile`). Python 3.10+ on any OS.

## Installation

```sh
pip install mdxml
```

## Usage

### The Model Header

```python
import mdxml

header = mdxml.read_header("BouncingBall.fmu")
print(header.model_name, header.fmi_version)  # BouncingBall 3.0
print(header.co_simulation.model_identifier)  # BouncingBall
print(header.unit_definitions["m/s"].base_unit)  # look definitions up by name
print(header.default_experiment.stop_time)  # 3.0
```

The Model Header is everything before `<ModelVariables>`: the root attributes, the interface types (Model Exchange, Co-Simulation, Scheduled Execution), units, type definitions, log categories and the default experiment. Parsing stops there, so the rest of the file is never read.

### Streaming Model Variables

```python
import mdxml

with mdxml.iter_variables("BouncingBall.fmu", causality="output") as variables:
    print(variables.header.model_name)  # the header comes from the same pass
    for variable in variables:
        print(variable.index, variable.name, variable.type_name, variable.start)
```

`causality=`, `variability=` (one value or several) and `name_prefix=` filter variables before they're built, so skipped variables cost almost nothing. Each variable keeps its Variable Index (its 1-based position in `ModelVariables`) even when others are filtered out. `effective_initial` gives the standard's default `initial` when the file doesn't set one.

### The whole Model Description

```python
import mdxml

md = mdxml.read("BouncingBall.fmu")
derivative = md.model_structure.continuous_state_derivatives[0]
print(md.variable_by_value_reference(derivative.value_reference).name)  # der(h)
```

`read()` returns the header, every variable and the Model Structure from one pass. References are kept exactly as written; the `variable_by_name`, `variable_by_value_reference` and, for FMI 2, `variable_by_index` helpers look them up.

### Inputs

Every entry point accepts:

- a path to a `.fmu` file (recognised by its content, not its extension),
- a path to an unzipped FMU directory,
- a path to a `modelDescription.xml` file,
- a binary file-like object, such as an upload in a web framework (zipped input needs a seekable one),
- `bytes`.

```python
import io

import mdxml

with open("BouncingBall.fmu", "rb") as upload:
    data = upload.read()

assert mdxml.read_header(io.BytesIO(data)) == mdxml.read_header(data)
```

Zips are read in place, and nothing is extracted to disk. Use `member=` for an FMU whose Model Description isn't at the standard `modelDescription.xml`.

### FMI 2 and FMI 3

Results are version-specific types (`mdxml.fmi2.*` or `mdxml.fmi3.*`) that mirror their XSD. Code that doesn't care about the version can use the shared Protocols, which both versions' classes satisfy:

```python
import mdxml


def describe(header: mdxml.ModelHeader, variable: mdxml.ModelVariable) -> str:
    return f"{header.model_name} ({header.instantiation_token}): {variable.name} is a {variable.causality}"


variables = mdxml.iter_variables("BouncingBall.fmu")
print(describe(variables.header, next(variables)))
```

FMI 2's `guid` is also available as `instantiation_token`. To use version-specific fields, check the type first, e.g. `isinstance(header, mdxml.fmi2.ModelHeader)`.

### Lenient by default, strict when asked

Real-world FMUs often bend the schema a little, so by default unknown elements and attributes are ignored, booleans may be written in any case, unknown enum values stay plain strings, and optional values that can't be read keep their default. With `strict=True`, all of those raise `mdxml.ParseError` (with line and column), as do missing required attributes.

```python
import mdxml

mdxml.read("BouncingBall.fmu", strict=True)
```

### Annotations

Tool annotations are skipped by default at no cost. With `annotations=True`, they're kept as their exact raw XML (`fmi2.ToolAnnotation(name, xml)`, `fmi3.Annotation(type, xml)`) for you to parse:

```python
import mdxml

md = mdxml.read("BouncingBall.fmu", annotations=True)
print(md.annotations)  # model-level annotations (FMI 3); () when there are none
print(md.variables[0].annotations)
```

### JSON

```python
import json

import mdxml

print(json.dumps(mdxml.to_dict(mdxml.read_header("BouncingBall.fmu")), indent=2))
```

`to_dict()` turns any result into JSON-ready data: enums become strings, `bytes` become hex, and infinities and NaN become `"INF"`, `"-INF"` and `"NaN"`.

### Concurrency

There's no shared state, and every result is immutable and picklable, so mdxml works from threads, process pools and free-threaded Python builds alike.

## Command line

```sh
mdxml header BouncingBall.fmu                        # the Model Header as JSON
mdxml variables BouncingBall.fmu --causality output  # one JSON object per variable
mdxml variables model.fmu --name-prefix plant. --variability continuous --strict
```

Both commands take `--member`, `--strict`, `--annotations` and `--max-xml-bytes`. `python -m mdxml` works too.

## Safety defaults

These checks are always on, in lenient and strict mode alike:

- **No `DOCTYPE` or entity declarations.** They're refused at the first token, which blocks entity bombs (billion laughs) and external entities (XXE). Model Descriptions never need them.
- **A size limit.** `max_xml_bytes` defaults to 256 MB and can be changed per call. For zips it counts the *decompressed* size, and a zip entry claiming to be bigger is refused before it's opened.
- **Only the Model Description is read.** No other archive member is ever opened.

All three raise `mdxml.UnsafeInput`. Every error mdxml raises on purpose is an `mdxml.MdxmlError`.

## Performance

Against FMPy 0.3.32 on generated FMUs with a million variables (see [benchmarks/RESULTS.md](benchmarks/RESULTS.md)):

| 1M variables | `iter_variables` | `read` | FMPy `read_model_description` |
|---|---|---|---|
| FMI 2 | 8.1 s · < 1 MB | 10.2 s · 586 MB | 12.3 s · 3,177 MB (10.8 s without validation) |
| FMI 3 | 7.1 s · < 1 MB | 8.8 s · 555 MB | 11.1 s · 3,055 MB (9.4 s without validation) |

`read_header` takes about 0.5 ms at any size.

## Supported versions

- FMI 2.0 (schema v2.0.5) and FMI 3.0 (schema v3.0.2). FMI 1.0 raises `mdxml.UnsupportedFmiVersion`.
- Only `modelDescription.xml`. FMI 3's other XML files (build description, terminals and icons, layered-standard manifests) aren't read.
- Python 3.10 to 3.14 on Linux, macOS and Windows.

## License

MIT. The FMI XSDs in `schema/`, which are used only by the tests, are © Modelica Association Project "FMI" under the 2-Clause BSD license, and aren't part of the installed package.
