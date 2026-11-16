# Stream with expat directly; no runtime XSD validation

We parse with `xml.parsers.expat` callbacks driving our own state machine, not `ElementTree`, `iterparse` or `lxml`, and we do not validate against the FMI XSDs at runtime. The goal is zero dependencies, peak memory that doesn't grow with variable count (the parser may run in parallel in web backends), and stopping as soon as the requested part is read. The XSDs in `schema/` are the source of truth for the shape of the data model, which is written by hand to mirror them and cross-checked against them in tests. They are not used to validate files at runtime.

## Considered Options

- `ElementTree.iterparse`: also standard library and C-backed, but builds an `Element` per tag that must be cleared by hand. Slower, and no real benefit for data that is mostly attributes.
- `lxml` with XSD validation: real validation, but adds a compiled dependency and holds the whole tree in memory.
