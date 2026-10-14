# Raw captured byte inventory foundation

Existing PR3831/source3820, based on 1c6fe324df93cfcc017b1bd4479a6c9987fa746b.

The existing CLI snapshot recording path now indexes all supplied raw context/diff
bytes in deterministic 64KiB half-open ranges, with whole-input and per-range hashes
and input/hash/offset identities. It validates existing inventories before writes.
This is an operational input binding, not a semantic partition planner.

- Original implementation plus new tests: 14 FAIL / 55 PASS.
- Actual production equality-guard bypass: see byte-mutant.log/JUnit; exact
  restoration: 76 PASS (byte-restored.log/JUnit).
- An initial CLI test used the wrong compare JSON field; corrected to the existing
  results[0] contract before the qualified mutation/restoration pair. The separate
  attempt1 logs remain in lane scratch; they are not successful proof.
- Related capture/recovery/prompt/comparison/template tests: 3913 PASS, 1 SKIP
  (immutable authenticated fixture owner-local; separate saved capture replay below).
- Offline original run38118258124 context/diff hashes matched the saved snapshot;
  all 3,882,172 raw bytes reassembled identically in 60 ranges. This replay is a
  hash/range proof only; original capture remains insufficient.

Commands: python3 -m pytest tests/tools/test_verifier_capture_obligation_manifest.py
 tests/scripts/test_pr_verifier_capture_obligation_failure.py -q; and related suites
named in byte-related.log. Production mutant changes only the equality predicate
in validate_capture_byte_inventory to False; byte-mutation.json retains exact
before/restored hashes. Root/template copies are byte-identical; touched Black,
Ruff and git diff --check pass.

Outstanding: semantic cross-proof obligation packages, all exact native judge
partition execution/aggregation, missing/truncated proof recovery and actual complete
native acceptance. No model/reserve change, provider call, merge or source closure.
