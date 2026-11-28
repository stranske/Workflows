# Reusable CI & Automation Workflows

## 1. Reusable CI (`reusable-10-ci-python.yml`)

To add Python CI, start with the [consumer example](INTEGRATION_GUIDE.md#quick-start). The [Gate job map](ci/WORKFLOWS.md#gate-job-map) shows which checks run in Workflows itself.

## 2. Reusable Docker Smoke (`reusable-12-ci-docker.yml`)

To build and probe a consumer's Docker image, call the [Docker workflow](../.github/workflows/reusable-12-ci-docker.yml) from a job:

```yaml
jobs:
  docker-smoke:
    uses: stranske/Workflows/.github/workflows/reusable-12-ci-docker.yml@main
```

## 3. Autofix (`reusable-18-autofix.yml`)

[CI Autofix Loop in Workflows](../.github/workflows/autofix.yml) and [Autofix in a consumer](../templates/consumer-repo/.github/workflows/autofix.yml) call [Reusable 18 Autofix](../.github/workflows/reusable-18-autofix.yml). For a Gate failure, see the [agent repair and formatting routes](ci/WORKFLOWS.md#autofix-routes).

## 4. Agent automation entry points

Use [Agents 63 Issue Intake](../.github/workflows/agents-63-issue-intake.yml)
in Workflows or [Agents Issue Intake](../templates/consumer-repo/.github/workflows/agents-issue-intake.yml)
in a consumer for manual intake and ChatGPT issue import. [Agents 64 Verify Agent Assignment](../.github/workflows/agents-64-verify-agent-assignment.yml)
checks an existing issue on demand. The [shared opener and closer](ops/LOCAL_LANES.md#lanes-overview)
own ordinary issue admission and PR promotion. Use
[Keepalive troubleshooting](keepalive/KEEPALIVE_TROUBLESHOOTING.md) for Gate and
sweep follow-ups. The [Agents 70 archive](archive/ARCHIVE_WORKFLOWS.md#agents-70-retirement)
records the retired dispatcher.

## 5. Selftest: Reusables (`selftest-reusable-ci.yml`)

The [self-test guide](ci/SELFTESTS.md) lists the scenarios, manual inputs, comment mode and reports from the [reusable CI self-test](../.github/workflows/selftest-reusable-ci.yml).

## Adoption Notes

Standard consumers use `@main`. See the [versioning policy](INTEGRATION_GUIDE.md#versioning-strategy) for controlled rollouts and the [installation guide](INTEGRATION_GUIDE.md#quick-start) for caller setup.

## Customisation Points

Check the [workflow outputs reference](ci/WORKFLOW_OUTPUTS.md) before wiring a downstream job. The [self-test scenarios](ci/SELFTESTS.md#scenario-matrix) exercise optional CI settings.

## Security & Permissions

Configure the caller's token permissions using the [integration guide](INTEGRATION_GUIDE.md#workflow-permissions).
