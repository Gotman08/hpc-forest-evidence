# External evaluation protocol

_Version 1.0 · 16 October 2026 · independent of the system’s internal implementation._

## Experimental unit and common conditions

One experimental unit is **one subject × one system configuration × one seed × one frozen evaluation contract**. Multiple timings of the same executable describe timing dispersion; they are not multiple independent optimization searches.

| Item | Main comparison profile |
| --- | --- |
| Starting point | Frozen reference program; fresh context and directory |
| Seed | 23 for the main profile; preregister additional shared seeds |
| Search budget | 1,800 s; 1,500,000 tokens declared for a model-based system |
| Final reserve | 120 s preserved within budget management |
| External program deliveries | At most eight, each generation request bounded to 600 s |
| Candidate execution target | Linux ARM64; four allocated CPU cores; 16 GiB; zero GPU |
| Search correctness | Three frozen development cases |
| Search timing | One excluded warmup, then three timings |
| Final correctness | Three distinct confirmation cases and the timed input |
| Final timing | One warmup, then five interleaved repetitions per admitted program |
| Gain admission | Exact correct output and at least 3% lower mean runtime |

The resource profile describes candidate execution, not the inference provider’s hardware. Record inference resources separately as observed, unknown or unavailable. A ceiling or reservation is not observed consumption; internal model calls are distinct from external program deliveries. Report missing token counters instead of inventing exact totals or claiming a hard token cap from an after-call counter.

## Prepare before generating candidates

Freeze source, statement, input/output contract, compiler flags, environment, time limits and case digests before the first search. Identify each system by a stable configuration ID; the internal implementation may remain confidential. To isolate the effect of one system change, keep model identity, effort, assistance rights, transport and budgets equal.

Compile and check the reference on the actual target. A reference that cannot reproduce the expected outputs is a preparation incompatibility, not an algorithmic failure by the evaluated system. Do not loosen its oracle or introduce compiler initialization to force compatibility.

Keep evaluator inputs and expected outputs outside the evaluated system’s readable environment. A folder name is not access isolation. If the system can read protected cases, record the exposure; those cases cannot support a claim of unseen confirmation. Publish a benchmark-specific input policy before the run. This repository does not distribute protected cases.

The historical candidate corpus contains fifteen subjects from the 2020–2023 Parallel Programming Marathon, listed in the [French protocol](PROTOCOLE.fr.md). Exact benchmark preparation must be supplied and qualified separately. Official problem statements remain the authoritative source for their original requirements.[^1]

## Run and confirm

1. Create a fresh directory, context, session and record. Use the frozen reference, with no candidate inherited from an earlier winning search.
2. Start the declared budget. Record deliveries, known consumption, errors and stop causes. An operator does not advise on algorithms or repair candidate code.
3. Preserve each candidate’s bytes and digest before compiling. Use the same compiler and flags as the reference, within the frozen time limits.
4. Compare output bytes exactly. Do not add rounding tolerances, remove headers or silently convert binary output. An exit status of zero is insufficient.
5. For valid candidates, perform the excluded warmup and three timed launches. Declare before the run which development feedback the system may receive and give both systems the same rights.
6. Freeze finalists and close the search before protected confirmation. A rejected final confirmation does not reopen optimization.
7. Recompile the reference and finalists under the same contract, verify confirmation outputs, then warm each executable once. Run five rounds, each containing every admitted executable including the reference, in shuffled order. Archive the initial list, PRNG seed/version and actual order.
8. Preserve raw timings, outputs or output digests, binary hashes before/after, exit status and resource counters. A missing confirmation remains missing rather than becoming a zero gain.

The historical confirmation convention initializes `random.Random(24)` once for the first confirmation phase, then shuffles anew each round without reseeding. The actual order remains part of the evidence. New comparisons should preregister their schedule; this convention does not recreate every past run automatically.

Measure elapsed wall time around the complete target command. Preserve which setup, file-opening, compilation and I/O costs are inside or outside each timer. Compilation and correctness checking still consume the search budget even when excluded from program runtime.

## Calculate and report

Let `T0` be the mean of the five reference confirmation timings and `T` the mean of the candidate’s five timings, from the same series:

| Quantity | Formula |
| --- | --- |
| Time reduction (%) | `100 × (1 − T / T0)` |
| Speedup versus reference | `T0 / T` |
| Seconds saved | `T0 − T` |
| Timing dispersion | Sample standard deviation, divisor `n − 1`; also report median |

A reference retained after usable search and confirmation has 0% admitted gain. Incorrect output, a missing confirmation, an infrastructure failure and an unexecuted cell are different outcomes. Keep them separate with explicit denominators. Retain failed compilations, duplicate proposals, rejected confirmations and their costs.

Compare independent searches by matched subject/configuration/seed and contract. Keep both reference durations visible. Do not pool raw means across allocations or treat only-success averages as all-run performance. Several independent searches are needed to assess stability; five timings of one binary do not provide that replication.

## Optional core-scaling diagnosis

Core scaling is a separate post-hoc experiment on already received and audited programs. Freeze the executable bytes and input. Allocate sixteen distinct physical CPU cores, 16 GiB and zero GPU; check physical topology and inherited affinity. Test accessible counts 1, 2, 4, 8 and 16, with coherent thread settings, an excluded warmup and five interleaved repetitions.

For the same binary and input, `S(p) = T(1) / T(p)` and efficiency `E(p) = S(p) / p`. These are distinct from speedup against another reference program. CPU/wall time is an occupancy indicator, not an exact thread count. Preserve flat curves and incorrect/incomplete cases; do not start another optimization search because a curve is disappointing.

## Returned evidence

Use the [blank templates](../templates/README.md). Return the frozen plan, environment, raw timings, code/binary digests, correctness evidence, schedule, actual costs, stop causes and final outcomes. A reviewer can compare these without receiving an internal orchestration design. The [comparison guide](COMPARING.md) gives the practical steps.

[^1]: Parallel Programming Marathon problem statements: [2020](http://lspd.mackenzie.br/marathon/20/problemset.pdf), [2021](http://lspd.mackenzie.br/marathon/21/problemset.pdf), [2022](http://lspd.mackenzie.br/marathon/22/problemset.pdf), [2023](http://lspd.mackenzie.br/marathon/23/problemset.pdf). These are archival source references; continued availability is not assumed.
