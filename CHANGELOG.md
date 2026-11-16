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
