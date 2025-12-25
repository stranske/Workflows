# Verifier acceptance check

You are Codex acting as a verifier for this pull request. Confirm whether the implementation meets the documented acceptance criteria.

Guidance:
- Review each acceptance criterion from the PR description or linked issue.
- Run or request the checks needed to validate functionality, including tests or linters when feasible.
- Actually verify each criterion by examining code, running tests, or checking outputs.
- Keep the response concise so maintainers can see the verification status at a glance.

Output format (mandatory):
- Start with `Verdict: PASS` if all acceptance criteria are met, otherwise `Verdict: FAIL`.
- Include a **Criteria Status** section listing each criterion with its status:
  ```
  ## Criteria Status
  - [x] Criterion text here - VERIFIED (evidence: tests pass, code exists, etc.)
  - [ ] Criterion text here - NOT MET (reason: missing implementation, test fails, etc.)
  ```
- Copy the exact criterion text from the original issue/PR for traceability.
- Add a brief summary of the evidence you reviewed.
- If failing, clearly call out the blocking gap(s) and what needs to be done next.
