# Capture failure CLI boundary acceptance

Current repair preserves structured FAIL for rejected captures in evaluate and compare modes, with zero provider evaluation. It fixes the new regression file's Ruff import ordering/Black formatting, propagates the production failure handler to the consumer template, and aligns snapshot identity/ambiguity integration tests with the report contract.

Validation: six focused suites, **447 passed, 19 skipped**. The skips are 18 Anthropic Models API parameter cases and one owner-local authenticated capture. Real module CLI runs (invalid UTF-8 and corrupt JSON snapshot, evaluate and compare) each exit 0 with JSON verdict FAIL, used_llm=false and a durable report file. Exit 0 is CLI/report completion, not verifier PASS.

Production mutation: re-raise validation exceptions instead of emitting FAIL -> **13 failed, 18 passed**, exit 1. Byte-identical production restoration -> **31 passed**, exit 0. Raw logs and source hash are adjacent. Snapshot tests exercise both modes and preserve unchanged rejected snapshot bytes with zero evaluation calls. Full Black, Ruff and template synchronization checks pass.

This accepts only the capture failure reporting boundary. Source #3820 remains open: lossless partition/all-arm recovery, missing required proof retrieval and authentic native complete-input acceptance are still pending. No provider verdict, native fit, source acceptance or deployment is inferred.
