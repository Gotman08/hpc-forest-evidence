# Native R2: first audited batch

This is the first received search batch for **2020-quicksort / gpt-6-luna / MAX / seed 23**, job 755562. The source cutoff is **19 October 2026, 11:11:41.348 UTC**, when ARM acceptance of the audited release was observed. The private audit itself is dated **11:09:30.683709 UTC**. The [closed public projection](first-batch.json) preserves the exact received durations, costs, provenance digests and limits.

The first batch was delivered, checked privately and released for continuation before its existing search deadline (11:13:04.369661 UTC). This is an initial search observation. It does not establish final confirmation, a scientifically admitted gain, completion of the cell or campaign, or launch of the other 59 planned cells. The [r4 matrix](../received-2026-10-19-r4/matrix15.csv) remains the historical 08:40 UTC snapshot, with its R2 missing values unchanged.

## Exact initial measurements

The reference was measured in this same allocation; the earlier zero-model qualification timings were not imported. Both rows below contain the three search timings, in seconds, rather than final confirmation timings.

| Program observation | Sample 1 | Sample 2 | Sample 3 | Mean |
| --- | --- | --- | --- | --- |
| Contemporary reference | 0.07028694730252028 | 0.07024739496409893 | 0.07020761910825968 | 0.07024732045829296 |
| First delivered optimization | 0.06142141669988632 | 0.06124462094157934 | 0.061352682299911976 | 0.06133957331379255 |

The descriptive reference/optimization mean ratio is **1.1452202332567816**, a **12.6805507831%** reduction in these initial measured runtimes. No final five-pair confirmation is received in this supplement, and no scientific gain is admitted. The original evaluator reports `status=valid` and `correct=true`; this is the original evaluator's observation under the limits below.

The outcome's separate recorded search score is **0.5338473950146169**. It is retained as a recorded value and is not the ratio against this contemporary reference. Public verification recomputes the duration means, sample standard deviations and descriptive ratio without interpreting that score as a confirmed speedup.

The allocation is aarch64, one node and task, four CPUs with affinity count four, 16,384 MiB, and zero GPUs. The R1 contract digest is `c2fa077535e04b8d3f65ca4e4705ba178b55de6513aa4d1f071374bf9a776a16`; the protocol identifier is `afc54473852a57f801fb42d776195f1ccbcce7949ed8cda85a76d685ae115392`.

## Calls, tokens and private audit

| Delivered role | Exact tokens |
| --- | --- |
| Mother preparation | 15,629 |
| First optimization | 17,136 |
| Total: two delivered calls | 32,765 |

Usage is exact for both calls. Reserved tokens, unknown-usage calls and bounded-usage calls are zero. The registry records three slots; this is not a count of three model calls. The audit and release validation did not add a model call or reset the budget or chronology.

The private review reconciled the received raw files, the CLI invocation projections and local policy, with clean diagnostics. Its proposal receipt has SHA-256 `47c230711a7c6c3757c1495996a2c1be36b7b5afa21530541df37d4de422eb54`; the source-127 release validator passed. The later ARM acceptance receipt has SHA-256 `60f1bb327a0caa9fbf3d873cf7a4ab967db234728832de9a2f03206798e10c87` and binds the same audit, digest projection and release. Acceptance records zero replayed claims and no budget or chronology reset.

The historical paused snapshot is preserved separately from this later acceptance. Its `release_installed_at_audit=false` describes the earlier audit stage, not the subsequent ARM acceptance.

## Instrumentation and operational incidents

The evidence level is **command-stream-v1**: six command records for the initial optimization and six for its current-allocation reference (build, check, warmup and three samples). There is no case-v2 claim, independent per-case provenance, independent raw stdout verification per candidate, independent performance audit, or independent SQLite snapshot re-audit. These flags remain false after private CLI validation and ARM acceptance. The public checks validate the projection and arithmetic; they cannot reproduce the private correctness or performance execution.

The audit reader's r2 handling explicitly binds the external `/bin/sh` alias to a real frozen copy and manifest received by SCP. A separate zero-model copy job, **755597 on romeo-a057**, copied **1,366,952 bytes**, with SHA-256 `7e3a3f9d6715ccab40ba328d2220f59f70133ac164ac491a07c5cff2dc035753`. The reader can therefore verify that dependency without changing the engine, original command traces or deadlines. Neither the binary nor the audit reader implementation is distributed here.

Earlier job **755550** failed before admission and before the scientific clock or any model call: the initially empty `CUDA_VISIBLE_DEVICES` value was absent after `srun`. Diagnostic job **755551** completed with exit code `0:0`, restored the empty value inline and passed the original interpreter guard with zero model calls. The native source ZIP remained unchanged at SHA-256 `b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4`. This bootstrap incident adds no scientific result.

The public transformation extracts approved scalar measurements, role-level accounting and digests. It excludes private source and candidates, prompts, argv, skills and their paths, census/configuration, account and session paths, private inventories, command streams, protected inputs, and raw files. Hashes identify the retained private evidence without distributing its contents.

Run `python -m tools.verify` and `python -m unittest discover -s tests -v` from the repository root. The [reproduction guide](../../docs/REPRODUCIBILITY.md) explains the boundary between arithmetic verification and experimental reproduction.
