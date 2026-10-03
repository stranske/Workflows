# Priority-label color drift proof for #3683

Tested base: `e2dea1809ae05d9f72d1a7ae5be1fb4e95b115ec`.

The isolated proof changed only `.github/labels-core.yml` entry `priority:low` from `0e8a16` to `ffffff`, ran the named suite, then restored the original bytes in a `finally` block. The source-drift assertion failed as required. The restored suite passed.

Command for both runs:

```sh
python3 -m pytest tests/scripts/test_bootstrap_consumer_labels.py -q --no-cov
```

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
E         Use -v to get more diff

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
E             Use -v to get more diff

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
>       with (
            patch(
                "scripts.bootstrap_consumer_settings._priority_label_inventory",
                side_effect=[initial, initial],
            ),
            patch("subprocess.run"),
            pytest.raises(SystemExit, match="Priority label verification failed"),
        ):
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'Priority label verification failed'
E         Actual message: 'Refusing to overwrite label metadata in stranske/Foo: priority:low'

tests/scripts/test_bootstrap_consumer_labels.py:332: AssertionError
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
E         {'metadata_mismatch': ['priority:low']} != {'metadata_mismatch': []}
E         {'status': 'FAIL'} != {'status': 'OK'}
E         Use -v to get more diff

tests/scripts/test_bootstrap_consumer_labels.py:398: AssertionError
=========================== short test summary info ============================
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_priority_labels_match_synced_source_and_review_uploader
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_label_plan_contains_all_three_required_labels
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_creates_only_missing_and_rechecks
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_accepts_complete_template_inventory
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_main_execute_reconciles_template_derived_consumer_fixture
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_tolerates_concurrent_exact_create
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_reraises_when_create_fails
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_apply_priority_labels_fails_final_verification
FAILED tests/scripts/test_bootstrap_consumer_labels.py::test_health_check_reports_zero_counts_and_missing_labels
9 failed, 17 passed in 0.60s
```

## Restored GREEN (exit 0)

```text
..........................                                               [100%]
26 passed in 0.22s
```

## Restoration

Original and restored bytes were identical; SHA-256: `92c3670964eb0f079d96e733dfcf837a64fc9b514341db54ac2ee32a0184a66d`.
`git diff -- .github/labels-core.yml` produced no output after restoration.
This PR commits only the captured transcript; no altered label source, generated runtime state, or simulated historical output.
