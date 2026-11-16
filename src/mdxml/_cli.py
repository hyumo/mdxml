"""The ``mdxml`` command-line tool."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from mdxml._dict import to_dict
from mdxml._errors import MdxmlError
from mdxml._header import read_header


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdxml", description="Read FMI modelDescription.xml files.")
    commands = parser.add_subparsers(dest="command", required=True)
    header = commands.add_parser("header", help="print the Model Header as JSON")
    header.add_argument("path", help="a .fmu file, an unzipped FMU directory or a modelDescription.xml file")
    header.add_argument(
        "--member", help="where the Model Description lives inside the FMU (default: modelDescription.xml)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        header = read_header(args.path, member=args.member)
    except (MdxmlError, OSError, ValueError, TypeError) as exc:
        print(f"mdxml: error: {exc}", file=sys.stderr)
        return 1
    json.dump(to_dict(header), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0
