# Issue 3883: filename-qualified quantified destinations

Bounded evidence-source filename qualifiers (`evidence from results.json`,
including quoted filenames) no longer hide a following quantified destination
list. `both in a PR comment and in an artifact` requires every named destination;
`either in a PR comment or in an artifact` accepts one alternative. Bare
`in an artifact` destinations normalize to the shared workflow-artifact channel.
Actor, polarity, optionality, product-capability and quoted-example scope are
unchanged. Independent reviewer duties remain separate obligations.

## Focused gate

```sh
python3 -m pytest tests/scripts/test_pr_verifier_delivery_destinations.py -k issue3883 -q
```

Recorded local result: **11 passed** (exit 0). Source/template verifier SHA256
`ce08477f4ea21999f2f3072cf3a7f7e73a364c37427f7705bc0aab1dd3d6e9a0`.

## Deliberate RED/GREEN replay

```sh
python3 docs/evidence/issue-3883-filename-qualified-destinations/replay.py \
  --output /tmp/issue3883-proof
```

Use a clean checkout and a **new** output path. The replay removes both
`_normalize_evidence_source_filename_qualifiers` call sites from the source and
consumer-template verifier copies, runs the three core issue3883 destination/floor
nodes (expect exit 1), restores exact fixed bytes, then reruns the same nodes
(expect exit 0). It refuses an existing output directory and restores fixed bytes
in `finally`.

Recorded local receipt (`receipts.json`): RED exit **1**, GREEN exit **0**,
restored hashes match the fixed source/template digest above. `manifest.json`
binds every archived output member by SHA256; `red.stdout` / `green.stdout` are
retained beside the receipt.

These results prove the local classifier and coverage-floor behavior for the two
issue examples. They do not establish hosted CI acceptance or consumer promotion.
