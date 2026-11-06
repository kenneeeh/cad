# First substantial hybrid experiment

**Completed one campaign. Conclusion: benefit from LLM guidance is inconclusive.**
The hybrid's best noisy TD3 policy sample scored **0.598883**, versus approximately
**0.573** in the selected standalone plot. All ten new LLM proposals were infeasible,
and the later interventions did not improve the best result. This is an observed
single-run comparison, not evidence that replay injection caused the difference.

Date: 2026-11-05. Existing `gemini-3.8-flash-low`, two native roles, seven MCP tools.
CLI status SUCCESS, exit 0. No second campaign, standalone rerun, commit or push.

## Selected existing baseline

Used [2026-11-05--17-07-29](../output_figs/2026-11-05--17-07-29/params.json).
Its episode plot contains 100 episodes and its maximum-reward plot reaches about
1,000 environment steps. Its recorded settings are seed 123456, noise 0.1,
batch 64, actor/critic learning rates 0.001, gamma .99, tau .005, actor interval 2,
hidden size 256 and replay capacity 1,000,000. Current episode horizon is 10.

**T=1000 includes w=200 warmup**, leaving **800 learning steps**. The hybrid
therefore used **400 + 400 training steps**, matching this existing baseline rather
than running an unmatched extra 200 learning steps. All saved learning settings
were read directly from that baseline's params.json.

The baseline plot labels match current targets: gain >=200 V/V, noise <=30 mV RMS,
PM >=60 deg, rising slew >=30 V/us, UGBW >=100 MHz. Its displayed best satisfies
these five constraints. Area/current are optimization scales, not hard limits.
However, no raw history, actor checkpoint, simulator/source hashes or elapsed-time
audit accompanies this run. Its reward **0.573 is rounded plot evidence**; exact
measurement equivalence and baseline first-feasible step cannot be established.

The only detailed historical CSV belongs to an older run: 1,617 of its 1,721 rewards
and 238 feasibility flags disagree with current configuration. It was inspected
but excluded from direct comparison; it was not silently re-scored as original
current-target evidence. No baseline files were overwritten.

## Actual campaign and progression

Initial design plus seven guided proposals produced eight pending records.
`warmup(192)` imported them and added 192 random transitions, giving exactly 200
warmup entries with zero gradient updates. After train(400), three further LLM
evaluations entered the same buffer immediately; the second train(400) continued.

| Checkpoint | Cumulative attempts | Replay entries | Best LLM reward | Best policy reward | Best combined reward | Feasible evaluations so far |
|---|---:|---:|---:|---:|---:|---:|
| Guided exploration | 8 | 0; eight pending | -0.811551 | -- | -0.811551 | 0 |
| Random warmup complete | 220 | 200 | -0.811551 | -- | -0.587648 | 0 |
| First 400 learning steps | 660 | 600 | -0.811551 | 0.598883 | 0.598883 | 3 |
| Three interventions | 663 | 603 | -0.811551 | 0.598883 | 0.598883 | 3 |
| Final 800 learning steps | 1103 | 1003 | -0.811551 | 0.598883 | 0.598883 | 8 |

Exact cost: **11 LLM-path evaluations + 192 random steps + 800 policy steps +
100 measured resets = 1,103 ngspice attempts**. Limit: 1,200; 97 unused. Reset
counts were 20 for warmup and 40 per training batch. There were zero simulator
failures and no additional simulation for insertion. All **11** LLM-path records
(one supplied initial design plus ten actual model proposals) were inserted once.

Each training batch made 400 critic and 200 delayed actor updates: **800/400** in
total. One MCP process/session retained the learner and buffer; cumulative policy
steps 0 -> 400 -> 800 and memory 200 -> 600 -> 603 -> 1003 agree with the actual
insertion feedback and duplicate-ID checks. No networks or optimizers restarted.

The first feasible policy sample occurred at **learning step 213**, total attempt
**454**. It was also the final best. Training batch 2's own best was **0.428158**,
so the best-ever curve stayed flat after step 213. Eight of 800 noisy policy
evaluations were feasible; all random and LLM evaluations were infeasible.

Data: [checkpoints.csv](runs/meaningful_hybrid_20261105_213240/checkpoints.csv),
[800-step policy history](runs/meaningful_hybrid_20261105_213240/policy_progress.csv),
[LLM reward/time history](runs/meaningful_hybrid_20261105_213240/llm_progress.csv),
[full summary](runs/meaningful_hybrid_20261105_213240/summary.json).
LLM elapsed checkpoints use existing simulator-output timestamps, approximately
measurement-completion time, rather than adding a logging framework.

![Hybrid policy progression](runs/meaningful_hybrid_20261105_213240/learning_progress.png)

[LLM best reward versus elapsed time](runs/meaningful_hybrid_20261105_213240/llm_progress.png)
reached -0.811551 during initial guidance and never improved during intervention.
The baseline line in the learning plot is its saved final best, not a reconstructed
standalone learning trajectory.

## Actual model modifications

G1-G7 each modify the supplied initial design independently. I1-I3 modify G2.
Values are absolute; lengths below are um unless nm is shown, capacitance pF,
resistance ohm, and m-prefixed parameters are multiplicities.

| Proposal | Changed physical values | Reward |
|---|---|---:|
| G1 | cap=.8, res=2000 | -0.920148 |
| G2 | cap=1, mn4=22, mp1=14, res=2500 | -0.811551 |
| G3 | cap=.9, mn3=22, mp3=24, wn3=2, wp3=2.5, res=1800 | -1.318024 |
| G4 | cap=.9, ln1=180 nm, lp3=180 nm, res=2200 | -1.454625 |
| G5 | cap=1.1, mn4=20, mp1=18, wp1=2.5, res=2200 | -1.582810 |
| G6 | cap=.7, mn3=20, mn4=18, mp1=12, mp3=22, res=1500 | -0.936018 |
| G7 | cap=.8, ln3=45 nm, ln4=45 nm, lp1=90 nm, res=2000 | -1.070341 |
| I1 | cap=.6, mn3=24, wn3=2.25, res=3500 | -1.280544 |
| I2 | cap=.7, ln1=180 nm, lp3=180 nm, mn3=22, res=3200 | -1.425614 |
| I3 | cap=.6, mn3=20, mp3=22, wp1=2.5, res=3000 | -1.332448 |

The model varied bias/load/driver sizing and channel lengths as well as compensation;
no physical modifications were prescribed in the prompt. Full base-relative changes,
IDs and original hypotheses are in [llm_proposals.csv](runs/meaningful_hybrid_20261105_213240/llm_proposals.csv).

## Best circuits and final actor

The best combined design is the **TD3-generated**
`design_fb0a6ba63b9847c8961dedb37c29896b`, reward **0.5988832864287164**.
All 20 SI parameters are retained in
[best_policy.json](runs/meaningful_hybrid_20261105_213240/best_policy.json).

| Specification | Best TD3 design | Hard requirement |
|---|---:|---|
| Gain | 832.073 V/V | >=200: pass |
| Noise | 16.8101 mV RMS | <=30: pass |
| Phase margin | 66.3438 deg | >=60: pass |
| Rising slew | 55.0406 V/us | >=30: pass |
| UGBW | 116.251 MHz | >=100: pass |
| Area | 696.778 um^2 | Optimization scale 2000 um^2 |
| Current | 290.417 uA | Optimization scale 200 uA |

The [best LLM design, G2](runs/meaningful_hybrid_20261105_213240/best_llm.json)
scored -0.811551 and failed gain, PM and UGBW. The random-warmup best was -0.587648.
Neither should be reported as a learned-policy result.

**Final deterministic actor quality is unavailable:** none of the existing seven
MCP tools exposes a noise-free actor evaluation. No new evaluation API/framework
was added. The last noisy policy sample scored -0.521932 and failed gain; this
single noisy action does not measure the deterministic final actor either.

## Comparison

| Metric | Existing standalone | Hybrid |
|---|---|---|
| Warmup entries | 200 random | 8 LLM-path + 192 random |
| Learning steps | 800, inferred from T-w | 800, audited |
| Best policy reward | Approximately 0.573, post-warmup plot | 0.598883, audited |
| Final deterministic actor reward | Unavailable | Unavailable |
| First feasible policy step | Not saved | 213; attempt 454 |
| Best overall reward | Approximately 0.573 | 0.598883 |
| LLM experiences | 0 | 11 total; 8 warmup + 3 intervention |
| Wall-clock runtime | Not saved | 421.301 seconds |
| LLM input/output tokens | 0 | 196,726 / 6,437 |
| Actual simulator attempts | About 1100 inferred; no failure audit | 1103 audited |

[comparison.csv](runs/meaningful_hybrid_20261105_213240/comparison.csv) retains the
same availability distinctions. The observed best-sample difference is about
**+0.026 reward**, not a statistically supported improvement. The original runner
did not seed Gym's action space, whereas the MCP wrapper does; source/version/PVT
hashes and exact initial network state were not saved for the baseline. Matching
numeric settings and the plot's target labels therefore does not make this a
controlled paired experiment. Baseline hardware/runtime is also unknown.

## Runtime, errors and interpretation

Wall clock **421.301 seconds**. CLI-reported input **196,726**, output **6,437**,
total **203,163 tokens**; separately reported cache reads **389,135**. Cache reads
are not added to that total. These are exposed CLI fields, not independently
verified specialist-backend billing totals.

One native specialist was invoked and later messaged on the same ID. The coordinator
provided two public consultation summaries. Separate specialist reply payloads
are not exposed in the stream, so their exact contribution remains unverified.
One native step 28 has state ERROR/type unknown without diagnostic detail; the
campaign continued and all three numerical batches succeeded.

An off-grid cap=0.65 pF intervention was rejected before simulation and corrected
to 0.6 pF. The coordinator's final narrative incorrectly reported warmup reward
and specs for a real warmup ID; the saved value is -0.587648. It also called mp1
the input pair and mn3 the second-stage driver. The unchanged netlist instead has
mn1/mn2 as input pair, mp1/mp2 as mirror load, mn3 as diode bias reference, mp3 as
second-stage PMOS amplifier. Its area statement of 0.70 nm^2 was wrong; the best
area is 696.778 um^2. Claims of robustness or proven gm/pole mechanisms are not
established by these fixed-testbench measurements.

**Assessment: inconclusive for LLM-assisted learning.** The policy-generated best
is numerically promising against the available standalone endpoint. Direct LLM
design quality and later intervention were unhelpful in this realization: no
feasible proposals and no new best after intervention. One stochastic run, different
random warmup and incomplete baseline evidence prevent causal attribution to replay.

Suggested next experiment, not executed: record paired standalone/hybrid trials
with identical action-space seeding, setup hashes and initialization, repeated seeds,
separate policy-only and deterministic final-actor evaluations, and charged LLM
preparation cost. Review device-role interpretation and retain actual native
specialist replies first. No further campaign was run here.

## Files created or modified

Only the execution blockers were adjusted: `llm/mcp_server.py` and
`llm/td3_session.py` raise the per-call limit from 50 to 500; total-budget checks
remain. `llm/.agents/mcp_config.json` raises request timeout from 120 to 600 seconds
for long batches (the first train call took 118.97 s). `llm/README.md` documents the
new limit. No learning equations, hyperparameters, sampling or simulator code changed.

This report and the single run directory are new. Its named analysis artifacts are
baseline.json, historical_csv_check.json, preflight_result.json, prompt.txt,
run_once.py, analyze.py, cli_summary.json, final_result.json, summary.json,
checkpoints.csv, policy_progress.csv, llm_progress.csv, llm_proposals.csv,
comparison.csv, learning_progress.png, llm_progress.png, best_policy.json,
best_llm.json, best_combined.json, public_events.jsonl and stderr.txt. The same
directory contains before/launch/baseline hashes, before/ snapshots, zero-budget
preflight artifacts and actual candidate/netlist/output/figure files. An exhaustive
path list is [files_created.txt](runs/meaningful_hybrid_20261105_213240/files_created.txt).

## Changes outside `llm/`

**One existing Codex test file changed:**
`codex_tests/test_persistent_session.py`, line **156**, in
`TestPersistentSession.test_budget_rejects_whole_batch_before_initialization`:
the invalid-boundary example changed **51 -> 501** to match the permitted maximum
500. This changes only the test expectation; standalone TD3 behavior is unaffected.
No other source file outside llm/ changed. The existing td3_runner.py working-tree
diff predates this task and was preserved.

The larger schemas/budget guards passed a zero-attempt stdio preflight. The real
192/400/400 calls then exercised the enlarged limits. Offline validation checked
all 1,003 records, with zero extra simulator calls. Protected TD3/environment/reward/
netlist/measurement hashes match; all **129** historical output files are unchanged.
No dependencies, agent/tool additions, refactor, standalone rerun, commit or push.
