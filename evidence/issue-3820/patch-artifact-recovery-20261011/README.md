# Original artifact recovery and patch text support

Original run38118258124 diagnostics identify11artifact IDs with extraction failures.
All11original ZIP archives were re-downloaded once, metadata/provenance/whole-archive
SHA256 recorded;5,529,267compressed bytes are retained in the automation-owned
`/Users/teacher/.codex/automations/imi-merge-verify-closer/work/20261011T1423Z/original-artifact-recovery/`.
Raw ZIPs are local recovery inputs, not delivered hosted verifier acceptance.

Concrete bounded source defect: all3comparison archives contain the verifier's
own `verifier-pr-diff.patch`, which the artifact text allowlist classified as an
unsupported payload. The source/template extractor now accepts `.patch`/`.diff`
under existing filename safety/entry/byte/character guards. Unsupported siblings
and exhausted limits still prevent completeness. No resource bound was raised.

Two new extraction tests fail on original production; disabling only production
patch/diff allowlisting yields2FAIL; exact-byte restoration yields2PASS. The full
collector suite143PASS. Tests include a real ZIP read, verbatim normalized patch
text, finite character exhaustion, and unsafe wildcard/leading-dash/binary siblings.
Raw console/source hashes/argv/cwd/exits retained; source/template parity verified.

Offline diagnostic re-extraction using explicit32MiBbytes/32MiBchars/100entry
per-archive bounds succeeds for all11archives, totaling118,319,651raw extracted
bytes. This exceeds the operational64MiBglobal extraction bound, and ordinary
per-artifact60000character clipping also remains. It is not operational source
recovery, lossless prompt admission, semantic partitioning, or provider PASS.
The original9truncated+1unavailable obligation records are not relabeled complete.
Next source owner must integrate immutable original raw proof/member bindings and
semantic governing-source/RED/restoration/GREEN packages with a bounded all-arm
planner. Current exact judges/128000reserve and all gap guards remain unchanged.

`recovery.json` binds original context hash, artifact/run/head identities, ZIP
hashes/sizes and member listings; metadata files are original authenticated API
responses. `original-artifact-extraction.json` binds each resulting text hash and
records the offline bounds. Raw member bytes remain in their original local ZIPs.
The bounded download script preserves the original API failure rather than retrying.
