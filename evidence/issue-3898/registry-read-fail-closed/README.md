# Trusted registry availability and exact-head status

Native Minor4289213508 originally requested bounded retries. Admitted source
diagnosis also found a distinct correctness path: read/type/parse failure in
the direct publisher exited without overwriting earlier same-head success.
The actual inline source/template publisher was executed with an initial green
status: transient reads (third succeeds), exhausted failures and malformed
registry. Original6casesFAIL; corrected full guard suites572PASS.

All three registry read sites retry only retryable API failures, at most3calls
with1s/2s waits. Trusted base ref and read-only registry parser remain unchanged.
The publisher overwrites previous success with a receipt-free failure if trusted
policy evidence remains unavailable. Denied status writes still surface failure;
no direct-write/permission bypass is introduced. Existing unchanged-policy
success, label drift, stale-head/attempt, denied-write and fork-token controls
remain in the full suite. The direct publisher needs no checkout code or secrets.

This is local source proof, separate from current-head CI/native reviewer,
guarded merge and actual provider acceptance. The original denied independent
sandbox reproductions remain stopped and are not claimed as verified.

Native P14289608854 corrected the separate privileged fork-publisher path. Missing/type/parse registry evidence is carried as failure through fresh PR/head/base/run binding and latest-attempt checks before publication; it does not trust policy receipts or old producer success. Original2RED and full574GREEN retained, including every head/run/newer-attempt drift refusing all writes. The stopped independent reproduction was not retried.
