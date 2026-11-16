"""Issue #13: "fast" and "flat memory" as enforced properties, and safe concurrent use.

The FMUs are generated during the run (see ``fmu_factory``) and never committed.
Tests marked ``slow`` stream a million variables under ``tracemalloc``; run them
with ``pytest -m slow``.
"""

from __future__ import annotations

import multiprocessing
import pickle
import time
import tracemalloc
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fmu_factory import OUTPUT_EVERY, write_fmu

import mdxml

DATA = Path(__file__).parent / "data"
REFERENCES = sorted((DATA / "reference_fmus").glob("*/FMI[23].xml"))
SIZES = (1_000, 10_000, 100_000, 1_000_000)
KiB = 1024


@pytest.fixture(scope="session")
def fmus(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[int, int], Path]:
    """Zipped FMUs for FMI 2 and FMI 3 at every size, generated once per test session."""
    folder = tmp_path_factory.mktemp("fmus")
    return {(v, n): write_fmu(folder / f"fmi{v}_{n}.fmu", v, n) for v in (2, 3) for n in SIZES}


def peak_memory(action: Callable[[], object]) -> tuple[Any, int]:
    """Run ``action`` and return its result and its peak traced memory in bytes."""
    tracemalloc.start()
    try:
        result = action()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


def best_time(action: Callable[[], object], repeat: int = 7) -> float:
    """The fastest of ``repeat`` runs, in seconds; the minimum is the least noisy estimate."""
    timings: list[float] = []
    for _ in range(repeat):
        started = time.perf_counter()
        action()
        timings.append(time.perf_counter() - started)
    return min(timings)


def count_variables(path: Path) -> int:
    return sum(1 for _ in mdxml.iter_variables(path))


# --- Flat memory ----------------------------------------------------------------------------


@pytest.mark.parametrize("version", [2, 3])
def test_iter_variables_peak_memory_is_flat(fmus: dict[tuple[int, int], Path], version: int) -> None:
    small_count, small_peak = peak_memory(lambda: count_variables(fmus[(version, 1_000)]))
    large_count, large_peak = peak_memory(lambda: count_variables(fmus[(version, 100_000)]))

    assert (small_count, large_count) == (1_000, 100_000)
    # 100x the variables: peak memory must stay about the same (bounded by one chunk's worth).
    assert large_peak < small_peak * 1.5 + 256 * KiB, f"{small_peak=} {large_peak=}"


@pytest.mark.slow
@pytest.mark.parametrize("version", [2, 3])
def test_iter_variables_peak_memory_is_flat_at_a_million(fmus: dict[tuple[int, int], Path], version: int) -> None:
    small_count, small_peak = peak_memory(lambda: count_variables(fmus[(version, 1_000)]))
    huge_count, huge_peak = peak_memory(lambda: count_variables(fmus[(version, 1_000_000)]))

    assert (small_count, huge_count) == (1_000, 1_000_000)
    assert huge_peak < small_peak * 1.5 + 256 * KiB, f"{small_peak=} {huge_peak=}"


def test_the_memory_check_would_catch_growth(fmus: dict[tuple[int, int], Path]) -> None:
    # Keeping every variable (what a regression would do) grows memory with the count.
    _, small_peak = peak_memory(lambda: list(mdxml.iter_variables(fmus[(2, 1_000)])))
    _, large_peak = peak_memory(lambda: list(mdxml.iter_variables(fmus[(2, 10_000)])))
    assert large_peak > small_peak * 1.5 + 256 * KiB


# --- read_header doesn't depend on the variable count --------------------------------------


@pytest.mark.parametrize("version", [2, 3])
def test_read_header_time_and_memory_are_flat(fmus: dict[tuple[int, int], Path], version: int) -> None:
    small, huge = fmus[(version, 1_000)], fmus[(version, 1_000_000)]
    assert mdxml.read_header(huge).model_name == "Big1000000"

    small_time = best_time(lambda: mdxml.read_header(small))
    huge_time = best_time(lambda: mdxml.read_header(huge))
    _, small_peak = peak_memory(lambda: mdxml.read_header(small))
    _, huge_peak = peak_memory(lambda: mdxml.read_header(huge))

    # 1,000x the variables: about as fast and as small (the header is read, then parsing stops).
    assert huge_time < small_time * 5 + 0.002, f"{small_time=:.6f} {huge_time=:.6f}"
    assert huge_peak < small_peak * 1.5 + 64 * KiB, f"{small_peak=} {huge_peak=}"


# --- Concurrency ----------------------------------------------------------------------------


def job(kind: str, path: Path) -> Any:
    """One unit of work; module-level so a process pool can pickle it."""
    if kind == "header":
        return mdxml.read_header(path)
    if kind == "variables":
        return tuple(mdxml.iter_variables(path))
    return mdxml.read(path, annotations=True)


def jobs(fmus: dict[tuple[int, int], Path]) -> list[tuple[str, Path]]:
    # 10k variables span dozens of 64 KB chunks, so concurrent streams genuinely interleave.
    paths = [*REFERENCES, fmus[(2, 1_000)], fmus[(3, 1_000)], fmus[(2, 10_000)], fmus[(3, 10_000)]]
    return [(kind, path) for path in paths for kind in ("header", "variables", "read")]


def run_sequentially(work: list[tuple[str, Path]]) -> list[Any]:
    return [job(kind, path) for kind, path in work]


def test_threads_give_the_same_results(fmus: dict[tuple[int, int], Path]) -> None:
    work = jobs(fmus) * 2
    expected = run_sequentially(work)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(job, *zip(*work, strict=True)))
    assert results == expected


def test_threads_interleaving_streams_give_the_same_results(fmus: dict[tuple[int, int], Path]) -> None:
    paths = [fmus[(2, 10_000)], fmus[(3, 10_000)]] * 8
    expected = [tuple(mdxml.iter_variables(path)) for path in paths]

    def stream(path: Path) -> tuple[Any, ...]:
        return tuple(mdxml.iter_variables(path))

    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        assert list(pool.map(stream, paths)) == expected


def test_processes_give_the_same_results(fmus: dict[tuple[int, int], Path]) -> None:
    work = jobs(fmus)
    expected = run_sequentially(work)
    # "spawn" behaves the same on every OS, and proves results survive pickling.
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(job, *zip(*work, strict=True)))
    assert results == expected


def every_result(fmus: dict[tuple[int, int], Path]) -> Iterator[Any]:
    yield from run_sequentially(jobs(fmus))


def test_every_result_pickles(fmus: dict[tuple[int, int], Path]) -> None:
    for result in every_result(fmus):
        restored = pickle.loads(pickle.dumps(result))
        assert restored == result
        if isinstance(result, (mdxml.fmi2.ModelDescription, mdxml.fmi3.ModelDescription)):
            # The lookup indexes are rebuilt after unpickling.
            first = result.variables[0]
            assert restored.variable_by_name(first.name) == first


def test_generated_fmus_are_valid(fmus: dict[tuple[int, int], Path]) -> None:
    for version in (2, 3):
        md = mdxml.read(fmus[(version, 1_000)], strict=True)
        assert len(md.variables) == 1_000
        outputs = md.model_structure.outputs
        assert len(outputs) == len(range(0, 999, OUTPUT_EVERY))
        assert md.variables[0].causality == "independent"
