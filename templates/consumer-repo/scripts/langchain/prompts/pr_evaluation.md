You are reviewing a **merged** pull request to evaluate whether the code changes meet the documented acceptance criteria.

**IMPORTANT: This verification runs AFTER the PR has been merged.** Therefore:
- Do NOT evaluate CI status, workflow runs, or pending checks - these are irrelevant post-merge
- Do NOT raise concerns about CI workflows being "in progress" or "queued"
- Focus ONLY on the actual code changes and whether they fulfill the requirements

PR Context:
{context}

PR Diff (summary or full):
{diff}

## Evaluation Focus

Evaluate the **code changes** against the acceptance criteria. Explicitly assess:

1. **correctness** - Does the implementation behave as intended based on the code?
2. **completeness** - Are all requirements addressed in the code changes?
3. **quality** - Code readability, maintainability, and style
4. **testing** - Are tests present and adequate for the changes? Do they cover the acceptance criteria?
5. **risks** - Security, performance, or compatibility concerns in the code

## What to Ignore

- CI workflow status (running, queued, success, failure) - verification is post-merge
- Any concerns about "CI not yet verified" or "waiting for checks"
- Log output or workflow artifacts - focus on the code itself

## What to Evaluate

- The actual code diff and what it implements
- Whether test files added/modified adequately verify the acceptance criteria
- Whether the implementation logic matches the stated requirements
- Code patterns, error handling, and edge cases

## Verdict Guidelines

- **PASS**: correctness and completeness are satisfied.  Testing gaps alone
  should NOT prevent a PASS if the implementation is functionally correct.
- **CONCERNS**: significant correctness or completeness issues exist, OR the
  implementation introduces meaningful risks.
- **FAIL**: the changes do not address the acceptance criteria or introduce
  breaking problems.

Respond in JSON with:
{{
  "verdict": "PASS | CONCERNS | FAIL",
  "confidence": 0.0-1.0,
  "scores": {{
    "correctness": 0-10,
    "completeness": 0-10,
    "quality": 0-10,
    "testing": 0-10,
    "risks": 0-10
  }},
  "concerns": ["..."],
  "summary": "concise report focusing on code quality and acceptance criteria fulfillment"
}}
