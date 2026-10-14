# Acceptance-source discovery admission guard

Source #3820, existing PR #3831. Production context builder always emits
`acceptance_source_discovery`, but deleting the record or using a false required
flag with unavailable/truncated/unknown discovery previously admitted a complete
capture. Missing status with required=false also passed. This could reach native
counting/generation with an unknown acceptance-source set.

The manifest now requires a record, an explicit Boolean required flag and included
status, regardless of whether linked issues are required. Valid required=true and
required=false included cases remain admitted. Every existing capture gap remains;
source/template copies are identical. Expanded fingerprint advances v9 to v10;
standard v2, provider selection, workflow permissions and secrets are unchanged.

Original source: 11 assertion failures, 8 passing controls. Reinstalling the actual
HEAD production module as a deliberate mutation: 11 failures, 8 passing controls;
byte-identical restoration: 19 pass. Integration controls exercise both evaluate
and compare, requiring no native count or generation on incomplete discovery.
Raw logs/JUnit, command arrays and source/restored hashes are in proof.json.

Final bounded suite: 826 pass, 18 provider-inapplicable cases skipped. Capture,
resource, partition, native capacity/registry, expanded comparison, profile,
sync-manifest, template allowlist and guide tests pass. Template sync/drift,
Black/Ruff and diff checks pass.

This proves the local admission guard. It does not recover original missing proof,
establish semantic partition closure, execute native providers, complete hosted CI
or grant source #3820 acceptance. The key remains active and source stays open.
