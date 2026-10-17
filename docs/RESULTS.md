# Results and interpretation

_Observed on 16 October 2026 · two distinct experiments · no model ranking._

## Controller overhead

The controller dataset uses four anonymous implementation variants. `kernel-A`/`kernel-B` compare two narrow kernels; `system-A`/`system-B` compare two policies within the same larger processing pipeline. The pair types perform different work and must not be mixed into a claim about whole-system speed.

All variants receive the same fixed synthetic score/response traces per seed and series length. No model or target HPC program runs in this experiment. This isolates a finite controller cost; it cannot measure whether a policy chooses better candidate programs.

| Cycles per series | System A, ms/cycle | System B, ms/cycle | Time reduction | Saved per cycle |
| --- | ---: | ---: | ---: | ---: |
| 8 | 8.739869 ± 0.323888 | 6.486806 ± 0.245103 | 25.7791% | 2.253063 ms |
| 32 | 10.132615 ± 0.222798 | 7.498647 ± 0.251914 | 25.9950% | 2.633969 ms |

Each mean summarizes fifteen series: three seeds (23, 29, 31), five measured repetitions each. `±` is the sample standard deviation of the series means, not a confidence interval. One warmup series per seed/design/variant is excluded. The complete dataset contains 144 series: 24 warmups and 120 measured series, totaling 2,400 measured cycles. Initialization is outside the cycle timer; the synthetic payload is 2,048 bytes.

The narrow kernel pair gives 2.615644 → 2.124604 ms/cycle at eight cycles, and 3.106646 → 2.799148 at 32. These reductions are 18.7732% and 9.8981% respectively. They do not imply that the complete pipeline is faster than the narrow kernel.

This result is a difference of milliseconds in bookkeeping. It is not a 26% improvement in model inference time, total research cost or the runtime of a generated program. The mean ratio `A/B` is about 1.35; the **time reduction** `100 × (1 − B/A)` is about 26%. Those percentages must not be interchanged.

## Core scaling of frozen programs

The CPU dataset contains **all four largest cases** from one audited allocation, including the cases with near-flat scaling. It is an explicit 200-timing subset of an original batch with 1,400 timings. Two binaries per subject, five core counts and five repetitions give 40 public configurations. No timing is duplicated as an independent execution.

| Selected program / largest input | Mean at 1 core, s | Mean at 16 cores, s | Same-program speedup | CPU/wall at 16 cores |
| --- | ---: | ---: | ---: | ---: |
| Bucket sort / 65,536 strings | 0.009479 | 0.009151 | 1.0359× | 0.8558 |
| k-NN / 98,070 points | 0.022111 | 0.021662 | 1.0207× | 0.9623 |
| N-body / 4,096 bodies | 0.667466 | 0.046426 | 14.3769× | 14.7405 |
| Sum / matrix side 1,024 | 0.006436 | 0.006051 | 1.0636× | 0.8353 |

The same executable bytes and input digest are held constant along each curve. Physical affinities 1/2/4/8/16 are checked; the allocation requests sixteen physical CPU cores, 16 GiB and zero GPU. Each configuration has one excluded warmup and five interleaved measurements. Wall timing includes process launch and program I/O; temporary-directory creation and input-file opening precede the timer.

`S(p) = T(1)/T(p)` describes scaling of a single program. `Treference(p)/Tselected(p)` compares different programs at the same core count. For N-body at sixteen cores these are 14.3769× and 14.3600× respectively, distinct despite their similar values. Both ratios are recalculated in [results.json](../evidence/results.json).

CPU/wall is the mean of per-launch CPU-seconds/wall-seconds ratios. It indicates average occupancy, not the exact number of threads. For short cases, process-launch costs and counter granularity can dominate. Flat curves do not prove that parallelism can never help those problems.

The selected executables came from earlier searches. **No new optimization search, code edit or compilation took place in the core-scaling allocation.** The dataset does not contain those earlier search trajectories or their complete costs, so it cannot support a model-efficiency comparison. These curves are not an ablation of the controller variants above.

## Validation and provenance

The original controller archive was received, restored into a fresh directory and checked before/after a read-only audit: 2,243 files, including 541 project sources. Its project suite has 196 passing tests and one optional skipped MCP check; the measurement suite has seven passing tests. The public verifier has its own tests; these counts describe different codebases.

The original CPU batch audit covers 280 configurations and 1,400 timings, with exact archived output checks and no incomplete configuration. This release exposes only its largest-case subset, not the protected inputs or original binaries. The associated integrity/audit claims are **reported from the original operator audit**, not independently re-executed by the public verifier.

Original archive SHA-256 identifiers and the exact public projection are recorded in [controller provenance](../evidence/controller/provenance.json) and [CPU provenance](../evidence/cpu-scaling/provenance.json). [Reproducibility](REPRODUCIBILITY.md) describes what readers can check directly.

## Still unproven

No real-model matched result demonstrates a quality improvement from the new controller comparison. No weight-learning result is available. No general superiority, exact thread count, full-domain correctness, official contest rank or universal speedup follows from these datasets. Read the [limitations](LIMITATIONS.md) before reusing the numbers.
