# Blank experiment templates

_Planning and data-collection forms; no example result is prefilled._

| File | Fill before / during |
| --- | --- |
| [experiment-plan.json](experiment-plan.json) | Freeze before the search; identify source, contract, rights, budgets and analysis |
| [environment.json](environment.json) | Separate requested, allocated and actually observed resources |
| [timings.csv](timings.csv) | One row per launch; keep warmup/search/final phases separate |
| [outcomes.csv](outcomes.csv) | One row per independent search outcome, including missing or negative results |

`null` means not yet supplied or unknown; it is not a successful observation. The example budget values define the default profile and are not measured consumption. CSV files contain headers only.

Use explicit final states: `confirmed_gain`, `reference_retained`, `finalist_rejected`, `confirmation_incomplete`, `infrastructure_incident`, `not_run` or `excluded`. Preserve explanatory evidence and costs for each. A missing confirmation must not be coded as `reference_retained` or silently converted to a zero gain.

A manifest/hash checker does not validate a newly contributed experiment’s scientific design. The current public recomputation tool accepts the two fixed released schemas; it does not claim to ingest arbitrary filled templates automatically. A new cohort needs its own reviewed adapter and validation.
