I couldn’t find any CI failure details in the repo, and the run you referenced was cancelled with no failing jobs reported. Without logs or a failing check name, there’s nothing targeted I can fix yet.

If you can share the failing job name or its log excerpt, I can zero in on it. Otherwise, a quick local verification could surface it:

- `scripts/validate_fast.sh`
- `pytest -q`

If you want, tell me which check was failing in PR #154 and I’ll take it from there.