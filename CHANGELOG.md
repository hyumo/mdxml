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
- `MdxmlError`, `ParseError` (with line and column) and `UnsupportedFmiVersion`.
- `mdxml.to_dict()` converts parsed objects into JSON-ready data.
- `mdxml header FILE` command (also `python -m mdxml`) prints the Model Header
  as JSON.
- Project scaffold: package metadata, `py.typed` marker, MIT license, and CI
  running tests, mypy and pyright on Python 3.10–3.14 across Linux, macOS and
  Windows.
