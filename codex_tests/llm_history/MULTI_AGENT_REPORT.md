# Milestone 4 implementation and measured experiment

Date: 2026-11-05. Native Antigravity CLI 1.5.1, model `gemini-3.8-flash-low`
for the coordinator and inherited specialist model. No model change, new Python
dependency, TD3 invocation or circuit/reward/target/measurement edit was made.
Sessions 3&4 were not available locally; native configuration was checked against
the installed CLI and the official references linked in README.md.

## Results and status

One new sizing experiment used exactly **five full ngspice attempts**, in one MCP
server session, beginning with the unchanged `initial_design.json`. Calls 4 and 5
were feasible. Python selected call 5 by actual reward, **0.8596666204924799**;
the coordinator's chosen ID agrees. All 20 parameters were valid on the YAML
grids; all measured specs, normalized specs and rewards were finite.

The CLI returned a valid final structured report, then terminal status **ERROR**:
`RESOURCE_EXHAUSTED (429): You have exhausted your capacity on this model. Resets in 0s.`
The process exit code was 0 but the launcher correctly returned failure because
the envelope status was ERROR. Simulator results and the final report were retained.
This is a model-service completion problem, not a simulator or reward failure.
It has not been hidden, retried as a new optimization campaign, or relabelled SUCCESS.

Evidence: [recorded_run.json](recorded_run.json) contains the compact shareable
summary, full five-design history and consultation summaries. Original local audits,
filtered handoffs and final CLI envelope remain in
`../runs/multi_agent_26459rp8/` (ignored runtime data). Recorded numeric predictions
were checked offline without further model or simulator calls; the original
pre-call audits and agent assessments remain unchanged.

## What the agents actually did

| Full call | Changes from previous design | Reward | Failed hard constraints |
|---|---|---:|---|
| 1 | Unchanged initial design | -0.394829684 | gain, slewRate |
| 2 | cap 3.5 -> 1.5 pF; res 6000 -> 3500 ohm | -0.110125628 | gain, slewRate |
| 3 | wn4 1.5 -> 2.0 um; wn1 1.75 -> 2.25 um | 0.008374608 | slewRate |
| 4 | wn4 2.0 -> 2.25 um | 0.858933837 | none |
| 5 | mn5 17 -> 16 | **0.859666620** | none |

The diagnostician prioritized the severe slew deficit and then gain. The
strategist recommended local refinement using the initial phase-margin reserve.
The designer chose the changes above; none was prescribed in the experiment
prompt. Reducing compensation improved slew less than predicted and nearly
consumed the PM margin. Increasing input/tail widths subsequently improved gain
and slew in these measurements. The final sink-multiplicity reduction produced
a small measured current reduction while preserving feasibility.

These are observed input/output associations, not verified transistor operating
points. Statements about branch current, gm or the unique physical cause remain
hypotheses. In particular, a 12.5% width change does not prove a 12.5% tail-current
change; no DC analysis was introduced.

The best design differs from the starting design only in cap=1.5 pF, res=3500 ohm,
wn1=2.25 um, wn4=2.25 um and mn5=16. All 20 actual SI parameters are retained in
the recorded history. Best simulation ID: `TwoStage_1793894982_aemsxlafax`.

| Measured spec | Best value | Hard requirement |
|---|---:|---:|
| Gain | 278.125 V/V | >=200 |
| Integrated noise | 4.35485 mV RMS | <=30 mV RMS |
| Phase margin | 66.2169 deg | >=60 |
| Rising-edge slew rate | 16.6372 V/us | >=15 |
| UGBW | 27.8621 MHz | >=1 MHz |
| Current | 148.694 uA | optimization scale 200 uA |
| Area | 831.8005 um^2 | optimization scale 2000 um^2 |

Area/current scales are not hard constraints. Feasibility comes from the five
explicit constraint checks, not the sign of the reward: call 3 has a positive
reward but still violates slew rate.

## Prediction audit: useful designs do not prove accurate predictions

All candidates supplied the four pre-call decision summaries. The agents omitted
the optional structured `predictions` argument, placing explicit intervals in
`decision.predicted_effects` instead. The recorder now checks both structured
intervals and the narrow text form `metric in [lower, upper] unit`, including
uA/MHz conversion. It does not infer numeric predictions from arbitrary prose.
The experiment template now explicitly requests structured intervals whenever
numeric ranges are stated, to provide immediate MCP feedback on future runs.

The following contradictions are preserved and flagged deterministically:

- Call 4 was labelled supported. Predicted slew was [15.5,16.5] V/us; actual
  16.5204 lies outside it. Gain [205,230] versus 272.988 and PM [63,65] versus
  66.3991 also miss. Those higher measurements can be useful, but are not accurate
  interval predictions. No tolerance was widened to make them pass.
- Call 5 was labelled supported. Predicted current [141,147] uA versus 148.694,
  slew [15.2,16.5] versus 16.6372 and gain [260,275] versus 278.125 miss their
  stated ranges. PM passes [63,67]. The predicted current drop of roughly 3-4 uA
  was only 0.1945 uA in the measured difference.

Calls 2 and 3 also missed multiple ranges and were already labelled unsupported.
History stores each metric's check, the model's original assessment and an
`assessment_contradiction` flag. No separate LLM numerically evaluates success.
Unparseable qualitative predictions remain human interpretations; this is not a
general natural-language theorem prover.

## Native communication and access validation

The zero-budget synthetic-packet audit is in
[communication_check.json](communication_check.json). It created the intended
three native specialists, received their replies and recognized sentinel CHECK-42.
The diagnostician correctly separated slew/gain violations from PM's small margin.
The designer confirmed all 20 parameters and gave an advisory grid-valid change.
The strategist correctly halted experimentation at zero remaining calls.

Specialists reported only native messaging/task/resource tools and no simulator,
shell or write tools. This agrees with the native `inheritMcp: false`, empty tool
allowlist, command policy and invocation restrictions. They did not execute
simulation-consuming tools; the server budget was additionally zero. This checks
normal native capabilities, not resistance to every possible platform vulnerability.
The audit's final envelope also encountered the capacity error after returning
its structured result; the communication assertions passed while terminal status
remained ERROR.

In the sizing run there were **3 native specialist instances**, **7 native
follow-up send_message calls**, and **10 reported consultations**. The existing
instances were reused. Public native handoff metadata records IDs and initial
packets; consultation summaries record engineering advice rather than private
reasoning. No custom Python agent scheduler was added.

Discovery/setup issues were retained in ignored runs rather than disguised:
the first check had no delegation tool; the next invoked specialists but lacked
structured finish; an invalid explicit `call_mcp_tool` component failed before
any model tokens. The working coordinator explicitly enables native delegation,
messaging, wait and finish, while inheriting MCP through native configuration.
CLI options are placed before `-p` to avoid ambiguous headless argument handling.

## Preliminary V1 comparison

| Measure | Historical V1 single agent | New multi agent |
|---|---:|---:|
| Best actual reward | -0.0610232363 | 0.8596666205 |
| Feasible design found | No | Yes, calls 4 and 5 |
| Actual full simulator attempts | 5 | 5 |
| Wall-clock seconds | 39.021 | 168.492 |
| CLI duration seconds | 35.92795 | 165.836127 |
| Summed simulation-tool seconds | 0.7051 | 0.8662 |
| CLI-reported input tokens | 63,565 | 219,110 |
| CLI-reported output tokens | 1,785 | 9,955 |
| CLI-reported total tokens | 65,350 | 229,065 |
| CLI-reported cache-read tokens | 0 | 133,070 |
| Native specialist instances / follow-ups | 0 / 0 | 3 / 7 |
| Terminal CLI envelope | SUCCESS | ERROR after final report (capacity) |

The CLI figures are the usage fields actually exposed, not an independently
verified billing total across specialist backends. Credits and exact backend
LLM-call counts are unavailable; `num_turns` is not a backend-call count.
Do not add cache tokens to the displayed total or infer a dollar cost from these logs.

**Measurement confound:** upstream commit fd7d1ef changed slew measurement from
averaging rise/fall magnitudes to rising-only after the historical V1 run. The
initial reward is now -0.39483 rather than V1's approximately -0.44244. This prevents
an architecture-only reward comparison. The same current simulator/reward/targets
were reused here without editing them. No extra five-call V1 run was made.

The new run has clearer attribution of diagnosis, proposal and strategy, and more
explicit failed predictions. It also costs more reported tokens and elapsed time.
One stochastic run, the measurement confound and service errors preclude claiming
architectural superiority or a global optimum. Feasibility is only for the current
testbench and supplied measurements, not independent TA certification or PVT robustness.

Setup checks are separate from the sizing table: the four saved zero-simulation
checks reported totals of 91,095, 90,528, 0 and 55,450 tokens respectively
(237,073 combined); the brief discovery-only query reported another 5,625.
No setup check launched ngspice. These are development/debug overhead, not hidden
optimization runs, and are not included in the five-call comparison.

## Validation and exact change list

Eight focused tests in `codex_tests/test_multi_agent.py` and six existing mocked
MCP regression tests pass. They run no model and no actual simulator. The saved
experiment test reuses CircuitEnv normalization/reward, verifies all grids and
finite values, and checks the recorded best reward and feasibility. The stdio
test actually discovers the MCP schema and verifies a valid design is rejected
at budget zero. Tests and scratch artifacts stay in codex_tests.

Modified existing files:

- `llm/mcp_server.py`: optional bounded pre-call decisions/predictions, deterministic
  interval feedback, and a zero-budget discovery mode. Original parameter-only
  and hypothesis calls remain valid. No reward/measurement implementation changed.
- `llm/run_experiment.py`: mode selection, native workspace/agent selection,
  final/filtered-stream recording, compact memory, numeric prediction checks and
  explicit error metadata. Same runner for both modes; no Python delegation loop.
- `llm/README.md`: launch commands and links to the new workflow/report.

New framework files, all under `llm/multi_agent/`:

- `.agents/agents/coordinator.md`, `circuit-diagnostician.md`,
  `experiment-designer.md`, `optimization-strategist.md`: four native roles.
- `.agents/skills/opamp-physics/SKILL.md`,
  `.agents/skills/sizing-experiments/SKILL.md`: reusable qualified circuit knowledge.
- `.agents/agents.json`, `.agents/skills.json`: local native discovery manifests.
- `GEMINI.md`: scoped override allowing native delegation in this mode.
- `agent_settings.json`: session-only simulator allow and shell/edit/web denies.
- `experiment.md`: bounded experiment template without prescribed sizing changes.
- `communication_check.md`: synthetic zero-budget access/communication prompt.
- `communication_check.json`: compact observed access/communication evidence.
- `recorded_run.json`: compact actual five-call experiment and decisions.
- `README.md`: usage, file purposes, memory/tool rules and complete oral-exam flow.
- `REPORT.md`: this measured report and limitations.

New local validation file: `codex_tests/test_multi_agent.py`. Runtime run directories
are ignored. V1's GEMINI.md, experiment.md, settings and initial design are unchanged.
No commit, push, credential change, package installation, TD3, CircuitEnv, YAML or
ngspice-measurement edit was performed for this task.

## Remaining manual steps

No manual installation or account change is needed. The existing sign-in and MCP
registry were reused. After model capacity is available, a future explicitly
requested run can use the documented command; no additional campaign was run here.
A controlled architecture comparison would require a separate V1 run with the
same current slew measurement and repeated trials, as future work. Keep each run's
actual error status and prediction audit when assessing it.
