# Received operational incidents · 19 October 2026

The received r4 state has a technical cutoff of 08:40 UTC on 19 October. It includes failed technical attempts associated with Astra, Terra and Luna primes preparation. These incidents add no model result, timing gain or token consumption to the historical scientific aggregates. The scientific cutoff remains 18 October 2026 at 05:03:23.898140 UTC; the [r4 inventory](../evidence/received-2026-10-19-r4/README.md) and [operational status](../evidence/received-2026-10-19-r4/operational-status.json) keep the later technical evidence separate.

| Driver record | Received outcome | Worker starts | Native model calls | Scientific completion proved |
| --- | --- | ---: | ---: | --- |
| Attempt 2 | Dependency publication stopped after the Windows command-length limit; four dependency errors recorded for Astra; Astra 755409, Terra 755410 and Luna 755408 ended `FAILED`; 21 partial files were preserved and verified | 0 | 0 | false |
| Attempt 3 | Authorization publication failed its path/byte-length/SHA comparison; Astra 755433, Terra 755434 and Luna 755435 ended `FAILED` at 08:15:44, 08:15:46 and 08:15:51 UTC respectively | 0 | 0 | false |

Both records report `completed_transport_only=false` and `jobs_submitted=0` for the transport driver's own actions. Existing Slurm allocations and their terminal states have their own records. The table does not infer current process or queue state, successful authorization, or a completed model search from a prepared request. Original payloads, account paths and transport-response details remain preserved privately.

Attempt 3 preserved 78 files, including three corrupted authorization files. Three `allocation-ready` records exist, but the corresponding `authorization-ready` records are absent. The received diagnosis is CP1252-to-UTF-8 replacement during transport. An ASCII JSON output fix was validated locally only: after decoding the actual Astra package, all 23 hashes and UTF-8 byte lengths matched exactly. This proves neither remote authorization repair nor a successful new transport. Attempt 3 has zero workers, native calls, tokens and scientific results.

A4 is preparation only at the cutoff: zero `plan_job`, `submit`, `pass` or worker events. This document records the received state and initiates no R2 operation.

The earlier received driver fingerprints remain recorded for provenance:

| Original record | Bytes | SHA-256 |
| --- | ---: | --- |
| `RESULTAT-TRANSPORT-A2.json` | 21,743 | `2beacb48539768c9773d317c034292c78e8a507fbe47cffce7b239ab4c191062` |
| `RESULTAT-TRANSPORT-A3.json` | 121,821 | `a333432802012ae655005d915d7133ad81a5b0463ab7ca28bb73e8a4365d02d1` |

The [current campaign instruction](RECEIVED-2026-10-19.md) uses the already completed Sol pilot once, before the fifteen-subject MAX matrix. These failed transport attempts remain part of the received history.
