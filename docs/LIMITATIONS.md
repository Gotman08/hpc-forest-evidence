# Limits of the current evidence

_Statements that the present release does and does not support._

## 📊 Scope of the observations

The controller measurement supports a descriptive reduction of about 26% in cycle bookkeeping time on two finite fixed-response designs. It contains zero model calls. It does not establish better candidate selection, generated-code quality, inference speed or end-to-end search efficiency.

The core-scaling measurement supports the reported timing curves for the released frozen executables and inputs. N-body scales strongly on its largest case; the three other largest cases remain close to flat. This does not prove a universal property of the problems or the systems that selected those programs.

These experiments address different questions and were performed separately. The CPU results cannot be credited to a later controller change. No general causal advantage of an undisclosed implementation is claimed.

## 🧪 Experimental independence

Five launch timings of one executable estimate timing dispersion, not variation between independent optimization searches. The three controller seeds do not become real-model searches. Original program searches are historical and are not distributed as a complete matched causal experiment here.

Independent matched runs, multiple subjects/seeds and equal observable assistance are needed before making stronger system comparisons. No ranking of models or universal superiority is established. A mean conditional on successful runs must not be presented as all-run performance.

## 🖥️ Hardware and timing

The original CPU allocation uses ARM64 with verified physical affinity. It may share a node; frequency/cache effects are not locked. The exact CPU model and maximum RSS were not recorded in that CPU batch. Sixteen GiB is a requested allocation, not an observed memory footprint.

Process launch, program I/O and resource-counter granularity matter, especially for millisecond cases. `CPU seconds / wall seconds` estimates average occupancy and is not an exact thread count. Compiler settings or an OpenMP flag alone do not establish multi-core execution.

## ✅ Correctness, openness and provenance

The original audit compares exact outputs on archived finite cases. That does not certify all legal inputs, strict fidelity to a required algorithm, MPI/multi-node/GPU behavior or official contest compliance. The adapted target is not an official competition ranking.

Internal engine code, original evaluated executables and protected inputs are not distributed. The public verifier therefore checks data integrity and calculations rather than independently re-executing correctness or the original timings. SHA-256 hashes identify bytes; without a trusted source or retained commit they do not authenticate an experiment.

## 🧭 Unexecuted work

Real-model comparisons of the new controller and weight-learning experiments have not produced admitted outcomes in this release. Prepared plans, local format tests or a downloaded tokenizer are not learning results. A lower training loss alone would not establish faster correct programs. Future work must preserve training/validation/test separation and include its additional costs.
