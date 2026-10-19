# Reproduce the public checks

_Offline verification with Python 3.11+; optional plotting with a separate environment._

The [19 October received-data inventory](../evidence/received-2026-10-19/README.md) documents the additional complete historical projection, source hashes, retained columns and exclusions. The same verification command also validates that supplement. The original 0.1.0 subset and its calculations below remain available unchanged. Article and appendix PDFs are byte-identical to the reviewed edition identified by [article provenance](article/provenance.json); the public bundle does not rebuild the private research pipeline.

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

The provenance files also record original private-archive hashes and audit counts. Those hashes support identity if the original archives are later inspected. Since the archives are not distributed here, the public checks cannot establish their contents or authenticity independently.

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

They cannot reproduce the internal controller execution from this repository, because its implementation is not distributed. They also cannot re-run the original CPU programs or re-check their outputs without the original binaries and protected inputs. The published correctness and environment observations come from the original audited campaign. These boundaries are part of the evidence, not gaps to fill with assumed success.

To carry out a new hardware experiment, follow the [protocol](PROTOCOL.md) and [comparison guide](COMPARING.md), qualify the benchmark and preserve the actual environment and raw measurements. A new run is a new observation, not a replacement for an older inconvenient result.
