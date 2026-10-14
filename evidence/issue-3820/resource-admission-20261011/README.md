# Offline original-capture resource admission

`tools/verifier_proof_resource_plan.py` is an offline accounting slice of source3820, not an executable semantic partitioner. The retained original capture is unchanged; its reassembly contract includes277 obligations,163 gaps and60 raw ranges. All11 retained original ZIP/metadata hashes match their frozen collection inventory. All61 ZIP member occurrences require118,319,651 raw bytes versus the unchanged67,108,864-byte cumulative extraction ceiling. Identical member content/provenance occurrences are not subtracted from the operational charge. ZIP listings are declared metadata: no member decompression, CRC validation, rendering, provider call, native fit or evidence completeness is claimed.

The committed original-resource-plan.json binds full original contract and all archive/member occurrences; `admitted=false`. Global extraction, unproven semantic dependency closure, unproven native capacity/result matrix and original capture insufficiency remain explicit blockers. No input or historical receipt was modified. Original capture/context hash is f2f8732903e50b8cf4827dfe89a015efc6d4f2c66db8c01f4b090b41853c5223.

The actual source mutation changed cumulative `required_bytes += member.file_size` to per-member assignment. The named global-counter test fails RED with exit1; byte-identical candidate restoration passes GREEN with exit0. Raw logs/JUnit/source hashes are retained. A concurrent exploratory suite encountered the deliberate mutation and was discarded; the serialized focused-final run after restoration is the final candidate result.

New controls reject omitted archives, changed raw archive/metadata bytes, wrong-head provenance, omitted occurrences/gaps/ranges, promoted admission and counter resets. Complete small inputs remain diagnostic, not acceptance. CLI writes only to a fresh output and preserves context bytes. Source and consumer-template module parity is exact.

Next source slice must establish governing/code/RED-restoration-GREEN and cross-proof semantic closures before narrower packages or acceptance-bearing execution. Original native judge/model128,000-token reserves and full result matrix stay required. Source3820 remains OPEN; no whole-source/provider acceptance is inferred.

Final candidate validation:89 focused tests and3,944 partition/prompt/profile/sync regressions PASS. Source/template planner parity, generated Renovate ownership check, focused Black/Ruff and git diff --check PASS. The added managed entry changes the compiled sync inventory247→248; its named path is asserted.
