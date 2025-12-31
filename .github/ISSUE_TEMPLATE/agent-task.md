---
name: Agent task
about: Plan a Codex automation task with clear guardrails
title: "[Agent task] <summary>"
labels:
  - agents
  - agent:codex
assignees: ''
---

<!-- 
📚 Format Guide: See docs/ci/ISSUE_FORMAT_GUIDE.md for detailed formatting requirements,
   section header options, and examples of valid issue structures.
-->

<!-- 
⚠️ CHECKPOINT CONVERSION RULES:
   • Everything in "Tasks" section becomes a checkbox
   • Everything in "Acceptance criteria" section becomes a checkbox  
   • Put instructions, notes, verification steps in "Scope" or "Implementation Notes"
   • Use numbered lists (1. 2. 3.) for step-by-step instructions - they won't become checkboxes
   • Use bullet points (- item) only for actual tasks/criteria you want to check off
-->

## Why
<!-- Describe the primary objective Codex should accomplish. Include links to relevant issues, documents, or workflows. -->

## Scope
<!-- Define what is IN scope for this task. Be specific about files, components, or features to be modified. -->

## Constraints
<!-- List guardrails Codex must respect (files to avoid, technologies to use, time limits, dependencies, etc.). -->

## Tasks
<!-- 
Actionable checklist of work items. Each line with a bullet (-) will be converted to a checkbox.
DO NOT use bullets for instructions or explanations - only for actual tasks.
Each task should be a concrete, verifiable action item.

CORRECT:
- [ ] Add unit tests for feature X
- [ ] Update documentation

INCORRECT:
- Before implementing, review the codebase  (This is an instruction, not a task)
- Each test must cover edge cases  (This is guidance, not a task)
-->
- [ ] Task 1
- [ ] Task 2

## Expected outputs
<!-- Enumerate the artifacts Codex should produce (code changes, tests, docs, dashboards, reports, etc.). -->

## Acceptance criteria
<!-- 
Define how success will be evaluated. Each line with a bullet (-) will be converted to a checkbox.
DO NOT use bullets for instructions on how to verify - only for actual criteria.
Each criterion should be a verifiable condition that must be met.

CORRECT:
- [ ] All tests pass
- [ ] Code coverage ≥95%
- [ ] Documentation is updated

INCORRECT:
- Before marking complete, run pytest  (This is an instruction, not a criterion)
- To verify, check the output  (This is guidance, not a criterion)
- 1. Run tests  (Numbered lists are not criteria)
-->
