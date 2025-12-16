# Agents 63 issue sync label policy

The Agents 63 issue intake workflow—invoked directly for manual ChatGPT sync and via label triggers for the Codex bridge—relies on a
single, manually selected `agent:*` label to determine which automation is invited to work on a request. Auto-selection caused the bridge to summon the
wrong automation, so the workflow enforces a stricter contract across both entry paths.

## Manual agent selection

1. Choose the desired automation label (`agent:codex`, `agent:claude`, etc.) in
   the GitHub sidebar before running the sync. The sync will refuse to run if it
   cannot find exactly one base `agent:*` label.
2. Optional mode overrides such as `agent:codex-invite` may still be used, but
   they must accompany the base label (`agent:codex`). Invite-only labels without
   the base label are rejected.
3. Keepalive sentinel labels such as `agents:keepalive` are ignored by the
   validation logic and do not count toward the single-label requirement.

## Issue sync behaviour

- Each topic must specify exactly one base `agent:*` label. Topics without a
  label, or with more than one agent assignment, abort the run and emit
  actionable errors.
- The workflow publishes counts for skipped topics (missing or conflicting agent
  labels) in the run summary so the curator can fix the source topics before
  retrying.

## Bridge behaviour

- The bridge resolves the same single `agent:*` label and fails fast when the
  label is missing, duplicated, or only present in invite form.
- Copy/paste instructions derive the correct `@{agent}` mention and friendly
  agent title (`Codex`, `Claude`, etc.) from that label, ensuring the kick-off
  snippet always references the intended automation.
- When `agent:<name>-invite` is present alongside the base label, the bridge
  continues to honour the invite override while still deriving the correct agent
  mention.

Following these rules keeps the sync and bridge aligned, prevents accidental
hand-offs to the wrong automation, and keeps the keepalive workflow watching the
right checklists.
