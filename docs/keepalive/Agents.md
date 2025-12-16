# Agents Guidance — Keepalive Changes

Automation agents touching **any** keepalive code path must consult [`GoalsAndPlumbing.md`](GoalsAndPlumbing.md) before making changes. That document is the canonical contract covering:

- Activation prerequisites (labels, human kickoff, Gate status)
- Instruction comment formatting and required hidden markers
- Dispatch, acknowledgement, and branch-sync responsibilities
- Pause/resume labels and run-cap enforcement
- The full lifecycle sequence (human kickoff → guarded checks → timed repeats → acceptance shutdown → label reapply)

Do not mark checklist items complete or dispatch new keepalive rounds until the acceptance criteria in the canonical guide are satisfied. Update both documents together if the contract evolves.
