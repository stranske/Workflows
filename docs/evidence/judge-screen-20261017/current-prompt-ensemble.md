## Judge ensemble analysis

8 cases (4 NON_PASS). **Nothing is enabled by this report.**

| Judge | Correct | False PASS | False-PASS upper bound | Invalid | PASS authority |
|---|---:|---:|---:|---:|---|
| claude-cli | 4/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| cursor-cli | 5/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| gpt-5.6-terra | 6/8 | 0 | 0.4899 | 0 | no: false-PASS upper bound 0.4899 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| gpt-6-luna | 6/8 | 0 | 0.4899 | 0 | no: false-PASS upper bound 0.4899 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| muse-api | 4/8 | 4 | 1.0 | 0 | no: 4 false PASS observed; false-PASS upper bound 1.0 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| muse-api:muse-spark-1.2-contributor | 6/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| muse-api:muse-spark-1.3 | 4/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| muse-api:muse-spark-1.3-contributor | 3/8 | 3 | 0.9544 | 0 | no: 3 false PASS observed; false-PASS upper bound 0.9544 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |
| muse-api:muse-wonder-1.0 | 4/8 | 2 | 0.85 | 0 | no: 2 false PASS observed; false-PASS upper bound 0.85 exceeds 0.05 on 4 NON_PASS case(s); 73 are needed with zero errors; approval gate failed or unmeasured: minimum_adjudicated_cases; approval gate failed or unmeasured: minimum_cases_per_category; approval gate failed or unmeasured: task_success_rate_wilson_lower_bound; approval gate failed or unmeasured: false_pass_rate_wilson_upper_bound; approval gate failed or unmeasured: false_fail_rate_wilson_upper_bound; approval gate failed or unmeasured: schema_error_rate_wilson_upper_bound; approval gate failed or unmeasured: paired_success_noninferiority |

### Pairs (production strict-AND contract)

| Pair | Agreement | Both wrong | False PASS | False FAIL |
|---|---:|---:|---:|---:|
| claude-cli + cursor-cli | 0.625 | 2 | 1 | 2 |
| claude-cli + gpt-5.6-terra | 0.75 | 2 | 0 | 2 |
| claude-cli + gpt-6-luna | 0.75 | 2 | 0 | 2 |
| claude-cli + muse-api | 0.5 | 2 | 2 | 2 |
| claude-cli + muse-api:muse-spark-1.2-contributor | 0.75 | 2 | 2 | 2 |
| claude-cli + muse-api:muse-spark-1.3 | 1.0 | 4 | 2 | 2 |
| claude-cli + muse-api:muse-spark-1.3-contributor | 0.875 | 4 | 2 | 2 |
| claude-cli + muse-api:muse-wonder-1.0 | 1.0 | 4 | 2 | 2 |
| cursor-cli + gpt-5.6-terra | 0.625 | 1 | 0 | 2 |
| cursor-cli + gpt-6-luna | 0.625 | 1 | 0 | 2 |
| cursor-cli + muse-api | 0.625 | 2 | 2 | 1 |
| cursor-cli + muse-api:muse-spark-1.2-contributor | 0.625 | 1 | 1 | 1 |
| cursor-cli + muse-api:muse-spark-1.3 | 0.625 | 2 | 1 | 2 |
| cursor-cli + muse-api:muse-spark-1.3-contributor | 0.5 | 2 | 1 | 2 |
| cursor-cli + muse-api:muse-wonder-1.0 | 0.625 | 2 | 1 | 2 |
| gpt-5.6-terra + gpt-6-luna | 1.0 | 2 | 0 | 2 |
| gpt-5.6-terra + muse-api | 0.25 | 0 | 0 | 2 |
| gpt-5.6-terra + muse-api:muse-spark-1.2-contributor | 0.5 | 0 | 0 | 2 |
| gpt-5.6-terra + muse-api:muse-spark-1.3 | 0.75 | 2 | 0 | 2 |
| gpt-5.6-terra + muse-api:muse-spark-1.3-contributor | 0.625 | 2 | 0 | 2 |
| gpt-5.6-terra + muse-api:muse-wonder-1.0 | 0.75 | 2 | 0 | 2 |
| gpt-6-luna + muse-api | 0.25 | 0 | 0 | 2 |
| gpt-6-luna + muse-api:muse-spark-1.2-contributor | 0.5 | 0 | 0 | 2 |
| gpt-6-luna + muse-api:muse-spark-1.3 | 0.75 | 2 | 0 | 2 |
| gpt-6-luna + muse-api:muse-spark-1.3-contributor | 0.625 | 2 | 0 | 2 |
| gpt-6-luna + muse-api:muse-wonder-1.0 | 0.75 | 2 | 0 | 2 |
| muse-api + muse-api:muse-spark-1.2-contributor | 0.75 | 2 | 2 | 0 |
| muse-api + muse-api:muse-spark-1.3 | 0.5 | 2 | 2 | 2 |
| muse-api + muse-api:muse-spark-1.3-contributor | 0.625 | 3 | 3 | 2 |
| muse-api + muse-api:muse-wonder-1.0 | 0.5 | 2 | 2 | 2 |
| muse-api:muse-spark-1.2-contributor + muse-api:muse-spark-1.3 | 0.75 | 2 | 2 | 2 |
| muse-api:muse-spark-1.2-contributor + muse-api:muse-spark-1.3-contributor | 0.625 | 2 | 2 | 2 |
| muse-api:muse-spark-1.2-contributor + muse-api:muse-wonder-1.0 | 0.75 | 2 | 2 | 2 |
| muse-api:muse-spark-1.3 + muse-api:muse-spark-1.3-contributor | 0.875 | 4 | 2 | 2 |
| muse-api:muse-spark-1.3 + muse-api:muse-wonder-1.0 | 1.0 | 4 | 2 | 2 |
| muse-api:muse-spark-1.3-contributor + muse-api:muse-wonder-1.0 | 0.875 | 4 | 2 | 2 |

**Tie-break:** not enabled: 0 of the judges meet the PASS-authority gates (three are needed so that every vote carries authority)
**Failover:** not enabled: 0 judge(s) meet the PASS-authority gates; a backup must earn the same authority as the judge it replaces
**Sample:** 4 NON_PASS case(s) observed; 73 are needed with zero false PASS to bound the false-PASS rate at 0.05. Small-sample results cannot enable either option.
