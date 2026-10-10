# Authoritative expanded verdict helper checkout — source repair

Adopted current-head Codex finding4238614191 on e79e2c0fa7f9562f1283f8be62f2ce6d649672b4; owner reply4238620802. Python stdin prioritizes caller cwd over PYTHONPATH. Parent reproduced the real authored workflow against a stale caller package: both configured PASS arms became CONCERNS (1 behavioral failure1.11s; parent durable receipt20261010-3822-stale-consumer-red.json).

Expanded parsing now requires the fresh `.workflows-lib/scripts/langchain/pr_verifier.py` file and places its checkout first before importing the helper. Missing authoritative source stays CONCERNS. Relative result files remain in caller cwd; standard aggregation is unchanged. Five actual-workflow cases cover absent old helper, contradictory old helper, prohibited caller execution, caller-spoofed PASS with one non-PASS arm, and missing authoritative source. Source reusable workflow, manifest annotation and maintenance contract documentation are updated; consumer thin callers execute this reusable source without requiring prior consumer sync.

## Production mutation and restoration

Removed the exact eight-line production import-boundary repair, without changing tests. Locked offline pytest `tests/workflows/test_verifier_expanded_checkout.py -q -o addopts= --junitxml=evidence/issue-3820/expanded-checkout-mutation-red.xml`: exit1, five behavioral failures2.89s. Reapplied the exact saved bytes: same selector/restored-green.xml exit0, five passes3.70s. Source before/restored SHA256 e80d57592c2f83c7a35658bb6dd9db54ffa8caf08131358dbf3b9c47626ba260; deliberately mutated SHA2562acf5ec350b0bea4fce74df9b0d470b84176d40146ae9028be1311853b72f904. Original test SHA2562660a4cc9a4b8582144189efa8351f2a66e9ec67f0a5f135a2967f1166db2e42 unchanged during mutation/restoration.

One initial90-test integration overlapped the deliberate mutation and is NOT counted as stable-source validation despite its exit0. After restoration and all processes terminated, a separate stable-source integration passed161 tests52.66s: expanded checkout, all-arms comparison, caller security, evidence profile, drift allowlist and template sync. JUnit expanded-checkout-integration.xml. Then Black's initial check found formatting only; formatted the new test, Ruff passed, and reran its five tests: five passes3.40s/formatted-green.xml. Final test SHA2567b24bd6178c88ea9bf5b09b0a5cb9828bc7741194791be05c2cf8e656342bf0b. Actionlint on all three verifier workflows and production diff-check passed. All Python commands use `uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m`.

JUnit SHA256 bindings:

- mutation-red.xml:1281833bbd8ea5a9ae08a98197c8b62c96f3bda413daf2450607d3b082ac82ae
- restored-green.xml:40b9ecf19dbf92556290be37d84354a99659c5ef341727193a53c29fe067d287
- integration.xml:7a3e888e00c97f0e4bc8caa8982e438025565e55344603889dff7b7a7085c841
- formatted-green.xml:7e02f751fbcee016a05cc6ba980311883170f9ce755171457961d72ade1cdbac

The preceding security worker was terminal before parent edits. Its67 artifact hashes and six production YAML mutation/restoration proofs were independently verified before this additional source change. Its869PASS19SKIP and scanner bindings apply to its documented pre-checkout-fix source snapshot, not a claim of whole current-head scanning. The integration includes all15 security contract tests after the checkout change. Scanner aggregate residuals remain explicitly documented, never green-by-workflow-success. All historical/untracked owner artifacts are preserved.

These are local source/mock-provider results, not actual authenticated provider counts, originating finding acceptance, whole-PR approval or campaign completion. Provider capacity and verdict remain UNKNOWN/NONPASS until source delivery and actual hosted evidence.
