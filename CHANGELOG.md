# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, the public API may change
between minor versions.

## [Unreleased]

### Added

- `mdxml.read_header(path)` reads the root attributes of an FMI 2.0 Model
  Header from a `modelDescription.xml` file, streaming with expat and stopping
  at `<ModelVariables>`.
- `read_header` returns the full FMI 2.0 Model Header: Interface Types
  (`ModelExchange`, `CoSimulation`) with their source files, unit definitions,
  type definitions, log categories and the default experiment, with XSD
  defaults applied. Vendor annotations are skipped.
- `annotations=True` on `read_header`, `iter_variables` and `read` (CLI:
  `--annotations`) keeps Tool Annotations as their exact raw XML instead of
  skipping them: `fmi2.ToolAnnotation(name, xml)` for FMI 2
  `VendorAnnotations` and variable `Annotations`, `fmi3.Annotation(type, xml)`
  for FMI 3 variable and model-level `Annotations` (the latter only from
  `read`). Without it, the fields are `None` and nothing is kept.
- Version-independent `typing.Protocol`s: `mdxml.ModelHeader`,
  `mdxml.ModelVariable` and `mdxml.InterfaceType`, satisfied by the FMI 2.0 and
  FMI 3.0 classes (also usable with `isinstance`). FMI 2.0 headers expose `guid`
  as `instantiation_token` too.
- `mdxml.read(src)` returns the whole Model Description in one pass
  (`fmi2.ModelDescription` / `fmi3.ModelDescription`): the Model Header, every
  Model Variable and the Model Structure (FMI 2 by Variable Index, FMI 3 by
  value reference), with `dependencies` / `dependenciesKind` kept as written.
  Lookups: `variable_by_name`, `variable_by_value_reference` (FMI 2 takes an
  optional `type_name`) and, for FMI 2, `variable_by_index`; all raise
  `KeyError` for unknown keys.
- Unit definitions, type definitions and log categories are `mdxml.Named`
  tuples that can also be indexed by name (`header.type_definitions["Position"]`).
- `mdxml.iter_variables(src)` streams FMI 2.0 Model Variables one at a time
  with flat memory, stopping at `</ModelVariables>`. One class per kind
  (`RealVariable`, `IntegerVariable`, `BooleanVariable`, `StringVariable`,
  `EnumerationVariable`, all `ScalarVariable`s) with the typed child's
  attributes merged in, a `type_name`, the Variable Index, enums for
  causality, variability and initial, and `effective_initial` from the
  standard's table. `causality=`, `variability=` and `name_prefix=` filters
  skip non-matching variables before they're built. The iterator's `.header`
  is the Model Header from the same pass, and it can be closed early or used
  as a context manager.
- `iter_variables` streams FMI 3.0 Model Variables too: one class per element
  kind (`Float32Variable` … `ClockVariable`), with aliases, `<Dimension>`s,
  tuple `start` values for arrays, `String`/`Binary` `<Start>` children
  (`Binary` as `bytes`), all clock attributes, `variability` defaulted as the
  standard defines it, and `effective_initial` from the standard's Table 22.
- `to_dict` turns `bytes` into hex strings.
- `mdxml variables FILE [--causality …] [--variability …] [--name-prefix …]`
  prints one JSON object per variable.
- `read_header` returns the full FMI 3.0 Model Header (`mdxml.fmi3.ModelHeader`):
  Interface Types including `ScheduledExecution`, units with `inverse` display
  units, all fifteen type definition kinds (`Float32Type` … `ClockType`), log
  categories and the default experiment. `Annotations` are skipped. Any
  `fmiVersion` of major version 3 is read; strict mode checks it against the
  XSD pattern. `read_header` is typed as returning
  `fmi2.ModelHeader | fmi3.ModelHeader`.
- Lenient parsing by default; `strict=True` (CLI: `--strict`) raises
  `ParseError` on unknown elements and attributes, missing required attributes,
  out-of-range enum values and values that can't be read.
- `read_header` accepts a `.fmu` zip path, an unzipped FMU directory, a
  `modelDescription.xml` path, a binary file-like object or bytes. Zips are
  detected by magic bytes and streamed without extracting to disk; `member=`
  (CLI: `--member`) overrides the Model Description's location.
- Hostile input protection, always on: any `DOCTYPE` or entity declaration is
  refused, external entities are never resolved, and XML larger than
  `max_xml_bytes` (default 256 MB, per call; CLI: `--max-xml-bytes`) is refused,
  counting the decompressed size for zips. These raise `UnsafeInput`. Corrupt
  zip data raises `ParseError`.
- `MdxmlError`, `ParseError` (with line and column), `UnsafeInput` and
  `UnsupportedFmiVersion`.
- `mdxml.to_dict()` converts parsed objects into JSON-ready data (infinite and
  NaN floats become `"INF"`, `"-INF"` and `"NaN"`).
- `mdxml header FILE` command (also `python -m mdxml`) prints the Model Header
  as JSON.
- Project scaffold: package metadata, `py.typed` marker, MIT license, and CI
  running tests, mypy and pyright on Python 3.10–3.14 across Linux, macOS and
  Windows.
