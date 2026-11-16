"""Benchmark mdxml against FMPy's ``read_model_description`` on generated FMUs.

    uv run --group bench python benchmarks/bench.py [--sizes 1000 100000 1000000] [--repeat 3]

Each measurement runs in a fresh Python process, so imports, caches and memory
from one run can't affect another. Time is the fastest of ``--repeat`` runs.
Memory is the process's peak resident set size minus its size after imports,
so it includes C-level allocations (lxml's) that ``tracemalloc`` can't see.
Peak RSS needs the ``resource`` module, so this script runs on Linux and macOS.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

OPERATIONS: dict[str, str] = {
    "mdxml.read_header": "Model Header only",
    "mdxml.iter_variables": "stream every variable",
    "mdxml.read": "whole Model Description",
    "fmpy (validate=False)": "read_model_description(validate=False)",
    "fmpy (validate=True)": "read_model_description() (its default: XSD validation)",
}


def _peak_rss_kib() -> int:
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak // 1024 if sys.platform == "darwin" else peak  # bytes on macOS, KiB on Linux


def _operation(name: str, path: str) -> Callable[[], int]:
    """Return a callable doing one operation and returning how many variables it read."""
    if name.startswith("mdxml"):
        import mdxml

        if name == "mdxml.read_header":
            return lambda: len(mdxml.read_header(path).model_name) * 0
        if name == "mdxml.iter_variables":
            return lambda: sum(1 for _ in mdxml.iter_variables(path))
        return lambda: len(mdxml.read(path).variables)

    import fmpy  # FMPy has no type hints

    read_model_description: Any = getattr(fmpy, "read_model_description")  # noqa: B009 - FMPy is untyped
    validate = name.endswith("(validate=True)")
    return lambda: len(read_model_description(path, validate=validate).modelVariables)


def worker(name: str, path: str) -> None:
    """Run one operation once and print its time, variable count and memory as JSON."""
    operation = _operation(name, path)
    baseline = _peak_rss_kib()
    started = time.perf_counter()
    count = operation()
    elapsed = time.perf_counter() - started
    print(json.dumps({"seconds": elapsed, "count": count, "rss_kib": _peak_rss_kib() - baseline}))


def measure(name: str, path: Path, repeat: int) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for _ in range(repeat):
        out = subprocess.run(
            [sys.executable, __file__, "--worker", name, str(path)], capture_output=True, text=True, check=False
        )
        if out.returncode != 0:
            return {"error": out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "failed"}
        runs.append(json.loads(out.stdout))
    return {
        "seconds": min(r["seconds"] for r in runs),
        "count": runs[0]["count"],
        "rss_kib": min(r["rss_kib"] for r in runs),
    }


def _format(result: dict[str, Any], variables: int, *, reads_variables: bool) -> str:
    if "error" in result:
        return f"| error: {result['error'][:60]} | | |"
    seconds = result["seconds"]
    rate = f"{variables / seconds / 1000:,.0f}k/s" if seconds > 0 and reads_variables else "—"
    time_text = f"{seconds * 1000:,.1f} ms" if seconds < 1 else f"{seconds:,.2f} s"
    megabytes = result["rss_kib"] / 1024
    # Below 1 MB the peak doesn't rise measurably above the interpreter's own startup peak.
    memory = "< 1 MB" if megabytes < 1 else f"{megabytes:,.0f} MB"
    return f"| {time_text} | {rate} | {memory} |"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", maxsplit=1)[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 100_000, 1_000_000])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--worker", nargs=2, metavar=("OPERATION", "PATH"), help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help="also write the report to this Markdown file")
    args = parser.parse_args(argv)
    if args.worker:
        worker(*args.worker)
        return 0

    import fmpy
    from fmu_factory import write_fmu

    fmpy_version: str = getattr(fmpy, "__version__", "?")

    lines = [
        "# Benchmarks",
        "",
        f"mdxml {importlib.metadata.version('mdxml')} vs FMPy {fmpy_version} · Python {platform.python_version()} · "
        f"{platform.system()} {platform.machine()} · best of {args.repeat} fresh processes",
        "",
        "Variables/s is the file's variable count over the time; `read_header` reads none, so it has no rate.",
        "Memory is peak RSS above the process's size after imports.",
    ]
    with tempfile.TemporaryDirectory() as folder:
        for version in (2, 3):
            for size in args.sizes:
                path = write_fmu(Path(folder) / f"fmi{version}_{size}.fmu", version, size)
                lines += [
                    "",
                    f"## FMI {version}, {size:,} variables",
                    "",
                    "| Operation | Time | Variables/s | Peak memory |",
                    "|---|---|---|---|",
                ]
                for name in OPERATIONS:
                    result = measure(name, path, args.repeat)
                    reads_variables = name != "mdxml.read_header"
                    lines.append(f"| {name} " + _format(result, size, reads_variables=reads_variables))
                    print(lines[-1], file=sys.stderr, flush=True)
    report = "\n".join(lines) + "\n"
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
