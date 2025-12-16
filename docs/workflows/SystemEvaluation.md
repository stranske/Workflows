# System Evaluation: Workflow Architecture

## Executive Summary

This document evaluates the current GitHub Actions workflow architecture against four key operational goals: **Repo Health**, **Efficient PRs**, **Autofix Automation**, and **Keepalive Operations**.

**Overall Status**: The system is functional but suffers from **logic duplication** (specifically in Autofix) and **high complexity** in the Orchestrator. The "Gate" workflow is effectively optimizing PR checks, but its coupling with Autofix labeling creates maintenance overhead.

---

## 1. Repo Health (`health-40-sweep.yml`)

**Goal**: Maintain repository hygiene and validity.

*   **Current State**:
    *   Focuses primarily on **Workflow Syntax** (`actionlint`) and **Branch Protection** verification.
    *   Runs on a weekly schedule and on workflow file changes.
*   **Gaps**:
    *   **Scope Limitation**: It does not currently check for stale branches, dependency freshness (outside of Dependabot), or other "repo health" metrics like TODO tracking or code complexity trends.
    *   **Naming**: The name `health-40-sweep` implies a broader scope than just workflow linting.
*   **Recommendations**:
    *   **Rename** to `health-workflows.yml` to reflect its actual scope.
    *   **Expand** "Health" concept to include a separate `health-codebase.yml` that might run deeper static analysis (e.g., complexity checks, dead code detection) that is too slow for PR gates.

## 2. Efficient PRs (`pr-00-gate.yml`)

**Goal**: Fast, reliable regression testing for Pull Requests.

*   **Current State**:
    *   **Optimization**: Uses `detect-changes.js` to intelligently skip tests when only docs or non-code files change. This is a strong feature.
    *   **Execution**: Delegates actual testing to `reusable-10-ci-python.yml`, ensuring consistency.
    *   **Feedback**: Provides a clear summary and comments on the PR.
*   **Issues**:
    *   **Coupling**: The Gate workflow contains significant inline logic for **Autofix Labeling** (detecting cosmetic failures and applying labels). This mixes "Testing" concerns with "Fixing" concerns.
    *   **Complexity**: The `summary` job is complex, handling artifact aggregation and comment posting.
*   **Recommendations**:
    *   **Decouple Autofix**: Move the "Auto-labeling" logic into a separate workflow or a dedicated step in the reusable CI workflow that outputs a "recommendation" rather than having the Gate apply labels directly.

## 3. Autofix (`autofix.yml` vs `reusable-18-autofix.yml`)

**Goal**: Automatically correct small code issues (linting, formatting).

*   **Current State**:
    *   **Redundancy (Critical)**: `autofix.yml` (the event trigger) **duplicates** the logic found in `reusable-18-autofix.yml`.
        *   `autofix.yml`: Manually sets up Python, installs `ruff`/`black`, runs them, and commits.
        *   `reusable-18-autofix.yml`: *Also* sets up Python, installs tools, runs them, and commits.
    *   **Split Brain**: Improvements to the reusable workflow (e.g., better commit messages, safer push logic) are **not** reflected in the main `autofix.yml` loop.
*   **Recommendations**:
    *   **Refactor `autofix.yml`**: It should be a thin wrapper that listens for events (labels, pushes) and then **calls** `reusable-18-autofix.yml`.
    *   **Single Source of Truth**: Centralize all "how to fix" logic in `reusable-18`.

## 4. Keepalive (`agents-70-orchestrator.yml`)

**Goal**: Ensure continuous operation and iterative task completion.

*   **Current State**:
    *   **Monolithic**: The orchestrator is extremely large (~3500 lines). It handles scheduling, token rotation, run caps, agent dispatch, and context resolution.
    *   **Robustness**: It has sophisticated "Guard" logic to prevent runaway agents and ensure human oversight (via labels).
    *   **Integration**: Works closely with `agents-keepalive-dispatch-handler.yml` to process user commands from comments.
*   **Issues**:
    *   **Maintainability**: The sheer size of the orchestrator makes it difficult to debug or modify.
    *   **Logic Dispersion**: Keepalive logic is split between the Orchestrator (scheduling), the Dispatch Handler (comments), and the Branch Sync workflow.
*   **Recommendations**:
    *   **Modularize**: Extract the "Guard" and "Context Resolution" logic into separate reusable workflows or composite actions.
    *   **Simplify**: The token rotation and identity verification logic is verbose; consider simplifying or moving to a dedicated script.

---

## 5. Missing Functionality & Performance

**Goal**: Identify gaps in the current workflow suite and opportunities for speed optimization.

*   **Performance**:
    *   **Sequential Testing**: `reusable-10-ci-python.yml` runs `pytest` without parallelism. `pytest-xdist` is missing from `pyproject.toml`.
        *   **Impact**: Tests run one by one, slowing down feedback loops as the test suite grows.
    *   **Artifact Overload**: The CI workflow uploads a massive amount of artifacts (coverage XML/JSON/HTML, metrics, history, classification, delta, trend) for *every* run.
        *   **Impact**: Increases storage costs and workflow runtime (upload/download time).
    *   **Fail-Slow Strategy**: The CI workflow uses `continue-on-error: true` for all checks (lint, format, typecheck, test) to gather a full report.
        *   **Impact**: Developers wait for the full suite to finish even if a simple lint error occurred 10 seconds in.

*   **Missing Functionality**:
    *   **Security Scanning**: No SAST tools (e.g., `bandit`, `safety`, CodeQL) are currently integrated.
    *   **Release Automation**: No workflow exists to automate PyPI publishing or GitHub Releases upon tagging.
    *   **Documentation**: No workflow exists to build and deploy documentation (Sphinx/MkDocs) to GitHub Pages.

*   **Repo Health (Re-evaluation)**:
    *   `health-41-repo-health.yml` *does* exist and covers "Stale Branches" and "Unassigned Issues". This is good!
    *   **Gap**: It does not check for "Stale PRs" or "Dependency Freshness" (beyond what Dependabot might do silently).

*   **Recommendations**:
    *   **Enable Parallel Testing**: Add `pytest-xdist` to `pyproject.toml` and update `reusable-10-ci-python.yml` to use `pytest -n auto`.
    *   **Optimize Artifacts**: Only upload full coverage reports on `main` or when explicitly requested. Use summary comments for PRs.
    *   **Add Security Workflow**: Create `security.yml` running `bandit` and `safety`.
    *   **Create Release Workflow**: Add `release.yml` for automated publishing.

---

## Summary of Action Items

| Priority | Task | Status | Notes |
| :--- | :--- | :--- | :--- |
| **High** | **Refactor `autofix.yml` to use `reusable-18`** | **Completed** | Loop guard now uses commit-prefix detection |
| **High** | **Enable `pytest-xdist`** | **Completed** | Added to pyproject.toml |
| High | Add `security.yml` (CodeQL) | Completed | Standard CodeQL for Python |
| Medium | Add `release.yml` | Completed | Uses `softprops/action-gh-release` |
| Medium | Add `docs.yml` | Removed | No build system (mkdocs/sphinx) configured |
| Medium | Add "Stale PR" check to `health-41` | Completed | Tracks PRs inactive >30 days |
| Low | Optimize CI artifacts | Completed | 1-day retention for PRs, 7 for main |
