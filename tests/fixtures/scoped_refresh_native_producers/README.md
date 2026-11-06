# Reviewed historical producer fixtures

The gzip files contain complete immutable source blobs, not caller-supplied
scope declarations. Decompressed filenames are SHA-256 identities, verified by
the tests before use. They are data fixtures and are never executed.

- `d52252...` is the workflow at native run40531388440/head0cbf1f5992a8b7a3a3e478ac452a7c54b4c05ba6 and bootstrap run40251631761/head67829b6145644352661b56f5251344cf952d0a64.
- `e24c64...` and `5684f1...` are the prior full producer versions observed in the same authenticated native history.
- `10d28c...` is the pure `.github/scripts/sync_run_contract.js` module at bootstrap head67829b6145644352661b56f5251344cf952d0a64. It has no imports or external effects.

Complete workflow diffs preserve Resolve immutable plan scope → source checkout
→ Validate immutable source reachability. Changes between these historical
versions concern the delivery guard, force behavior and cleanup propagation;
none substitutes payload source after validation. The whole-source pins reject
an extra post-validation checkout or other unreviewed change.

The production reader independently fetches native workflow/module blobs and
verifies their Git blob identity and complete SHA-256. Fixtures do not establish
live provenance, grant authority, or erase an UNKNOWN effect. The bootstrap
proof requires the entire native job/dependency/readback conjunction.

Bootstrap no-start additionally pins the complete native tree
`67829b6145644352661b56f5251344cf952d0a64`. The cancelled setup-api-client
composite and create_vendor_aliases helper at that tree only prepare local
directories/packages/env; npm lifecycle scripts are disabled and the helper
uses fs/path only. The exact native summary step/status inventory is required;
its promotion-check publisher was skipped. A changed native head or extra
summary execution remains UNKNOWN even if the workflow file is unchanged.
The conclusion is no delivery start, not absence of local setup activity.
