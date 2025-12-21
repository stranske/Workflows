# Workflows integration consumer

This repository exercises the [`reusable-10-ci-python.yml`](https://github.com/stranske/Workflows/blob/main/.github/workflows/reusable-10-ci-python.yml) workflow from `stranske/Workflows` across multiple configurations to detect regressions before they reach real consumers.

![Integration CI status](https://github.com/stranske/Workflows-integration-test/actions/workflows/ci.yml/badge.svg)

## What it does

- Runs three permutations of the reusable workflow:
  - **Basic:** default inputs against a tiny Python package.
  - **Full coverage:** multi-version test matrix with coverage gating enabled.
  - **Monorepo simulation:** targets a nested package via `working-directory`.
- Opens an upstream issue in [`stranske/Workflows`](https://github.com/stranske/Workflows) when any integration permutation fails (requires a `WORKFLOWS_PAT` secret with `repo` scope).
- Triggers automatically on schedule, manual dispatch, and when the workflow library publishes new releases through a `repository_dispatch` event named `workflow-library-release`.

## Usage

1. Create a repository from this template.
2. Add a secret named `WORKFLOWS_PAT` with permissions to open issues in `stranske/Workflows`.
3. Optional: set a repository variable `WORKFLOW_LIBRARY_REF` to pin a specific branch or tag of the workflow library (defaults to `main`).
4. Push to `main` or wait for the scheduled run to validate the reusable workflow.
