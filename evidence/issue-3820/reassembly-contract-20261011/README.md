# Frozen capture obligation dependency floor — source3820

Existing PR3831 adds an operational reassembly contract to the CLI recorder and
existing input snapshot. It binds canonical obligation manifest and complete raw
byte inventory hashes, identities for every original obligation/gap, and one
conservative all-captured-input range dependency floor. Any conflicting frozen
contract fails before snapshot/sidecar writes or provider evaluation in both
compare and evaluate. No snapshot identity or captured source is repaired.

This is **not a semantic partition plan**. It does not classify native proof
relationships, recover unavailable/truncated artifacts, execute partition arms,
change judges/output reserves, or establish source3820 acceptance. All original
capture insufficiency and gaps persist. Every obligation conservatively depends
on all ranges until a later planner proves narrower cross-proof packages.

## Observed verification

- New tests on original source:9failed/76passed. Added an independent identity
  revision control before final verification.
- Candidate focused suite:86passed. Production equality guard disabled:
  8failed/78passed; exact-byte restoration:86passed. Raw JUnit/console and
  source hashes retained in contract-mutation.json. Only the operational guard
  was disabled; tests were unchanged across RED/restoredGREEN.
- Related recorder/capacity/recovery/prompt/comparison/template suites:
  4276passed/19skipped (18 Anthropic API contracts,1owner-local capture).
- Full Black699files, touched Ruff, source/template byte parity and diff check pass.
- Offline original run38118258124 snapshot context/diff hashes independently
  verified. Contract retains277obligations,163gaps,60ranges and sufficient=false.
  No provider invocation. Context contains clipped changed-code views despite
  separate full diff bytes; immutable byte binding does not upgrade that coverage.

## Reproduce

```sh
python3 -m pytest tests/tools/test_verifier_capture_obligation_manifest.py tests/scripts/test_pr_verifier_capture_obligation_failure.py -q
```

For the production mutation, replace the recorder's existing-contract condition
`if "capture_reassembly_contract" in snapshot and json.dumps(` with
`if False and "capture_reassembly_contract" in snapshot and json.dumps(`,
run the same focused suite, restore the exact original source bytes in finally,
and run again. Do this in an isolated checkout. Raw execution argv/cwd/exits and
before/mutant/restored SHA256 are in contract-mutation.json. Manifest.json binds
all retained evidence; original authenticated capture was read only.

Original/mutant console and JUnit are preserved byte-identically in
raw-red-evidence.tar.gz; archived member hashes retain their original identities.
