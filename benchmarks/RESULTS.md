# Benchmarks

mdxml 0.1.0 vs FMPy 0.3.32 · Python 3.13.14 · Linux x86_64 · best of 3 fresh processes

Variables/s is the file's variable count over the time; `read_header` reads none, so it has no rate.
Memory is peak RSS above the process's size after imports.

## FMI 2, 1,000 variables

| Operation | Time | Variables/s | Peak memory |
|---|---|---|---|
| mdxml.read_header | 0.5 ms | — | < 1 MB |
| mdxml.iter_variables | 8.6 ms | 116k/s | < 1 MB |
| mdxml.read | 9.5 ms | 105k/s | < 1 MB |
| fmpy (validate=False) | 20.9 ms | 48k/s | 5 MB |
| fmpy (validate=True) | 23.3 ms | 43k/s | 6 MB |

## FMI 2, 100,000 variables

| Operation | Time | Variables/s | Peak memory |
|---|---|---|---|
| mdxml.read_header | 0.5 ms | — | < 1 MB |
| mdxml.iter_variables | 803.3 ms | 124k/s | < 1 MB |
| mdxml.read | 941.5 ms | 106k/s | 47 MB |
| fmpy (validate=False) | 969.5 ms | 103k/s | 314 MB |
| fmpy (validate=True) | 1.10 s | 91k/s | 322 MB |

## FMI 2, 1,000,000 variables

| Operation | Time | Variables/s | Peak memory |
|---|---|---|---|
| mdxml.read_header | 0.5 ms | — | < 1 MB |
| mdxml.iter_variables | 8.11 s | 123k/s | < 1 MB |
| mdxml.read | 10.20 s | 98k/s | 586 MB |
| fmpy (validate=False) | 10.84 s | 92k/s | 3,119 MB |
| fmpy (validate=True) | 12.31 s | 81k/s | 3,177 MB |

## FMI 3, 1,000 variables

| Operation | Time | Variables/s | Peak memory |
|---|---|---|---|
| mdxml.read_header | 0.5 ms | — | < 1 MB |
| mdxml.iter_variables | 7.7 ms | 130k/s | < 1 MB |
| mdxml.read | 8.1 ms | 124k/s | < 1 MB |
| fmpy (validate=False) | 18.7 ms | 53k/s | < 1 MB |
| fmpy (validate=True) | 22.6 ms | 44k/s | < 1 MB |

## FMI 3, 100,000 variables

| Operation | Time | Variables/s | Peak memory |
|---|---|---|---|
| mdxml.read_header | 0.5 ms | — | < 1 MB |
| mdxml.iter_variables | 704.3 ms | 142k/s | < 1 MB |
| mdxml.read | 813.3 ms | 123k/s | 24 MB |
| fmpy (validate=False) | 807.3 ms | 124k/s | 279 MB |
| fmpy (validate=True) | 962.3 ms | 104k/s | 293 MB |

## FMI 3, 1,000,000 variables

| Operation | Time | Variables/s | Peak memory |
|---|---|---|---|
| mdxml.read_header | 0.5 ms | — | < 1 MB |
| mdxml.iter_variables | 7.11 s | 141k/s | < 1 MB |
| mdxml.read | 8.79 s | 114k/s | 555 MB |
| fmpy (validate=False) | 9.42 s | 106k/s | 2,935 MB |
| fmpy (validate=True) | 11.12 s | 90k/s | 3,055 MB |
