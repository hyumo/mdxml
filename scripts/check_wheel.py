"""Check a built wheel: no XSD files, no runtime dependencies, py.typed present.

Usage: python scripts/check_wheel.py dist/*.whl
"""

from __future__ import annotations

import sys
import zipfile
from email.parser import Parser


def check(path: str) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        problems += [f"XSD file shipped: {n}" for n in names if n.lower().endswith(".xsd")]
        if not any(n.endswith("mdxml/py.typed") for n in names):
            problems.append("py.typed marker missing")
        metadata_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(wheel.read(metadata_name).decode())
        problems += [f"runtime dependency declared: {d}" for d in metadata.get_all("Requires-Dist") or []]
    return problems


def main(paths: list[str]) -> int:
    if not paths:
        print("usage: check_wheel.py WHEEL [WHEEL ...]", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        problems = check(path)
        for problem in problems:
            print(f"{path}: {problem}", file=sys.stderr)
        failed |= bool(problems)
        if not problems:
            print(f"{path}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
