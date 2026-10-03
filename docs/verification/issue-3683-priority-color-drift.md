# Priority-label color drift proof for #3683

This verifies the deliberate color-drift break required by [original issue #3624](https://github.com/stranske/Workflows/issues/3624)
for [merged PR #3663](https://github.com/stranske/Workflows/pull/3663),
merged commit [`b7a1147aa9c1c092a9269f74a84862e73fbce9de`](https://github.com/stranske/Workflows/commit/b7a1147aa9c1c092a9269f74a84862e73fbce9de).

Tested Workflows tip: `532a16759542af652cc30b05bd5abdc64e661d31`.
Captured at: `2026-10-03T22:58:09.337937+00:00` (UTC).

The proof temporarily changed only `.github/labels-core.yml` entry `priority:low`
from `0e8a16` to `ffffff`. The existing gate,
`tests/scripts/test_bootstrap_consumer_labels.py::test_priority_labels_match_synced_source_and_review_uploader`,
failed on that color difference. The original source bytes were restored in a `finally` block
before rerunning the same command, which passed all 26 tests.

## Temporary mutation

```diff
diff --git a/.github/labels-core.yml b/.github/labels-core.yml
index 72275268..2b28e789 100644
--- a/.github/labels-core.yml
+++ b/.github/labels-core.yml
@@ -46,7 +46,7 @@
   color: "fbca04"
   description: Normal-priority weekly repo-review work
 - name: priority:low
-  color: "0e8a16"
+  color: "ffffff"
   description: Low-priority weekly repo-review work

 # Agent status labels (for human visibility and retry mechanism)
```

## Command for both runs

The command is the exact issue-requested invocation. `PYTEST_ADDOPTS` adds the
`-m "not slow"` marker filter required by the agent instructions; no coverage
options or other pytest configuration overrides were used.

```sh
export PYTEST_ADDOPTS='-m "not slow"'
pytest tests/scripts/test_bootstrap_consumer_labels.py -q
```

Captured output below preserves all lines; trailing whitespace is stripped for repository hygiene.

## RED (exit 1)

```text
F........FFFF...FFF..F....                                               [100%]
=================================== FAILURES ===================================
_________ test_priority_labels_match_synced_source_and_review_uploader _________

    def test_priority_labels_match_synced_source_and_review_uploader() -> None:
        entries = yaml.safe_load(Path(".github/labels-core.yml").read_text(encoding="utf-8"))
        synced_priority_labels = {
            entry["name"]: {
                "color": entry["color"],
                "description": entry["description"],
            }
            for entry in entries
            if entry["name"].startswith("priority:")
        }
>       assert synced_priority_labels == EXPECTED_PRIORITY_LABELS
E       AssertionError: assert {'priority:hi...review work'}} == {'priority:hi...review work'}}
E
E         Omitting 2 identical items, use -vv to show
E         Differing items:
E         {'priority:low': {'color': 'ffffff', 'description': 'Low-priority weekly repo-review work'}} != {'priority:low': {'color': '0e8a16', 'description': 'Low-priority weekly repo-review work'}}
E
E         Full diff:
E           {
E               'priority:high': {
E                   'color': 'b60205',
E                   'description': 'High-priority weekly repo-review work',
E               },
E               'priority:normal': {
E                   'color': 'fbca04',
E                   'description': 'Normal-priority weekly repo-review work',
E               },
E               'priority:low': {
E         -         'color': '0e8a16',
E         ?                   ^^^^^^
E         +         'color': 'ffffff',
E         ?                   ^^^^^^
E                   'description': 'Low-priority weekly repo-review work',
E               },
E           }

tests/scripts/test_bootstrap_consumer_labels.py:80: AssertionError
______________ test_label_plan_contains_all_three_required_labels ______________

    def test_label_plan_contains_all_three_required_labels() -> None:
        plan = bcs.build_label_plan("stranske/Foo")
        assert [operation["id"] for operation in plan] == [
            "label_high",
            "label_normal",
            "label_low",
        ]
        commands = [operation["command"] for operation in plan]
        for name, definition in EXPECTED_PRIORITY_LABELS.items():
            command = next(command for command in commands if name in command)
>           assert command == [
                "gh",
                "label",
                "create",
                name,
                "--repo",
                "stranske/Foo",
                "--color",
                definition["color"],
                "--description",
                definition["description"],
            ]
E           AssertionError: assert ['gh', 'label...ske/Foo', ...] == ['gh', 'label...ske/Foo', ...]
E
E             At index 7 diff: 'ffffff' != '0e8a16'
E
E             Full diff:
E               [
E                   'gh',
E                   'label',
E                   'create',
E                   'priority:low',
E                   '--repo',
E                   'stranske/Foo',
E                   '--color',
E             -     '0e8a16',
E             +     'ffffff',
E                   '--description',
E                   'Low-priority weekly repo-review work',
E               ]

tests/scripts/test_bootstrap_consumer_labels.py:177: AssertionError
_________ test_apply_priority_labels_creates_only_missing_and_rechecks _________

    def test_apply_priority_labels_creates_only_missing_and_rechecks() -> None:
        initial = _label_inventory("priority:high", "priority:low")
        complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
        with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[initial, complete],
            ),
            patch("subprocess.run") as run,
        ):
>           bcs.apply_priority_labels("stranske/Foo")

tests/scripts/test_bootstrap_consumer_labels.py:202:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

repo = 'stranske/Foo'

    def apply_priority_labels(repo: str) -> None:
        """Create only absent labels, then verify exact metadata without silent overwrite."""
        inventory = _priority_label_inventory(repo)
        missing, mismatched = _priority_label_findings(inventory)
        if mismatched:
>           raise SystemExit(f"Refusing to overwrite label metadata in {repo}: {', '.join(mismatched)}")
E           SystemExit: Refusing to overwrite label metadata in stranske/Foo: priority:low

scripts/bootstrap_consumer_settings.py:331: SystemExit
________ test_apply_priority_labels_accepts_complete_template_inventory ________

    def test_apply_priority_labels_accepts_complete_template_inventory() -> None:
        complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
        with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[complete, complete],
            ),
            patch("subprocess.run") as run,
        ):
>           bcs.apply_priority_labels("stranske/Template")

tests/scripts/test_bootstrap_consumer_labels.py:222:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

repo = 'stranske/Template'

    def apply_priority_labels(repo: str) -> None:
        """Create only absent labels, then verify exact metadata without silent overwrite."""
        inventory = _priority_label_inventory(repo)
        missing, mismatched = _priority_label_findings(inventory)
        if mismatched:
>           raise SystemExit(f"Refusing to overwrite label metadata in {repo}: {', '.join(mismatched)}")
E           SystemExit: Refusing to overwrite label metadata in stranske/Template: priority:low

scripts/bootstrap_consumer_settings.py:331: SystemExit
________ test_main_execute_reconciles_template_derived_consumer_fixture ________

    def test_main_execute_reconciles_template_derived_consumer_fixture() -> None:
        fixture = json.loads(
            (
                Path(__file__).parent / "fixtures/template_derived_consumer_priority_labels.json"
            ).read_text(encoding="utf-8")
        )
        response = MagicMock(stdout=json.dumps([fixture]))
        with (
            patch(
                "sys.argv",
                [
                    "bootstrap_consumer_settings.py",
                    "--repo",
                    "fixture/template-consumer",
                    "--labels-only",
                    "--execute",
                ],
            ),
            patch("subprocess.run", side_effect=[response, response]) as run,
        ):
>           assert bcs.main() == 0
                   ^^^^^^^^^^

tests/scripts/test_bootstrap_consumer_labels.py:246:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
scripts/bootstrap_consumer_settings.py:719: in main
    apply_priority_labels(args.repo)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

repo = 'fixture/template-consumer'

    def apply_priority_labels(repo: str) -> None:
        """Create only absent labels, then verify exact metadata without silent overwrite."""
        inventory = _priority_label_inventory(repo)
        missing, mismatched = _priority_label_findings(inventory)
        if mismatched:
>           raise SystemExit(f"Refusing to overwrite label metadata in {repo}: {', '.join(mismatched)}")
E           SystemExit: Refusing to overwrite label metadata in fixture/template-consumer: priority:low

scripts/bootstrap_consumer_settings.py:331: SystemExit
_________ test_apply_priority_labels_tolerates_concurrent_exact_create _________

    def test_apply_priority_labels_tolerates_concurrent_exact_create() -> None:
        initial = _label_inventory("priority:high", "priority:low")
        complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
        error = subprocess.CalledProcessError(1, ["gh"], stderr="already exists")
        with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[initial, complete, complete],
            ),
            patch("subprocess.run", side_effect=error),
        ):
>           bcs.apply_priority_labels("stranske/Foo")

tests/scripts/test_bootstrap_consumer_labels.py:313:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

repo = 'stranske/Foo'

    def apply_priority_labels(repo: str) -> None:
        """Create only absent labels, then verify exact metadata without silent overwrite."""
        inventory = _priority_label_inventory(repo)
        missing, mismatched = _priority_label_findings(inventory)
        if mismatched:
>           raise SystemExit(f"Refusing to overwrite label metadata in {repo}: {', '.join(mismatched)}")
E           SystemExit: Refusing to overwrite label metadata in stranske/Foo: priority:low

scripts/bootstrap_consumer_settings.py:331: SystemExit
____________ test_apply_priority_labels_reraises_when_create_fails _____________

    def test_apply_priority_labels_reraises_when_create_fails() -> None:
        initial = _label_inventory("priority:high", "priority:low")
        error = subprocess.CalledProcessError(1, ["gh"], stderr="forbidden")
        with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[initial, initial],
            ),
            patch("subprocess.run", side_effect=error),
            pytest.raises(subprocess.CalledProcessError),
        ):
>           bcs.apply_priority_labels("stranske/Foo")

tests/scripts/test_bootstrap_consumer_labels.py:327:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

repo = 'stranske/Foo'

    def apply_priority_labels(repo: str) -> None:
        """Create only absent labels, then verify exact metadata without silent overwrite."""
        inventory = _priority_label_inventory(repo)
        missing, mismatched = _priority_label_findings(inventory)
        if mismatched:
>           raise SystemExit(f"Refusing to overwrite label metadata in {repo}: {', '.join(mismatched)}")
E           SystemExit: Refusing to overwrite label metadata in stranske/Foo: priority:low

scripts/bootstrap_consumer_settings.py:331: SystemExit
_____________ test_apply_priority_labels_fails_final_verification ______________

    def test_apply_priority_labels_fails_final_verification() -> None:
        initial = _label_inventory("priority:high", "priority:low")
        with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[initial, initial],
            ),
            patch("subprocess.run"),
>           pytest.raises(SystemExit, match="Priority label verification failed"),
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        ):
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'Priority label verification failed'
E         Actual message: 'Refusing to overwrite label metadata in stranske/Foo: priority:low'

tests/scripts/test_bootstrap_consumer_labels.py:338: AssertionError
___________ test_health_check_reports_zero_counts_and_missing_labels ___________

    def test_health_check_reports_zero_counts_and_missing_labels() -> None:
        complete = _label_inventory(*EXPECTED_PRIORITY_LABELS)
        missing_normal = _label_inventory("priority:high", "priority:low")
        with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[complete, missing_normal],
            ),
            patch(
                "scripts.bootstrap_consumer_settings._read_paginated_collection",
                side_effect=[[], [_issue(1, "unlabelled delivery")]],
            ),
        ):
            rows, exit_code = bcs.check_consumer_health(["stranske/Empty", "stranske/Missing"])
        assert exit_code == 1
>       assert rows[0] == {
            "repository": "stranske/Empty",
            "implementation_count": 0,
            "priority_labelled_count": 0,
            "unprioritized_count": 0,
            "missing": [],
            "metadata_mismatch": [],
            "excluded": {},
            "error": None,
            "status": "OK",
        }
E       AssertionError: assert {'repository'...ount': 0, ...} == {'repository'...ount': 0, ...}
E
E         Omitting 7 identical items, use -vv to show
E         Differing items:
E         {'status': 'FAIL'} != {'status': 'OK'}
E         {'metadata_mismatch': ['priority:low']} != {'metadata_mismatch': []}
E
E         Full diff:
E           {
E               'repository': 'stranske/Empty',
E               'implementation_count': 0,
E               'priority_labelled_count': 0,
E               'unprioritized_count': 0,
E               'missing': [],
E         -     'metadata_mismatch': [],
E         ?                           --
E         +     'metadata_mismatch': [
E         +         'priority:low',
E         +     ],
E               'excluded': {},
E               'error': None,
E         -     'status': 'OK',
E         ?                ^^
E         +     'status': 'FAIL',
E         ?                ^^^^
E           }

tests/scripts/test_bootstrap_consumer_labels.py:398: AssertionError
=========================== short test summary info ============================
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_priority_labels_match_synced_source_and_review_uploader - AssertionError: assert {'priority:hi...review work'}} == {'priority:hi...review work'}}

  Omitting 2 identical items, use -vv to show
  Differing items:
  {'priority:low': {'color': 'ffffff', 'description': 'Low-priority weekly repo-review work'}} != {'priority:low': {'color': '0e8a16', 'description': 'Low-priority weekly repo-review work'}}

  Full diff:
    {
        'priority:high': {
            'color': 'b60205',
            'description': 'High-priority weekly repo-review work',
        },
        'priority:normal': {
            'color': 'fbca04',
            'description': 'Normal-priority weekly repo-review work',
        },
        'priority:low': {
  -         'color': '0e8a16',
  ?                   ^^^^^^
  +         'color': 'ffffff',
  ?                   ^^^^^^
            'description': 'Low-priority weekly repo-review work',
        },
    }
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_label_plan_contains_all_three_required_labels - AssertionError: assert ['gh', 'label...ske/Foo', ...] == ['gh', 'label...ske/Foo', ...]

  At index 7 diff: 'ffffff' != '0e8a16'

  Full diff:
    [
        'gh',
        'label',
        'create',
        'priority:low',
        '--repo',
        'stranske/Foo',
        '--color',
  -     '0e8a16',
  +     'ffffff',
        '--description',
        'Low-priority weekly repo-review work',
    ]
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_creates_only_missing_and_rechecks - SystemExit: Refusing to overwrite label metadata in stranske/Foo: priority:low
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_accepts_complete_template_inventory - SystemExit: Refusing to overwrite label metadata in stranske/Template: priority:low
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_main_execute_reconciles_template_derived_consumer_fixture - SystemExit: Refusing to overwrite label metadata in fixture/template-consumer: priority:low
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_tolerates_concurrent_exact_create - SystemExit: Refusing to overwrite label metadata in stranske/Foo: priority:low
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_reraises_when_create_fails - SystemExit: Refusing to overwrite label metadata in stranske/Foo: priority:low
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_fails_final_verification - AssertionError: Regex pattern did not match.
  Expected regex: 'Priority label verification failed'
  Actual message: 'Refusing to overwrite label metadata in stranske/Foo: priority:low'
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_health_check_reports_zero_counts_and_missing_labels - AssertionError: assert {'repository'...ount': 0, ...} == {'repository'...ount': 0, ...}

  Omitting 7 identical items, use -vv to show
  Differing items:
  {'status': 'FAIL'} != {'status': 'OK'}
  {'metadata_mismatch': ['priority:low']} != {'metadata_mismatch': []}

  Full diff:
    {
        'repository': 'stranske/Empty',
        'implementation_count': 0,
        'priority_labelled_count': 0,
        'unprioritized_count': 0,
        'missing': [],
  -     'metadata_mismatch': [],
  ?                           --
  +     'metadata_mismatch': [
  +         'priority:low',
  +     ],
        'excluded': {},
        'error': None,
  -     'status': 'OK',
  ?                ^^
  +     'status': 'FAIL',
  ?                ^^^^
    }
9 failed, 17 passed in 1.05s
```

## Restored GREEN (exit 0)

```text
..........................                                               [100%]
26 passed in 0.88s
```

## Restoration

The exact original bytes were restored, including `priority:low` color `0e8a16`.

- Original SHA-256: `92c3670964eb0f079d96e733dfcf837a64fc9b514341db54ac2ee32a0184a66d`.
- Restored SHA-256: `92c3670964eb0f079d96e733dfcf837a64fc9b514341db54ac2ee32a0184a66d`.
- `git diff -- .github/labels-core.yml` produced no output after restoration.
- `tests/scripts/test_bootstrap_consumer_labels.py` remains unchanged as the gate.

Only this evidence artifact was changed permanently, as required by issue #3683.

## Verified task and acceptance completion

The transcript above was captured at `532a16759542af652cc30b05bd5abdc64e661d31`
and committed in `632fed89caba7e6453b92b33815d168903131791`. The intervening
commit changed only this evidence artifact; the label source and test gate did
not change. Revalidation at `632fed89` with the same command and marker filter
exited 0 (`26 passed in 0.87s`), with the same source SHA-256 recorded above.

- [x] At the current Workflows tip, temporarily changed `priority:low` in `.github/labels-core.yml`.
- [x] Captured the requested pytest command failing the priority-label drift assertion.
- [x] Restored the exact bytes and reran the same command successfully.
- [x] Commit the refreshed current-tip evidence artifact.
- [x] Evidence names the path and both failing and passing commands and outputs.
- [x] Restored color remains `0e8a16`, and the existing test file remains the gate.
- [x] Evidence links original issue #3624 and merged commit
  `b7a1147aa9c1c092a9269f74a84862e73fbce9de`.

## PR checkbox reconciliation blocker

All six unchecked items in PR #3724's automated task summary are satisfied by
the committed evidence above. The evidence-only commit is already present in
the PR; the earlier claim that the transcript remains uncommitted is obsolete.
An attempt to check those six verified items in the PR body was rejected:

```text
MCP tool call requires approval, but approval policy is never
```

Remote PR checkboxes were not updated because this run cannot grant the
required connector approval. PR #3724 was confirmed open with `draft=false`.
Reconcile these existing PR summary items without repeating the demonstration:

- [x] At the current Workflows tip, temporarily change the `priority:low` color in `.github/labels-core.yml`.
- [x] Run `pytest tests/scripts/test_bootstrap_consumer_labels.py -q` and capture the failure of the priority-label drift assertion.
- [x] Restore the exact color, rerun the same command, and commit only the red/green transcript or an evidence artifact.
- [x] The evidence names the changed repo-relative path `.github/labels-core.yml`, the failing command/output, and the restored passing command/output.
- [x] Restored source preserves the required `priority:low` color `0e8a16`; `tests/scripts/test_bootstrap_consumer_labels.py` remains the gate.
- [x] The evidence explicitly links original issue #3624 and merged commit `b7a1147aa9c1c092a9269f74a84862e73fbce9de`.
