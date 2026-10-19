# Reproduce the public checks

_Offline verification with Python 3.11+; optional plotting with a separate environment._

The [19 October received-data inventory](../evidence/received-2026-10-19/README.md) documents the historical scientific projection, source hashes, retained columns and exclusions. The same verification command validates that supplement. The original 0.1.0 subset and calculations remain unchanged. Article and appendix PDFs are byte-identical to the reviewed edition identified by [article provenance](article/provenance.json). The later [complete snapshot](../reproducibility/README.md) separately releases the available historical source and raw corpus; verification does not execute or rebuild that research pipeline.

## Verify the release

From a fresh clone:

```bash
python -m tools.verify
python -m unittest discover -s tests -v
python -m tools.recompute --check
```

No package installation, account, token, model, compiler or cluster access is required for these commands. The tools read public JSON/JSONL files and calculate hashes and statistics. They do not execute received programs or load executable checkpoints.

Expected initial-release coverage is 144 controller series, including 24 excluded warmups and 2,400 measured cycles, plus 200 CPU timings / 40 configurations. The rejection tests check arithmetic, warmup exclusion, incomplete designs, duplicates, changed inputs/binaries, invalid outputs, nonfinite values, modified or unlisted files and unsafe paths.

The [native first-batch projection](../evidence/native-first-batch-2026-10-19/README.md) adds three initial search timings and three contemporary reference timings, two delivered calls with exact role-level costs, private-audit digests and later ARM release acceptance. Its verifier recalculates statistics and the descriptive initial ratio, rejects private extra fields and unsupported confirmation/completion claims, and preserves the original search score as a separate observation. It does not execute the private programs, re-audit their SQLite registry or independently certify their performance. The earlier paused snapshot and later acceptance are separate dated records; neither changes the original budget or deadlines.

The article r5 [numeric comparison](article/donnees-r1-r2/comparison.json) and its two CSV views preserve 60 R1 cells and 26 individual timings across six series: R1 reference/candidate, R2 initial reference/candidate, and R2 final source-confirmed reference/candidate. The standard-library verifier checks their exact public projection, missing values, descriptive means, sample standard deviations, phase-specific normalization and ratios. It keeps eleven measured R1 zero gains at speedup 1, 59 R2 cells without scientific measurements, zero admitted R2 gains and zero admitted R1/R2 pairs. Source confirmation is not independent performance certification; different searches and audit time prevent a causal efficiency conclusion. The [figure reproduction instructions](article/donnees-r1-r2/REPRODUCTION.md) use only this numeric projection. The earlier [r4 article provenance](article/history/r4/provenance.json) and all its artifacts are preserved separately and still checked.

To emit all recalculated results without changing files:

```bash
python -m tools.recompute
```

Integer nanosecond counters must agree exactly with their recorded cycle sums. Derived floating-point values are compared at relative tolerance `1e-12`, absolute tolerance `1e-15`, to accommodate arithmetic differences across Python versions. This tolerance applies to recomputation, **not** to the evaluated programs’ output oracle.

## What is in the public projection

| Dataset | Public data | Transformation |
| --- | --- | --- |
| Controller | Every raw series, per-cycle wall/CPU nanoseconds, seeds and trace digests | Internal variant labels replaced by neutral IDs; timing integers unchanged |
| CPU scaling | All reference/selected timings at 1/2/4/8/16 cores for the four largest cases | Local campaign/account fields removed; program/input digests and timing values retained |

The CPU subset selection is explicit and includes all four subjects in that largest-case stratum, including near-flat results. It contains 200 of the original batch’s 1,400 timings. It is not a claim to release the entire research corpus.

`MANIFEST.json` lists SHA-256 hashes and byte lengths for the release files, excluding the manifest itself. It checks consistency within a checkout. A Git commit or release fixes the manifest version. If an attacker replaces both data and manifest, the manifest alone cannot authenticate the original observation; retain the trusted commit identifier when citing or comparing releases.

The dated provenance files record original archive hashes and audit counts. They retain their original publication boundary. The later complete snapshot supplies available source archives, raw results and operational materials with a separate path/object inventory. Its verifier checks the released file bytes, including part and complete-file hashes; this does not authenticate an experiment independently of a trusted release or reproduce performance.

## Render the figures

Figure rendering is optional and separate from evidence verification. Use Python 3.13 and a new environment:

```bash
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -r requirements-figures.txt
python -m tools.plot_results
```

This regenerates PNG and SVG figures from [results.json](../evidence/results.json). Recalculate/check the results before plotting. Numerical values should agree; fonts and image bytes can vary across platforms. The distributed figures were rendered with Matplotlib 3.10.8. Any changed figure must be reviewed before updating the release manifest.

## Recalculation versus experimental reproduction

Public readers can verify record completeness, hash consistency and arithmetic. They can inspect the protocol and run an independent system against a separately prepared benchmark.

Historical controller implementations and available programs/inputs can now be restored from the complete snapshot. Restoring their bytes does not recreate original hardware, accounts, software installations, time limits or model responses. The published correctness and environment observations still come from the original campaign; no new execution is performed by the restoration tool. The source guides identify the exact R1 historical cohort, its comparison-derived harness and the R2 native edition separately. The R2 transport prototype remains unintegrated, and all experiments remain paused.

To carry out a new hardware experiment, follow the [protocol](PROTOCOL.md) and [comparison guide](COMPARING.md), qualify the benchmark and preserve the actual environment and raw measurements. A new run is a new observation, not a replacement for an older inconvenient result.
