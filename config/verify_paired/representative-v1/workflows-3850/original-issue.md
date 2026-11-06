## Problem
Source-owned Maint 71 independent finding verification passes the first validation, but cannot disposition a valid Maint 52 dev-tool delivery because the final revalidation unconditionally requires `latestRecord.head_observed_sha === pr.head.sha`. Maint 52's `sync-pr-delivery-record/v1` dev-tool record has no `head_observed_sha` field. The authenticated exact PR head, source, desired tree and lease remain unchanged. Do not patch the generated PR or waive a guard.

## Exact evidence
- Campaign: Workflows #1836. Consumer: stranske/Trend_Model_Project#6079, exact head `39ab28414db3944adcb74f73daee66806921edfc`.
- Maint 52 generation run: https://github.com/stranske/Workflows/actions/runs/38185912450 . Delivery plan `dev-tool-ab725abacde7`, generation `ab725abacde7`, source `19ab61a1e281791e915e512407fffa20515600bb`, desired tree `79080970d514c98122ec25fae6fd41933c587b5f`, lease `2026-10-14T23:53:24Z`.
- Completed independent Sol finding assessment `22d43c3d255ce9a8b2defe2e4342195d546d24f53ac42f1bdd07a128050b99e2`, result SHA256 `f45bb38eb7380f8c9b3f51c3b43d529939ec782460be577e235124d1c0df91ed`, exact-head bounded classification PASS. Durable attestation: https://github.com/stranske/Workflows/issues/1836#issuecomment-6115389680 . This is not whole-PR or originating-bot acceptance.
- Actual resolution run https://github.com/stranske/Workflows/actions/runs/38186594757 completed with `review_resolution_thread_ids: []`, error `PRRT_kwDOO0LrSc6rRwzT:verification_changed_before_resolution`, and two active threads. Its immutable `sync-pr-merge-report.json` is authoritative, not workflow success.
- Source `.github/scripts/maint71_merge_sync_prs.js` final independent-verification condition at `latestRecord?.head_observed_sha !== pr.head.sha` rejects the missing field. The request-stage validator already distinguishes dev-tool deliveries and optional observed-head binding. Source main `19ab61a1e281791e915e512407fffa20515600bb` was executing.

## Tasks
- [ ] Reproduce the valid exact-head dev-tool record counterexample using the actual schema and final controller path, with deliberate RED.
- [ ] Implement one lane-aware final binding contract: keep workflow-delivery observed-head requirements; validate dev-tool exact current PR head plus immutable record/source/tree/lease bindings. Do not merely remove the check or accept a conflicting observed head.
- [ ] Exercise both initial and immediately-pre-mutation reads. Negative controls: changed head, source/plan/generation/tree/lease, expired lease, conflicting observed head, missing required workflow binding, altered attestation or reviewer activity, and incomplete review pagination. Preserve strict concurrency and reviewer authority.
- [ ] Update defining ops docs and relevant tests; check source/template/manifest ownership rather than adding generated-consumer edits.
- [ ] Obtain source review, complete CI, seven-minute unchanged-head floor and merge before replaying the existing proof through serialized Maint 71. Preserve the separate CodeRabbit thread and all ordinary merge gates.

## Ownership and admission
Receiving owner: local Sol maintenance lane via Luna/controller admission, not an ungated hosted keepalive writer. This issue is a source prerequisite discovered by a real exact-head delivery attempt; the current maintenance assignment names existing source roots, not this new repair. Register this issue and any successor PR to stable campaign `workflows-1836`, obtain the remaining admitted engineering permit before source implementation, and never reset accounting or use another lane to evade admission. Recheck eligibility at the next controller discovery; no duplicate Maint 71 replay until a material source repair lands. No mandatory human review is introduced.
