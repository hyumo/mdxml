# mdxml

Reads the model description of an FMU (FMI 2.0 and 3.0) quickly, and lets callers read only the parts they need.

## Language

**FMU**:
A Functional Mock-up Unit: a zip archive (or its unzipped directory) packaging a model under the FMI standard.
_Avoid_: model file, archive

**Model Description**:
The `modelDescription.xml` document at the root of an FMU, describing the model's interface. Its shape is defined by the FMI XSD for its version.
_Avoid_: manifest, metadata file

**FMI Version**:
The major version of the FMI standard a Model Description conforms to (2 or 3), read from its `fmiVersion` attribute.
_Avoid_: schema version, spec version

**Model Header**:
Everything in a Model Description that comes before `ModelVariables`: the root attributes, the interface types (Model Exchange, Co-Simulation, Scheduled Execution), unit definitions, type definitions, log categories and the default experiment. Tool Annotations are not part of it, though FMI 2's `VendorAnnotations` (which come before `ModelVariables`) can be read along with it.
_Avoid_: info, metadata, summary

**Interface Type**:
One way an FMU can be run, declared in the Model Header: Model Exchange, Co-Simulation, or (FMI 3 only) Scheduled Execution.
_Avoid_: FMU type, mode

**Model Variable**:
One variable declared in `ModelVariables`: a `ScalarVariable` in FMI 2, or a typed variable element such as `Float64` or `Clock` in FMI 3.
_Avoid_: signal, parameter (a parameter is one causality, not the general term)

**Variable Index**:
A Model Variable's 1-based position in `ModelVariables`, in file order. FMI 2's Model Structure refers to variables by it.
_Avoid_: position, offset

**Effective Initial**:
A Model Variable's `initial` value: the one written in the file if present, otherwise the one the FMI standard derives from its causality and variability.
_Avoid_: default initial

**Tool Annotation**:
A block of tool-specific XML inside an annotations element: a `Tool` identified by its `name` in FMI 2, an `Annotation` identified by its `type` in FMI 3. Its content has no schema.
_Avoid_: vendor data, extension

**Model Structure**:
The `ModelStructure` section that follows `ModelVariables`, declaring outputs, derivatives, initial unknowns and their dependencies.
_Avoid_: dependency graph
