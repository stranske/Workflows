# Workflow Integration Guide

This guide explains how to apply the generated snippets to the three target workflows without modifying them in this PR. Line numbers refer to current file locations as of February 7, 2026.

Snippets:
- `docs/workflow-snippets/pip-cache-step.yml`
- `docs/workflow-snippets/pip-freeze-step.yml`
- `docs/workflow-snippets/agents-auto-pilot-install.yml`
- `docs/workflow-snippets/reusable-agents-verifier-install.yml`
- `docs/workflow-snippets/agents-verify-to-new-pr-install.yml`

Note: The pip cache snippet uses `matrix.python-version`. If a job does not already define a matrix, add a single-value matrix that matches the existing Python version before inserting the cache step.

**agents-auto-pilot.yml**
1. Open `.github/workflows/agents-auto-pilot.yml` and locate the `Set up Python` step at lines 184-188.
2. Insert the cache step from `docs/workflow-snippets/pip-cache-step.yml` immediately after line 188.
3. Replace the `Install Python dependencies` step at lines 190-197 with the contents of `docs/workflow-snippets/agents-auto-pilot-install.yml`.
4. Insert the pip freeze step from `docs/workflow-snippets/pip-freeze-step.yml` immediately after the install step you added in step 3.

**reusable-agents-verifier.yml**
1. In `.github/workflows/reusable-agents-verifier.yml`, find the `Setup Python for LLM evaluation` step at lines 365-369.
2. Insert the cache step from `docs/workflow-snippets/pip-cache-step.yml` immediately after line 369.
3. Replace the `Install LLM evaluation dependencies` step at lines 371-374 with the evaluation portion of `docs/workflow-snippets/reusable-agents-verifier-install.yml`.
4. Insert the pip freeze step from `docs/workflow-snippets/pip-freeze-step.yml` immediately after the evaluation install step.
5. Find the `Setup Python for comparison` step at lines 519-523.
6. Insert the cache step from `docs/workflow-snippets/pip-cache-step.yml` immediately after line 523.
7. Replace the `Install comparison dependencies` step at lines 525-528 with the comparison portion of `docs/workflow-snippets/reusable-agents-verifier-install.yml`.
8. Insert the pip freeze step from `docs/workflow-snippets/pip-freeze-step.yml` immediately after the comparison install step.

**agents-verify-to-new-pr.yml**
1. Open `.github/workflows/agents-verify-to-new-pr.yml` and locate the `Set up Python` step at lines 92-96.
2. Insert the cache step from `docs/workflow-snippets/pip-cache-step.yml` immediately after line 96.
3. Replace the `Install dependencies` step at lines 98-101 with the contents of `docs/workflow-snippets/agents-verify-to-new-pr-install.yml`.
4. Insert the pip freeze step from `docs/workflow-snippets/pip-freeze-step.yml` immediately after the install step you added in step 3.
