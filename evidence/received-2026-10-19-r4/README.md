# Received r4 supplement · 19 October 2026

This supplement records the technical state received at **2026-10-19T08:40:00Z**. It leaves the [historical received projection](../received-2026-10-19/README.md) intact, with its scientific cutoff of **2026-10-18T05:03:23.898140+00:00**. It adds no new scientific gain, completed R2 matrix cell or model ranking.

| File | Scope |
| --- | --- |
| [summary.json](summary.json) | Received r4 counts and scope |
| [provenance.json](provenance.json) | Source fingerprints and public projection provenance |
| [operational-status.json](operational-status.json) | Failed A2/A3 attempts, local validation and A4 preparation |
| [matrix15.csv](matrix15.csv) | Fifteen subjects × four models at MAX, seed 23: sixty cells |

The matrix retains all sixty R1 historical references. All sixty R2 results remain `NA`, with **zero R1/R2 pairs**. Eleven measured R1 zero gains retain the reference program (speedup 1); these measured outcomes remain distinct from missing R2 results. Primes is outside these fifteen subjects. The [current campaign instruction](../../docs/RECEIVED-2026-10-19.md) uses the completed Sol pilot once before this matrix; the frozen r4 article preserves the earlier four-primes plan as dated history.

The exact r4 [article PDF](../../docs/article/ARTICLE.pdf) has 19 pages and SHA-256 `8a688dbf70446d769a60f0c88e53f83039808c4f8270f9526de0150b645a7459`. The [appendix PDF](../../docs/article/ANNEXES-TECHNIQUES.pdf) has 308 pages and SHA-256 `0c0980d69b9e677b387d49222956e118e1b25d5f5c80d40966ed95ef891f2295`. Markdown sources, [article HTML](../../docs/article/ARTICLE.html), [appendix HTML](../../docs/article/ANNEXES-TECHNIQUES.html), all 275 figures and [article provenance](../../docs/article/provenance.json) accompany them. Earlier editions remain in Git history.

Sol R2h remains the completed supplement already received: three calls, 59,037 exact known tokens, twelve certified inputs and five timing pairs on a separate allocation. Its 8.927268770813551× ratio uses the same evaluator and timer; it does not establish independent evaluator implementation or universal correctness.

A2 preserves 21 partial files and zero native calls. A3 preserves 78 files, including three corrupted authorization files, with zero workers, native calls, tokens or scientific results. Its ASCII JSON fix is validated locally only, with 23 exact hashes and UTF-8 byte lengths after decoding the actual Astra package. No remote authorization repair or successful new transport is established. A4 is preparation only, with zero `plan_job`, `submit`, `pass` or worker events at the cutoff. See the [operational incident account](../../docs/OPERATIONAL-INCIDENTS-2026-10-19.md).

Private implementation, prompts, credentials, account paths, evaluated binaries and protected inputs are not included.

## Cost counter scopes

The matrix names two different views explicitly: r1_archived_unmetered_native_invocations comes from the original archived comparison audit, while r1_received_reconciled_unmetered_calls comes from the complete received historical ledger. Three cells differ: count Astra (0 versus 1), count Terra (1 versus 2), and npbonacci Terra (1 versus 2). The received view includes later original deliveries absent from the initial archive; exact known token counts and measured timings agree. These are different accounting scopes, not newly generated calls. In particular, the npbonacci expired request without invocation evidence is not counted as an invocation. Both counters and their source fingerprints are preserved in [provenance.json](provenance.json). Use the reconciled ledger for received costs; an archival zero does not establish zero unknown consumption.
