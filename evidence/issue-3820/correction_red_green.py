#!/usr/bin/env python3
"""Mutate the scoped #3821 correction, run RED, restore exact bytes, run GREEN."""

from deliberate_red_green import PYTEST, PYTHON, RECOVERY, WORKFLOW, main

PROFILE_TEST = "tests/workflows/test_verifier_evidence_profile.py"
INVOKE_GUARD = (
    '    if os.environ.get("VERIFIER_EVIDENCE_PROFILE") == "expanded":\n'
    "        _preflight_input_capacity(client, prompt)\n"
)
REPAIR_GUARD = (
    '        if os.environ.get("VERIFIER_EVIDENCE_PROFILE") == "expanded":\n'
    "            _preflight_input_capacity(self.client, prompt)\n"
)
MUTATIONS = [
    (
        "standard-native-invocation-regression",
        PYTHON,
        INVOKE_GUARD,
        "    _preflight_input_capacity(client, prompt)\n",
        PYTEST + [RECOVERY + "::test_configured_native_client_compatibility", "-k", "not repair"],
    ),
    (
        "standard-native-repair-regression",
        PYTHON,
        REPAIR_GUARD,
        "        _preflight_input_capacity(self.client, prompt)\n",
        PYTEST + [RECOVERY + "::test_configured_native_client_compatibility", "-k", "repair"],
    ),
    (
        "lose-selected-profile-before-python",
        WORKFLOW,
        "\n      VERIFIER_EVIDENCE_PROFILE: ${{ inputs.evidence_profile }}\n"
        "    steps:\n      - name: Select bounded verifier evidence profile\n        env:\n",
        "\n    steps:\n      - name: Select bounded verifier evidence profile\n        env:\n"
        "          VERIFIER_EVIDENCE_PROFILE: ${{ inputs.evidence_profile }}\n",
        PYTEST + [PROFILE_TEST + "::test_selected_profile_reaches_python_process"],
    ),
    (
        "lose-evaluate-capacity-upload",
        WORKFLOW,
        "          name: evaluation-capacity-${{ github.run_id }}\n          path: verifier-capacity-checks.jsonl",
        "          name: evaluation-capacity-${{ github.run_id }}\n          path: nonexistent.jsonl",
        PYTEST + [PROFILE_TEST + "::test_capacity_receipt_upload_survives_failed_generation"],
    ),
    (
        "bypass-expanded-invocation-unknown-count-and-overflow",
        PYTHON,
        INVOKE_GUARD,
        "",
        PYTEST
        + [
            RECOVERY + "::test_actual_capacity_unknowns_never_invoke",
            RECOVERY + "::test_actual_capacity_boundary_counts_entire_rendered_request",
        ],
    ),
    (
        "bypass-expanded-repair-unknown-count-and-overflow",
        PYTHON,
        REPAIR_GUARD,
        "",
        PYTEST
        + [
            RECOVERY + "::test_actual_capacity_unknowns_never_invoke",
            RECOVERY + "::test_native_message_capacity_and_schema_repair_are_checked",
        ],
    ),
    (
        "disable-standard-evidence-floor",
        PYTHON,
        'if coverage.sufficient or result.verdict != "PASS" or not result.used_llm:',
        'if os.environ.get("VERIFIER_EVIDENCE_PROFILE") != "expanded" or coverage.sufficient or result.verdict != "PASS" or not result.used_llm:',
        PYTEST + [RECOVERY + "::test_evidence_floor_is_unconditional"],
    ),
]

if __name__ == "__main__":
    main(MUTATIONS, "correction-deliberate-red-green.json", require_capture=False)
