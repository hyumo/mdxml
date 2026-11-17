# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, the public API may change
between minor versions.

## [Unreleased]

## [0.1.1] - 2026-11-16

### Changed

- The README shows how to install with uv (`uv add mdxml`,
  `uv pip install mdxml`) and how to run the command-line tool without
  installing it (`uvx mdxml header model.fmu`).
- Each release now also creates a GitHub release, with the changelog section as
  its notes and the published wheel and sdist attached.

## [0.1.0] - 2026-11-16

First release: a fast, zero-dependency reader for FMI 2.0 and FMI 3.0
`modelDescription.xml` files.

### Added

- Three entry points, each a single streaming pass with expat:
  - `mdxml.read_header(src)` returns the Model Header (root attributes,
    interface types, units, type definitions, log categories and the default
    experiment) and stops at `<ModelVariables>`, so its cost doesn't depend on
    the number of variables.
  - `mdxml.iter_variables(src)` streams Model Variables one at a time with flat
    memory and stops at `</ModelVariables>`. `causality=`, `variability=` and
    `name_prefix=` filters skip variables before they're built. The iterator's
    `.header` comes from the same pass, and it can be closed early or used as a
    context manager.
  - `mdxml.read(src)` returns the whole Model Description: the Model Header,
    every Model Variable and the Model Structure, with `variable_by_name`,
    `variable_by_value_reference` and (FMI 2) `variable_by_index` lookups.
- Inputs: a `.fmu` path (detected by content, not extension), an unzipped FMU
  directory, a `modelDescription.xml` path, a binary file-like object or
  `bytes`. Zips are read in place without extracting; `member=` overrides the
  Model Description's location.
- FMI 2.0 and FMI 3.0 types in `mdxml.fmi2` and `mdxml.fmi3`: frozen, slotted
  dataclasses that mirror each version's XSD, with real Python types, XSD
  defaults and enums. FMI 3 arrays (`<Dimension>`, tuple `start` values),
  aliases, `Binary` values (as `bytes`) and clocks are supported. Variables
  carry their Variable Index and `effective_initial`, from the standard's
  causality × variability tables.
- Version-independent `typing.Protocol`s, `mdxml.ModelHeader`,
  `mdxml.ModelVariable` and `mdxml.InterfaceType`, satisfied by both versions'
  classes. FMI 2's `guid` is also available as `instantiation_token`.
- Unit definitions, type definitions and log categories are `mdxml.Named`
  tuples that can also be indexed by name.
- Lenient parsing by default; `strict=True` raises `ParseError` (with line and
  column) on unknown elements and attributes, missing required attributes,
  unknown enum values and values that can't be read.
- `annotations=True` keeps Tool Annotations (`fmi2.ToolAnnotation`,
  `fmi3.Annotation`) as their exact raw XML; by default they're skipped and
  nothing is kept.
- Hostile input protection, always on: any `DOCTYPE` or entity declaration is
  refused, external entities are never resolved, and XML larger than
  `max_xml_bytes` (default 256 MB, counting decompressed size for zips) is
  refused. These raise `UnsafeInput`.
- Errors: `MdxmlError`, with `ParseError`, `UnsafeInput` and
  `UnsupportedFmiVersion`.
- `mdxml.to_dict()` converts any result into JSON-ready data.
- All results are immutable and picklable, and parsing keeps no shared state,
  so it's safe with threads and process pools.
- The `mdxml` command (also `python -m mdxml`): `mdxml header` prints the Model
  Header as JSON, and `mdxml variables` prints one JSON object per variable.
  Both take `--member`, `--strict`, `--annotations` and `--max-xml-bytes`, and
  `variables` also takes `--causality`, `--variability` and `--name-prefix`.
- Type hints throughout (`py.typed`). Python 3.10 to 3.14 on Linux, macOS and
  Windows, with no runtime dependencies.
