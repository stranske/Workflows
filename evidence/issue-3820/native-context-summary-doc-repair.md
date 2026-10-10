# Independent capacity-bound summary correction

Adopted Codex finding4238466577 on ec5c20414da7b2baaf706b99b7f83c2fa88a3afb: the top-level maintenance summary still stated the superseded input-plus-output versus input-only comparison. The provider-specific section and production implementation already used independent limits.

New regression against the actual original paragraph: `uv run --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest -q -o addopts= tests/workflows/test_verifier_evidence_profile.py::test_capacity_docs_keep_input_and_context_bounds_independent` exited1, 1 failed in0.34s. After the documentation correction, the complete evidence-profile suite exited0, 42 passed in3.39s.

The summary now explicitly requires input <= input limit, input + actual output <= context limit, and actual output <= output limit. No source/template production behavior or fingerprint changed in this correction. Native provider capacity and verifier acceptance remain UNKNOWN/NONPASS until actual hosted receipts and verdicts are inspected. The prior production mutation evidence remains historical and unmodified.
