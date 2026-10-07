# Publisher environment-attempt correction

Follow-on review of14d5976a found the producer should read the actual Actions
GITHUB_RUN_ATTEMPT environment value instead of assuming context.runAttempt.
The test context intentionally omits that property. The helper validates a
positive integer before any write; its audited reporter hash and template agree.
Three missing/invalid environment cases reject before writing. Disabling only
that real JavaScript guard yields three named assertion failures, and exact-byte
restoration gives362focusedPASS. Raw corrected logs and helper hash are retained.
An initial syntax-invalid mutant is excluded from proof. Earlier collection
mutation and359PASS proof remain bound to14d5976a; no earlier artifact is rewritten.
This is controlled acceptance evidence, not an observed new-format live fork
publication, hosted CI PASS, reviewer disposition or merge authorization.
