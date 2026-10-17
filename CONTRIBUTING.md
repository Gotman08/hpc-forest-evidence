# Contributing

_Keep every claim connected to a concrete observation and its provenance._

## Useful contributions

Report a reproducibility problem, improve an explanation, add a meaningful rejection test, or propose an independently collected comparison. Identify the affected release/commit and include the smallest public example that supports the issue.

New data should arrive as a separate named cohort with a frozen plan, actual environment, raw observations, complete negative outcomes and provenance. Do not replace older observations, alter an oracle after seeing failures or present an unexecuted plan as a result. Keep confidential implementations and protected inputs outside contributions.

## Local checks

Python 3.11+:

```bash
python -m tools.recompute --check
python -m unittest discover -s tests -v
```

For an intended documentation/code/figure change, review the exact file diff and any disclosure risk first. Then rebuild the file manifest explicitly and verify the whole bundle:

```bash
python -m tools.manifest --write
python -m tools.verify
```

Do not update the manifest to hide unexpected data changes. For a data correction, retain the old release, document the reason and show the before/after calculation. The manifest verifies consistency, not scientific truth.

## Documentation and review

Use plain text in documentation, filenames and GitHub titles. Do not use emoji or emoji shortcodes.

Keep the README concise and bilingual entry points aligned. Put experimental detail in `docs/`, raw evidence in `evidence/`, and calculated plots under `docs/assets/`. Figures must derive from released records and state their units and scope. Conceptual diagrams must be identified as such.

Use a focused pull request with the problem, resulting behavior, data/provenance changes and checks run. CI uses read-only permissions and performs offline verification and tests. No account, model call or private benchmark data is needed for a documentation contribution.
