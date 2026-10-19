# Public evidence inventory

_A curated timing projection with explicit provenance and reproduction limits._

The [19 October received-data inventory](received-2026-10-19/README.md) adds the complete admitted historical data and the Sol R2h supplement. The table below describes the preserved initial release subset; overlapping timings must not be counted twice as independent samples. The [article and appendices](../docs/RECEIVED-2026-10-19.md) explain the additional cohorts.

The later [first native R2 batch](native-first-batch-2026-10-19/README.md) is a separate initial-search projection for Luna MAX on 2020-quicksort, with a contemporary reference, exact role-level costs, private audit and ARM release acceptance. It has no final confirmation or admitted scientific gain and does not replace the dated r4 missing-data snapshot.

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
