# Correction helper receiver copies

The managed receiver copies of `verifier_correction_runtime.js`,
`verifier_correction_collector.js`, `verifier_correction_profile.py` and
`verifier_correction_seed.js` are retired. Their canonical files under
Workflows `.github/scripts/` and all documented offline request/receipt APIs
remain intact. This changes receiver distribution only.

The native `agents-verify-to-new-pr.yml` collection job explicitly checks out
`stranske/Workflows` into the workspace root before its relative imports.
The collector imports the seed helper and resolves the profile reader from
its own `__dirname`. The reusable verifier imports the seed producer from its
explicit `.workflows-lib` Workflows checkout. The older native apply jobs installed on all sixteen checked heads also fetch
their correction runtime from Workflows, whose source remains available. This
does not remove source files or historical Git objects used by pinned consumers.

The six remaining copied correction helpers are retained in this change to
preserve the transitive interface of copied `verification_event.js`:
consumer, host, effects, autopilot, artifacts and decision. That import closure
is an observable local API dependency; it is not evidence that an active
receiver workflow executes every helper. Retiring that entire closure needs
its own entry-point and compatibility proof. No receiver-local documented
offline API or receiver-specific edits were found in the sixteen checked
installed default-branch trees on 2026-11-27.

Each retired path has an explicit manifest removal, and its consumer template
copy is deleted. Removing only the copy entry would leave already installed
copies behind. The Renovate ownership preset is regenerated from the manifest.
Normal Maint 68/71 delivery must subsequently show the four paths absent on
each receiving head, the retained six and `verification_event.js` available,
and the receiver's ordinary verifier/native collection checks passing. Source
PR acceptance and a local pruned snapshot are not that delivery receipt.
No receiver was edited or synchronized during preparation.
