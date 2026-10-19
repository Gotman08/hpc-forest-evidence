# Native R2: received technical incidents

This later [numeric status supplement](incidents.json) is observed at **19 October 2026, 12:34:58.457867 UTC**. It leaves article r5, its figures and its [numeric comparison](../../docs/article/donnees-r1-r2/comparison.json) frozen at their **11:40:35.931 UTC** source cutoff. It summarizes an earlier Sol failure and the subsequently received Astra failure; it does not claim that both failures occurred after the article cutoff.

| Declared cell | Received technical status | Calls and tokens |
| --- | --- | --- |
| Sol / MAX / 2023-count, job 755766 | Slurm `FAILED` after three seconds; bootstrap failed at 11:38:43.684971 UTC, before admission or model-child launch | Zero model calls and zero tokens |
| Astra / MAX / 2023-count, job 755862 | Allocation admitted; Slurm `FAILED`, exit `1:0`, ended at 12:22:12 UTC; pipeline incomplete and technical first-start verification unresolved | Two delivered calls announced by source cache/responses: 14,753 + 16,166 = **30,919 exact tokens announced** |

Sol failed **before** its original admission deadline, 11:48:43.359950 UTC. That deadline had passed by this supplement's observation; expiration did not cause the earlier failure. No reset or replay is recorded. The three-second scheduler duration is distinct from the shorter bootstrap execution.

For Astra, the generic source `invocation_unknown=true` belongs to technical first-start verification. It is not a classification of unknown token usage and does not replace the exact consumption announced by the source. Model names and MAX effort are declared source metadata. This supplement does **not** claim an independent private CLI audit, final performance admission or independent performance proof, and publishes no Astra timing sample.

The original Astra archive contains **179,031 bytes, 295 members, 190 regular files and zero links**. Eleven of the twelve preceding metadata artifacts are present, regular and bounded; the second delivery receipt is absent in that original archive. A later, separately received copy has **976 bytes** and SHA-256 `9a39db85d915ae2563926541ae1c29607b34a739b871bd39272c355c7eb84004`. All **six requested SCP receptions** were received and verified. Later reception is not retroactively attributed to the original archive. The private receipt basename is withheld; only its public source label, byte length and digest are included.

The sixty-cell inventory now distinguishes **one cell with source-confirmed final timings, two technical incidents and 57 unlaunched cells**. It still contains **59 cells without an included scientific comparison measurement and zero scientifically admitted R1/R2 pairs or new gains**. Missing values are not measured zero gains. This does not mean that Astra made no calls or ran no physical operation: its source search is checkpointed, but no Astra performance timing is included here. The earlier Luna bootstrap incident remains history within that same Luna cell; it adds no extra cell. This operational accounting adds no performance result and does not complete the campaign.

The JSON publishes approved scalar statuses, counts, timestamps and source fingerprints. Private artifacts, source, prompts, configuration, CLI traces and identifying paths are excluded. Verification is offline: `python -m tools.verify` checks this projection and its arithmetic without launching a scientific job or issuing a model call.
