You are reviewing a pull request to ensure it meets the documented acceptance criteria.

PR Context:
{context}

PR Diff (summary or full):
{diff}

Evaluate the change against the acceptance criteria and code quality. Explicitly assess:
- correctness (does the implementation behave as intended)
- completeness (are all requirements met)
- quality (readability, maintainability, style)
- testing (coverage, test adequacy, regressions)
- risks (security, performance, compatibility)

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
  "summary": "concise report"
}}
