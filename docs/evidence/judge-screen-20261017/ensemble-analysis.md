## Judge ensemble analysis

8 cases (4 NON_PASS). **Nothing is enabled by this report.**

| Judge | Correct | False PASS | False-PASS upper bound | Invalid | PASS authority |
|---|---:|---:|---:|---:|---|
| agy-cli | 4/8 | 2 | 0.85 | 2 | no: 2 false PASS observed; 2 invalid result(s); false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| claude-cli | 4/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| cursor-cli | 6/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| gpt-5.6-terra | 6/8 | 0 | 0.4899 | 0 | no: false-PASS upper bound 0.4899 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| gpt-6-luna | 5/8 | 1 | 0.6994 | 0 | no: 1 false PASS observed; false-PASS upper bound 0.6994 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| muse-api | 6/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |
| muse-cli | 3/8 | 2 | 0.85 | 1 | no: 2 false PASS observed; 1 invalid result(s); false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors |

### Pairs (production strict-AND contract)

| Pair | Agreement | Both wrong | False PASS | False FAIL |
|---|---:|---:|---:|---:|
| agy-cli + claude-cli | 0.75 | 3 | 2 | 3 |
| agy-cli + cursor-cli | 0.5 | 1 | 1 | 2 |
| agy-cli + gpt-5.6-terra | 0.5 | 1 | 0 | 3 |
| agy-cli + gpt-6-luna | 0.625 | 2 | 1 | 3 |
| agy-cli + muse-api | 0.75 | 2 | 2 | 2 |
| agy-cli + muse-cli | 0.875 | 4 | 2 | 3 |
| claude-cli + cursor-cli | 0.5 | 1 | 1 | 2 |
| claude-cli + gpt-5.6-terra | 0.75 | 2 | 0 | 2 |
| claude-cli + gpt-6-luna | 0.875 | 3 | 1 | 2 |
| claude-cli + muse-api | 0.75 | 2 | 2 | 2 |
| claude-cli + muse-cli | 0.875 | 4 | 2 | 3 |
| cursor-cli + gpt-5.6-terra | 0.5 | 0 | 0 | 2 |
| cursor-cli + gpt-6-luna | 0.375 | 0 | 0 | 2 |
| cursor-cli + muse-api | 0.75 | 1 | 1 | 0 |
| cursor-cli + muse-cli | 0.375 | 1 | 1 | 3 |
| gpt-5.6-terra + gpt-6-luna | 0.875 | 2 | 0 | 2 |
| gpt-5.6-terra + muse-api | 0.5 | 0 | 0 | 2 |
| gpt-5.6-terra + muse-cli | 0.625 | 2 | 0 | 3 |
| gpt-6-luna + muse-api | 0.625 | 1 | 1 | 2 |
| gpt-6-luna + muse-cli | 0.75 | 3 | 1 | 3 |
| muse-api + muse-cli | 0.625 | 2 | 2 | 3 |

**Tie-break:** not enabled: 0 of the judges meet the PASS-authority gates (three are needed so that every vote carries authority)
**Failover:** not enabled: 0 judge(s) meet the PASS-authority gates; a backup must earn the same authority as the judge it replaces
**Sample:** 4 NON_PASS case(s) observed; 73 are needed with zero false PASS to bound the false-PASS rate at 0.05. Small-sample results cannot enable either option.
