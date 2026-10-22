# Verification standards: what they cost, what they buy, and what an approval standard should be

Date: 2026-10-18 (Workflows, evidence under `docs/evidence/judge-screen-20261017/`).
Reproduce the numbers with `python -m tools.verifier_standards_model` and the data scripts named below.

## 1. Bottom line

1. **A verifier is only worth running where defects are common or expensive.** At the measured costs of verifying (about 0.3 hours added per verified PR) and the assumed cost of repairing an escaped defect (10 rework rounds), a verifier with the best measured operating point adds delay unless more than about 6.6% of the PRs it sees are truly bad. At 30 rework rounds per escape the break-even falls to about 2%. The two numbers that decide it, the base rate of bad PRs and the repair cost, are the two we measure worst.
2. **Strictness is the expensive part, not verification.** A verifier that blocks hard on every non-PASS adds about 1.8 delay-hours per verified PR against 0.65 for the same verifier with a two-hour time box, because the flags on good PRs are persistent: the same two good PRs were flagged by all five judges. Hard blocking uses about 24 of the owner's 30 weekly minutes on persistent flags alone. A verifier that rejects everything adds 8.3 hours per PR and needs 126 human minutes a week: nothing moves.
3. **The judges are not statistically distinguishable at the data we can get.** gpt-6-luna missed 0 of 19 bad cases, the incumbent gpt-5.6-terra 2 of 19 (Fisher p = 0.49). Only Cursor and the Muse models are measurably worse (luna against Cursor p = 0.02).
4. **Zero-error approval standards approve nothing real.** A candidate whose true false-PASS rate is 5%, half the incumbent's 10%, passes the 73-case zero-error standard 2.4% of the time and the 35-case standard 17% of the time. The incumbent itself would pass them 0.05% and 2.5% of the time. Only a perfect model passes, so promotion was unreachable by construction.
5. **What is at stake in a judge swap is small**, about 0.6 delay-hours a week and a few cents. An approval process should cost less than that, be reversible, and be monitored; it should not need hundreds of cases.

**Recommended standards** (section 6): verify only the PR classes where the measured bad-outcome rate is high; use a single judge with a time-boxed block of at most two hours, then merge with an auto-filed follow-up; never hard-block. Approve a candidate model when its false-PASS count on the fixed evaluable set is no more than the incumbent's plus one, its false-FAIL count no more than the incumbent's plus two, and a 14-day shadow shows no live regression, with automatic rollback.

## 2. What was measured, and what each number means

| Quantity | Value | Evidence class |
| --- | --- | --- |
| Merged keepalive PRs, 6 repositories, 2026-09-15 to 2026-10-17 | 161 (about 34 a week), median 1.4 hours from open to merge | production use |
| Share of those PRs with a verification result | 63 of 161 (39%) | production use |
| Added cycle time of one verification round (median, within repository) | +0.27 h (Workflows), +0.46 h (consumers) | production use |
| PRs that merged with the verification state `failed` | 29 of 161 | production use: verification does not block merges today (some are infrastructure failures such as an expired login, not verdicts) |
| Later breakage (reverted, reworked, broke later) among verifier-judged runs, verdict PASS | 16 of 158 (10.1%) | production use, Brain `outcomes`; selection-confounded |
| Same, verdict NON_PASS | 33 of 255 (12.9%) | production use; the two rates overlap |
| Same, runs with no verifier verdict | 36 of 4,521 (0.8%) | production use; verified PRs are the harder ones |
| Judge false-PASS and false-FAIL | table in section 3 | benchmark on 35 cases (16 good, 19 bad), CLI harness |
| Persistence of false flags | the 2 flagged good PRs common to all 5 judges, 1 more flagged by 2 judges | benchmark |
| Cost of a verification model call | about 0.5 cents (terra), 0.03 cents (luna) per case | benchmark, CLI usage |

Two things this table says about how far to trust the rest. First, the production outcome data shows **no detectable difference between PASS and NON_PASS verdicts** in later breakage; the sample is small and selection-confounded, but it means the benchmark's detection rates may not carry over to production. Second, verification already does not gate merging, so "stricter" is a policy change, not a tuning of the status quo.

## 3. Operating points of the standards considered

Measured on the 35 comparable cases. The 22 failed-CI mutants are left out: the verifier workflow already floors a red CI at CONCERNS, so a model miss there costs nothing.

| Standard | Bad PRs that still pass | Good PRs flagged |
| --- | ---: | ---: |
| No verification | 100% | 0% |
| gpt-6-luna alone | 0/19 (0%; upper bound 17%) | 3/16 (19%) |
| gpt-5.6-terra (incumbent) alone | 2/19 (11%) | 3/16 (19%) |
| Claude CLI alone | 2/19 (11%) | 2/16 (12%) |
| Cursor CLI alone | 6/19 (32%) | 2/16 (12%) |
| Muse 1.2 contributor tier alone | 7/19 (37%) | 2/16 (12%) |
| Both luna and terra must pass | 0/19 (0%) | 3/16 (19%) |
| Two of luna, terra, Claude must pass | 1/19 (5%) | 3/16 (19%) |
| All three must pass | 0/19 (0%) | 3/16 (19%) |
| Reject everything | 0% | 100% |

Requiring a second judge changed nothing measurable here: the flagged good PRs are the same ones, and the combinations never beat luna alone. Every bad case any judge missed comes from five source PRs (fineart-754, fineart-755, workflows-2528, 2831 and 2832), and the 19 bad cases come from 12 source PRs because the mutants of one PR share their input, so they are fewer independent observations than they look.

## 4. The cost model

All costs are wall-clock delay to finishing the work, in hours per verified PR, so the cost of a repair and of waiting are on one scale.

* A verification round adds 0.3 hours (measured).
* A false flag on a good PR costs one fix round, 1.0 hour (assumed). If the flag is **persistent** (every judge repeats it, 2 of 3 flagged cases here), a fix round cannot clear it: under a hard block it waits for a human, 12 hours (assumed), and costs 15 human minutes (assumed); under a time box it waits the box, 2 hours, then merges.
* A bad PR that is caught costs one fix round, 1.0 hour. One that escapes costs `ratio` fix rounds to repair later (assumed 3, 10 or 30).
* The base rate of bad PRs is swept at 2%, 5% and 10% (measured: 1.8% overall, 10 to 13% among verifier-judged runs).
* Prices are for the 13.3 verified PRs a week (34 a week, 39% verified).

### 4.1 Central case: 5% bad, escape costs 10 fix rounds

Delay-hours per verified PR; no verification costs 0.50.

| Standard | Advisory | Time-boxed (2 h) | Hard block | Human min/week (hard) |
| --- | ---: | ---: | ---: | ---: |
| gpt-6-luna | 0.59 | 0.65 | 1.83 | 24 |
| gpt-5.6-terra (incumbent) | 0.62 | 0.69 | 1.88 | 24 |
| Claude CLI | 0.61 | 0.60 | 1.39 | 16 |
| Cursor CLI | 0.66 | 0.69 | 1.48 | 16 |
| Two of three judges | 0.60 | 0.67 | 1.86 | 24 |
| Reject everything | n/a | n/a | 8.3 | 126 |

At these assumptions every standard costs more delay than no verification, a hard block costs far more, and the owner's weekly budget is 80% consumed by the hard block's persistent flags alone.

### 4.2 Where verification pays: gain in delay-hours per PR against no verification (positive = worth it)

Single judge (luna operating point), time-boxed block:

| Bad rate | escape = 3 rounds | 10 rounds | 30 rounds |
| --- | ---: | ---: | ---: |
| 2% | -0.57 | -0.43 | -0.03 |
| 5% | -0.50 | -0.15 | +0.85 |
| 10% | -0.38 | +0.32 | +2.32 |

Break-even bad rate: 6.6% at 10 rounds and 2.1% at 30 rounds for the time box; 17.6% and 6.1% for a hard block; 7.1% and 2.2% for advisory.

### 4.3 How much of the benchmark's detection survives in production

The benchmark's bad cases remove a file the plan requires, an obvious class. At a 10% bad rate and a 10-round escape cost, the time-boxed standard gains +0.32 hours per PR if all detection carries over, -0.13 if half does and -0.36 if a quarter does. Production outcomes show no detectable separation between PASS and NON_PASS, so a realism factor well below 1 is plausible and the case for verifying low-risk PRs weakens further.

## 5. Approval standards for a model

The question is when a candidate verifier may replace the incumbent. All figures: incumbent true false-PASS rate 10%; chance that a standard approves a candidate with the true rate shown (exact binomial).

| Candidate's true false-PASS rate | Zero errors in 73 | Zero errors in 35 | Zero errors in 16 | At most the incumbent's count (19 cases) | At most incumbent's plus one (19) | Plus one (35 cases) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% (perfect) | 100% | 100% | 100% | 100% | 100% | 100% |
| 5% (twice as good) | 2.4% | 17% | 44% | 82% | 94% | 94% |
| 10% (same) | 0.05% | 2.5% | 19% | 61% | 80% | 73% |
| 20% (twice as bad) | 0% | 0% | 2.8% | 26% | 43% | 25% |
| 30% | 0% | 0% | 0.3% | 8% | 17% | 4% |
| 40% | 0% | 0% | 0% | 2% | 5% | 0.4% |

* **Absolute zero-error standards** reject a model twice as good as the incumbent 98% of the time at 73 cases, and reject the incumbent 99.95% of the time. They are a test for perfection. Loosening the bound to 0.20 still rejects a twice-as-good model 56% of the time. This is why no model could be promoted.
* **Relative standards** treat the incumbent as the bar. At 19 cases they cannot tell a twice-as-bad candidate from the incumbent (43% approval); at 35 cases with a tolerance of one they approve an equal model 73% of the time and a three-times-worse one 4%.
* **Value at stake.** A swap changes expected delay by (difference in false-PASS rate) x (bad rate) x (escape minus fix cost) x (verified PRs a week). For luna against terra the point estimate is 0.105 x 5% x 9 hours x 13.3 = 0.6 delay-hours a week, plus about 7 cents a week of model cost. Wrongly approving a candidate twice as bad as the incumbent costs about the same each week, and live monitoring with rollback bounds it to a few hours. A standard that needs more evidence than those hours cannot pay for itself.

| Approval standard | Cases needed | Wrongly approves a 2x worse model | Rejects an equal model | Time to evidence | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| Absolute, 0.05 bound | 73 bad + 35 good, zero errors | 0% | 99.95% | weeks of captures | unreachable: approves only a perfect model |
| Absolute, 0.10 / 0.20 bounds (current) | 35 bad + 16 good, zero errors | 0% | 97.5% | days | unreachable in practice |
| Never promote | none | 0% | 100% | never | the incumbent decays; a retired model forces an unprepared migration |
| Relative, no worse than the incumbent (19 cases) | 19 bad + 16 good | 26% | 39% | now | too noisy |
| **Relative plus one, then a 14-day shadow with rollback** | 35 bad when available, 16 good | 25% before the shadow, then bounded by rollback | 27% | the corpus plus 14 days | **recommended** |
| Human judgement only | none | n/a | n/a | the owner's minutes | violates the zero-owner-time rule |

## 6. Recommended standards

**Runtime verification.**
1. Verify the PR classes with a high measured bad-outcome rate (executable code, workflows, shared scripts, synced templates) and skip documentation and test-only changes. The Brain shows 10 to 13% later breakage among verifier-judged runs against 0.8% among the rest; both numbers are selection-confounded, so the classes must be re-measured per class.
2. One judge, not two. A second judge changed no measured outcome here, and the three strongest single judges (luna, terra, Claude) are statistically equal.
3. A time-boxed block of at most two hours, then merge with an auto-filed follow-up issue. Never a hard block: persistent flags then consume most of the owner's weekly minutes and any rise in them exceeds the budget.
4. Keep a second judge as insurance only where an escape costs about 30 fix rounds or more (a defect that reaches all 16 consumers through template sync). Its benefit is untested here, since luna alone already missed none of the 19 bad cases, so this is a judgement call, not a measured gain.

**Model approval.**
1. The candidate's false-PASS count on the fixed evaluable set must not exceed the incumbent's plus one, and its false-FAIL count must not exceed the incumbent's plus two, with the corpus floors of 35 bad and 16 good cases.
2. A 14-day shadow in production: record both verdicts on every verified PR, and roll back automatically if the candidate misses a defect the incumbent catches.
3. Absolute bounds are reported, not blocking.
4. Re-tighten the tolerance (plus one to plus zero) when the evaluable corpus passes 100 bad cases.

Under these rules gpt-6-luna would qualify today (0 of 19 against 2 of 19, 3 of 16 against 3 of 16) and would go to the capped API confirmation and then the shadow.

## 7. What would change the conclusion

* **Escape and rework costs** are assumed, not measured. If an escape costs 30 fix rounds, verifying code PRs pays at a 2% bad rate. Measuring the cost of the 16 reverts and breaks in the Brain (time from merge to repair PR) is the single most valuable next measurement.
* **The bad rate by PR class** decides where to verify; it is measured only in aggregate.
* **The benchmark's detection rates** come from 35 cases, 19 of them mutants of five source PRs, on a CLI harness different from the production verifier. They are exploratory.
* **Production separation** between PASS and NON_PASS verdicts is not detectable in 413 runs; if a larger sample shows real separation, the realism factor moves toward 1 and verification is worth more.
* **Persistent flags** are the main cost of strictness. If the flagged good PRs (workflows-2744 and 2746, both labelled clean PASS by realized outcome) carry real defects the labels missed, the false-FAIL rate is overstated and the picture improves for strict standards.

## 8. Checks that would show this is working

| Measure | Check |
| --- | --- |
| Verified PRs blocked longer than the two-hour box | zero, from the keepalive state comments |
| Persistent-flag human minutes per week | under 30, from the owner-question log |
| Later breakage of PRs merged after a PASS against after a non-PASS, by PR class | at least 100 runs per class, re-run of the Brain query |
| Shadow disagreements between candidate and incumbent | listed per PR, any candidate-misses-incumbent-catches triggers rollback |

*Sources: Brain `outcomes` and `runs` (feedback database); the 161-PR sample from `gh pr list` keepalive state comments; `eval57-*` and `pilot-18-*` judge runs in `docs/evidence/judge-screen-20261017/`; `tools/verifier_standards_model.py`; the verifier workflow `reusable-agents-verifier.yml` (CI floor).*
