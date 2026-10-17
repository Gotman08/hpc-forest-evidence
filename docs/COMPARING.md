# Compare another system

_A practical route from an independent implementation to comparable evidence._

## 📋 Freeze a comparison plan

Copy the [blank templates](../templates/README.md). Assign neutral system/configuration IDs and keep a stable mapping to your own implementation. Record the source revision or confidential implementation digest, exact model/effort if relevant, assistance rights, budgets and stop rules. The internal architecture need not be disclosed, but the observable experimental conditions must be.

The published CPU and controller datasets are retrospective observations. They do not automatically become matched controls for your new run. For a controlled comparison, run both systems afresh with matched subjects, seeds, target resources, input contracts and evaluation rights. Preregister the order before observing outcomes.

## 🧪 Prepare and run the benchmark

Use the [external protocol](PROTOCOL.md). Obtain or create an appropriately licensed benchmark, freeze its reference and exact output contract, and qualify it on your target. This repository does not provide a ready-to-run fifteen-subject benchmark bundle or protected confirmation inputs.

Keep development/confirmation data outside the evaluated system’s readable environment. Give every system the same feedback contract. Separate inference hardware and costs from candidate-execution hardware. Use a fresh context and reference for every independent search, without importing past winning candidates.

Run under the declared limits. Preserve source and binary digests, raw timings, correctness results, known/missing counters, errors, duplicates and stop causes. Freeze finalists before separate confirmation. Several timing repeats of one binary are still one search outcome.

## 📦 Return the evidence

| File | Required information |
| --- | --- |
| Experiment plan | Subject/system/configuration/seed, frozen source/contract, budgets, rights and schedule |
| Environment | Requested/allocated/observed resources, target, compiler, flags, affinities and inference visibility |
| Raw timings | Per-launch phase, program identity, repeat, elapsed time, correctness and exit status |
| Outcomes | Confirmed gain, retained reference, rejection, missing confirmation, incident or not run |
| Provenance | Digests linking the data to source, executable and evaluation contract |

Keep actual binaries and protected inputs under the evaluator’s control. Published timings should use the least revealing identifiers that still support their stated claims. Do not upload credentials, live sessions or other systems’ private artifacts.

## 📊 Interpret the comparison

Compare each candidate to the reference timed in its own confirmation series. Present both absolute durations and normalized ratios. Retain paired subject/configuration/seed results, all denominators and unproductive search costs; do not pool raw timing means from unrelated allocations.

A missing or unqualified outcome is not a zero gain. A retained reference after usable search/confirmation is a valid zero-gain observation. If target hardware, assistance rights, model service or execution time differs, declare the confounding factors and limit the conclusion accordingly.

New evidence may be proposed in a pull request with its preregistered plan and complete negative outcomes. A contributed dataset is a separately identified cohort, not an overwrite of this release. Maintainers must verify provenance and recompute its claims before accepting it.
