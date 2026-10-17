# Public evidence inventory

_A curated timing projection with explicit provenance and reproduction limits._

| File | Coverage | Unit |
| --- | --- | --- |
| [controller/timings.jsonl](controller/timings.jsonl) | 144 series; 24 warmups excluded; 2,400 measured cycles | Integer wall/CPU nanoseconds per cycle |
| [controller/provenance.json](controller/provenance.json) | Original archive/audit identity and public transformation | Metadata |
| [cpu-scaling/timings.json](cpu-scaling/timings.json) | 200 samples; four subjects; reference and selected binaries; five core counts | Seconds per launch |
| [cpu-scaling/provenance.json](cpu-scaling/provenance.json) | Explicit largest-case subset of a 1,400-sample batch | Metadata |
| [results.json](results.json) | Recomputed descriptive statistics and ratios | Derived values |

Variant IDs conceal the controller implementation; they do not anonymize the experimental conditions needed for the stated overhead comparison. CPU program and input hashes link measurements across core counts without redistributing the corresponding bytes.

The provenance preserves original archive and audit hashes. Timing values are unchanged by the projection. Account paths, transport details, credentials, internal source and protected inputs are excluded.

Run `python -m tools.verify` from the repository root. See [reproducibility](../docs/REPRODUCIBILITY.md) for what is and is not independently reproducible, and [results](../docs/RESULTS.md) for interpretation.
