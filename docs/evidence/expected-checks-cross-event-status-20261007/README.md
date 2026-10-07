# Cross-event Gate status evidence

The unchanged current-main source yields PASS for the pull_request receipt but UNKNOWN for the same-head pull_request_target receipt because its Gate publisher is excluded by event. The candidate separately collects the latest exact-head pull_request publisher for status provenance, preserving all existing authentication/attempt/step-time checks and target-event topology. The candidate live receipt is PASS. Raw receipts are losslessly gzip-compressed; their original verdicts remain unchanged.

The standard local verifier reports command RED1/GREEN1 for the named regression. Its per-node warning identifies241/243 existing/control nodes as nondiscriminating; no all-node mutation proof is claimed. Full reporter suite243PASS. Baseline/candidate source and test byte identities plus artifact hashes are in manifest.json. No provider result, remote protection, workflow permissions, source publication or runtime activation changed.
