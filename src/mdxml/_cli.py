"""The ``mdxml`` command-line tool."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from mdxml._dict import to_dict
from mdxml._errors import MdxmlError
from mdxml._header import read_header
from mdxml._reader import DEFAULT_MAX_XML_BYTES
from mdxml._variables import iter_variables


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", help="a .fmu file, an unzipped FMU directory or a modelDescription.xml file")
    parser.add_argument(
        "--member", help="where the Model Description lives inside the FMU (default: modelDescription.xml)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="raise on anything the FMI XSD doesn't allow, instead of ignoring it",
    )
    parser.add_argument(
        "--max-xml-bytes",
        type=int,
        default=DEFAULT_MAX_XML_BYTES,
        help=f"refuse Model Descriptions larger than this many bytes (default: {DEFAULT_MAX_XML_BYTES})",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdxml", description="Read FMI modelDescription.xml files.")
    commands = parser.add_subparsers(dest="command", required=True)

    header = commands.add_parser("header", help="print the Model Header as JSON")
    _add_source_arguments(header)

    variables = commands.add_parser("variables", help="print the Model Variables as JSON, one per line")
    _add_source_arguments(variables)
    variables.add_argument("--causality", action="append", help="only variables with this causality (repeatable)")
    variables.add_argument("--variability", action="append", help="only variables with this variability (repeatable)")
    variables.add_argument("--name-prefix", help="only variables whose name starts with this")
    return parser


def _print_header(args: argparse.Namespace) -> None:
    header = read_header(args.path, member=args.member, strict=args.strict, max_xml_bytes=args.max_xml_bytes)
    json.dump(to_dict(header), sys.stdout, indent=2, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")


def _print_variables(args: argparse.Namespace) -> None:
    variables = iter_variables(
        args.path,
        causality=args.causality,
        variability=args.variability,
        name_prefix=args.name_prefix,
        member=args.member,
        strict=args.strict,
        max_xml_bytes=args.max_xml_bytes,
    )
    with variables:
        for variable in variables:
            sys.stdout.write(json.dumps(to_dict(variable), ensure_ascii=False, allow_nan=False))
            sys.stdout.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line tool and return its exit code."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "header":
            _print_header(args)
        else:
            _print_variables(args)
    except (MdxmlError, OSError, ValueError, TypeError) as exc:
        sys.stdout.flush()
        print(f"mdxml: error: {exc}", file=sys.stderr)
        return 1
    return 0
