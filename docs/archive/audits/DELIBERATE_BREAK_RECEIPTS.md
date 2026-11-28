# Historical deliberate-break receipts

These receipts preserve the observed failure, restoration, and any limit in the original delivery evidence. Each link opens the complete original at the same immutable repository revision.

| Issue | Receipt | Recorded outcome |
| --- | --- | --- |
| [#3457](https://github.com/stranske/Workflows/issues/3457) | [Auto-dispatch persistence](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-3457-auto-dispatch-deliberate-break.md) | The original PR lacked retained mutation evidence. Its later dispatch regression failed under the deliberate break and passed after restoration. |
| [#3470](https://github.com/stranske/Workflows/issues/3470) | [Primary storage refusal](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-3470-primary-storage-deliberate-break.md) | All eight focused cases passed on production and restored source and failed with the refusal removed. |
| [#3532](https://github.com/stranske/Workflows/issues/3532) | [PR 3508 review heading](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-3532-pr-3508-deliberate-break.md) | The retained reproduction ties the named one-case failure and restoration to the earlier evidence gap. |
| [#3533](https://github.com/stranske/Workflows/issues/3533) | [PR 3520 review correction](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-3533-pr-3520-deliberate-break.md) | The retained later verification records a one-case failure and restoration plus a 23-case follow-up. |
| [#3586](https://github.com/stranske/Workflows/issues/3586) | [PR 3562 re-verification](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-3586-pr-3562-deliberate-break.md) | The receipt preserves the focused mutation, restored verification, and separate advanced-base provider report. |
| [#3607](https://github.com/stranske/Workflows/issues/3607) | [Belt proxy invariant](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-3607-belt-proxy-deliberate-break.md) | The receipt keeps the deliberate break and restored pass separate from the observed exact merge-head scheduled run. |
| [#4097](https://github.com/stranske/Workflows/issues/4097) | [Issue 4097 regression](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/evidence/issue-4097/regression.md) | The standalone record preserves the exact mutated source, resulting regression, and restored verification. |

To recover the exact text locally, use `git show REVISION:PATH` with the revision and path in the receipt link. The original receipt records the source revision and test commands for the specific reproduction.
