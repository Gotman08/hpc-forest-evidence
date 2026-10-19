# Received evidence — 19 October 2026

This public projection expands the original 16 October timing subset with the received numerical evidence used in the article. Historical scientific data stop at **2026-10-18 05:03:23.898140 UTC**. The separate technical snapshot stops at **2026-10-19 06:05:01.280470 UTC**. These are frozen observations; the operational file does not describe the current live queue or authorize another run.

Run from the repository root:

```sh
python -m tools.received
```

The standard-library verifier checks every raw CPU repetition, recomputes means and sample standard deviations, checks comparisons against their raw groups, recalculates registry and final-confirmation ratios, validates schemas and cost sums, and checks the complete inventories. It executes no candidate, model, archive script or job. Original source fingerprints are provenance references: their private bytes are not available in this repository for an independent comparison. The repository manifest separately binds the published bytes.

## Public files

| File | Bytes | Scope |
| --- | ---: | --- |
| [campaigns.json](campaigns.json) | 77,610 | 209 campaign identifiers and registry fingerprints |
| [registers.jsonl](registers.jsonl) | 2,293,832 | 209 registries; 2,482 trials, including all recorded negative outcomes |
| [confirmations.csv](confirmations.csv) | 50,840 | 193 final confirmation rows; 14 native cohorts and 6 separate DeepSeek rows |
| [cpu-timings.csv](cpu-timings.csv) | 3,371,158 | 11,575 individual wall/CPU measurements; 2,315 configurations |
| [cpu-comparisons.csv](cpu-comparisons.csv) | 1,017,806 | 1,830 campaign/input/core comparisons linked to raw measurements |
| [cpu-batches.json](cpu-batches.json) | 23,482 | 10 allocation batches and recorded CPU affinity/resource metadata |
| [cpu-campaigns.json](cpu-campaigns.json) | 65,777 | 58 campaign memberships in CPU batches |
| [cost-observations.json](cost-observations.json) | 1,462,907 | 1,822 call observations in 11 separate, overlapping source views |
| [historical-summaries.json](historical-summaries.json) | 35,210 | 42 exploratory summaries with costs and selections as originally recorded |
| [sol-r2h.json](sol-r2h.json) | 3,247 | 3 exact calls; 5 independently executed frozen-pair rounds; 3 zero-start incidents |
| [operational-status.json](operational-status.json) | 847 | R2g partial closure, R3/R4b and R5 editorial states, 60-cell matrix snapshot |
| [provenance.json](provenance.json) | 4,965 | Source names, original byte lengths and SHA-256 fingerprints |
| [summary.json](summary.json) | 3,863 | Offline recomputation of counts, trial states and per-source costs |

This README describes the projection. All numerical artifacts are below 50 MiB. The 209 registry records and 193 selected confirmation rows are distinct inventories. Cohort row counts are in `summary.json`; the fourteen native cohorts exclude the six DeepSeek comparison rows. The 42 historical summaries remain a separate archive of exploratory protocols and are not added to those cohorts.

## Units and joining records

All wall and CPU durations and standard deviations are **seconds**. CPU `mean_used_cores` is CPU seconds divided by wall seconds. Repetitions are numbered 0–4; all five are present for each batch/case/program/core configuration. Sample standard deviation uses n−1. The CSV files preserve the original numeric text. CSV encoding and line endings are normalized; their file hashes therefore differ from the original source hashes. Empty `native_calls` in six DeepSeek confirmation rows means not provided by that source, not zero.

`gain_fraction` is 1 − chosen/reference, `gain_percent` is 100 times that fraction, and `speedup` is reference/chosen. Core-scaling speedup compares the same binary and input to one core; efficiency divides that speedup by the core count. Trials and confirmation evaluations include failed builds, incorrect outputs, duplicates, infrastructure failures, cancelled budgets and generation failures. A missing timing stays null or an empty sample list; it is never replaced with a fabricated observation.

A campaign ID is `campaign-` followed by SHA-256 of the exact original campaign-root string encoded in UTF-8. `campaigns.json` contains only that digest and scientific identifiers; it does not contain the original path or a reversible lookup table. Registry fingerprints retain the original received registry identity. Input, binary, output, commit and tree fingerprints link observations without distributing their bytes. CPU batches remain separate; repeated controls across allocations are not collapsed.

The registry projection retains selected configuration counts, numeric budgets, compiler fingerprints, parent/source commit identifiers, final confirmation samples, and all 2,482 trial outcome records. Detailed contracts are represented by a canonical JSON digest plus language, timeout and case counts. Contract digest canonicalization is sorted-key ASCII JSON with compact separators. The separate registry digest remains the digest of the original registry bytes.

## Costs and unknowns

Each of the eleven cost exports is a separate observed view. The original global ledger and later cohort reconciliations overlap, and some later views replace earlier states. **Do not sum the eleven exports into a total consumption figure.** No global exact cost or deduplicated global invocation count is claimed. `summary.json` provides a separate count, known-token sum, null count and state histogram for each source view. Tokens are service token counts, not monetary charges. Cached-input and reasoning-output subdivisions are already included in input/output totals; reservations and upper-bound charges are not exact consumption.

Session, nonce, mission and campaign identifiers in the cost views are replaced by SHA-256 digests. Original request and response fingerprints are retained when provided. A row with `exact_total: null` has unknown consumption. A recorded pre-invocation expiry with an exact zero remains a zero; its state and invocation flags remain available. In particular, Sol source-only has **124 requests: 111 measured usages, 10 unknown-consumption invocations and 3 proven pre-invocation expirations**. Its 2,676,472 known exact tokens do not constitute a global exact total.

## Separate supplements and limits

Sol R2h has three reconciled calls totaling **59,037 known exact tokens**, with zero unknown invocations. Its frozen pair was rerun on a distinct allocation, yielding five retained samples per executable: 0.04385464321821928 s reference versus 0.004912436753511429 s selected, an 8.927268770813551 ratio. This is independent execution of a frozen pair using the **same Evaluator/timer implementation**, on a finite domain of twelve certified inputs. It does not establish an independent evaluator implementation, universal correctness, causal model ranking or a contest-wide gain. Source audit flags describe received audits rather than a new execution by this exporter. These samples and calls stay outside historical CPU and native-cohort aggregates.

The Astra, Terra and Luna successor allocations expired before any native invocation: zero calls, zero known tokens, zero unknown invocations and no scientific timing gain. R2g remains a partially closed metadata cohort: ten reconciled invocations, seven measured usages with 146,676 known exact tokens, and three unmetered invocations. Five confirmations, a complete pipeline and scientific/performance admission were not verified. The article reports R3 with corrected R4b technically blocked, R5 not launched, and zero of sixty new matrix15 cells started at its snapshot. These editorial status claims are preserved with the article and technical-source fingerprints; they are not live-state checks. The newer human instruction to use primes only as a one-time smoke test does not rewrite these historical observations.

The 42 older summaries retain `complete_as_recorded`, costs and `best_confirmed_as_recorded` without importing their original free-text interpretation. They have not been newly promoted into the admitted cohorts. In particular an old summary label is not a new correctness or performance certification.

## Excluded source material

The projection uses explicit field allowlists. It excludes account and absolute filesystem paths; hostnames; transport/mailbox details; credentials; raw sessions/nonces; request/response payloads; prompts, analyses and hypotheses; mother-model plans and free-text errors; private controller/engine source; program and executable bytes; command templates; logs and cache keys; protected and held-out inputs/expected-output bytes; corpus contents; source-file lists; private static-scan explanations; process inventories and lock/cache contents. The original archives remain preserved locally. The 16 October controller-overhead projection elsewhere in the repository is unchanged.

## Original source fingerprints

The following are original source names, byte lengths and SHA-256 fingerprints, not links to private files. All sources were read only. The builder accepts explicit local source directories and refuses to overwrite an existing projection.

| Source | Original bytes | SHA-256 |
| --- | ---: | --- |
| `index-campagnes.json` | 122,255 | `6b0702cfc0f607ac073ce72f34df1f98ecaa65eff1753809d495a92059505d2b` |
| `cpu-lots.json` | 24,654 | `7594c501185a25e177ff8f304b2f49f2ef738d69d55ef62b12670218e5f6f7eb` |
| `cpu-campagnes.json` | 139,402 | `e96ba8da5937783e75cf4e40d81b2d2d00b279e55562c6b22ca876c93fa7797e` |
| `historique-preserve.json` | 6,530,756 | `049d0bb6a99762f41ba648579c7310cc27277793c1c5cd3037823395669de8cb` |
| `cpu-mesures-brutes.csv` | 3,382,737 | `bb4d281fa388f39624da0bba667a6804ba1f466c2af147aef0527b66ccdbba8a` |
| `confirmations.csv` | 67,896 | `7b65aaea535bf0e1d141eb79e9a5f9d7670dee209871ea5b8d70f6fd8db53716` |
| `cpu-comparaisons.csv` | 1,131,047 | `321bb4eb049d7a894a48d1ff77355e73ac45bf7885be818394b1393f39cd3364` |
| `registres-recalcules.json` | 70,882,791 | `539c9324d72884efd9feea11906d07bf4f057450d96a846f5ec6506782743deb` |
| `couts-astra-xhigh.json` | 61,216 | `7fde70ef04e343890fbfb67cc20f320e8344179aedb760c0b7ff433f6ec390fc` |
| `couts-gpt96.json` | 79,342 | `e6f9453c263eff3b42916758f46b11718a2a276327d3227d56ee15ab229b23e4` |
| `couts-luna-xhigh.json` | 80,245 | `173665429ae5d21e30ce5515925acfe08a77b6b650a685547fa3542298faacd9` |
| `couts-natifs.json` | 794,311 | `1774a55fa533645365093e9365114cd15baab6ecb6b8e0ce0f9b9e9c06fa4638` |
| `couts-sol.json` | 57,948 | `23172b4811b9b440e5002b227453bc688267b8e95453a0c355aecff76d711d49` |
| `couts-source-only-astra.json` | 49,720 | `a78956798c50536f163866353df9fb4f4b16652759a7a8d81424a4d1448d1d24` |
| `couts-source-only-sol.json` | 147,910 | `60d47ea880756ba3ab235bb4dbef7b6a8d8278f33b754f31b8421229b9e053e2` |
| `couts-source-only-terra.json` | 40,220 | `feddc01439e932bc2c55dda53bbdb2b0e3c26e043bae8f2f0d385081f9b1ddc4` |
| `couts-source-only.json` | 71,871 | `101a951d6fab9e3a13f5a3756a515bd884457531789f2b39589ca2b71f2302fe` |
| `couts-terra-xhigh.json` | 65,508 | `137aca42896384aea3d9cd6d3d30f3c698c2a3232e42b31488555e30bc579df6` |
| `couts-terra.json` | 33,656 | `ece20a785d4a22280f6668a70d3f54b54a6190256466b17f4faa672937be67ad` |
| `AUDIT-NATIF-FINAL-SOL.json` | 14,735 | `b8bfd8c55dc0c4b02bed058cb58e17178400fa026cd53655ec987af0f8e0222e` |
| `LIBERATION-SCIENTIFIQUE-SOL.json` | 4,554 | `ce06f8435526826051e66adc3f779436aeb97c7204c6b1f3a89a58bc9cb7efb0` |
| `AUDIT-EXTERNE-PAIRE-GELEE.json` | 2,731 | `86da0f5789ed1f6c9926289d92d198b4c2399626df5664afb58a9d6d3a71913a` |
| `CLOTURE-TROIS-ALLOCATIONS-SANS-NATIF.json` | 9,760 | `4deb4fa3558554c6de03d82f6b2e64f21ae780374141fde5a3ee45c8d0d1b43b` |
| `SUIVI-TECHNIQUE.json` | 8,503 | `08ea8b0f218877cd0ed5ebcf417c2c5ea016ded488296a3f3d9442c2b4c6ad76` |
| `RESULT-EXTERNAL-FROZEN-PAIR.json` | 9,411 | `7ae8050cb89942a1e01f94740216f166217e7234a9bf58906f681f2d49de3c2e` |
| `RECEPTION-FINALE-ET-CLOTURE-VERIFIEE.json` | 3,717 | `d4c74352d28555ba3a476273af51b1d7791c328fa37addcee580318aedbc6df4` |
| `ARTICLE.md` | 59,829 | `6f6b31a79a7b817964893de81036d8e9b0f317b31f2c061056624f5ad6db21b9` |
| `audit-calculs.json` | 1,663,894 | `f5348f8f4d6035bce4cbf3c1587da1c5c3b99ec6b1a9b8e2d6b772b63e1fae28` |
