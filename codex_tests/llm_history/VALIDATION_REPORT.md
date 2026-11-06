# Milestone 4 validation and autonomous sizing — 5 November 2026

These recorded experiments predate upstream fd7d1ef (rising-edge-only slew-rate
extraction). The newer measurement code was pulled before publishing the harness;
this report's numerical results were preserved rather than presented as a rerun.

The existing per-process budget works correctly and was left unchanged. Eight
MCP tests pass. Three same-model diagnostics completed, with diagnostic C also
serving as the single autonomous sizing experiment. It used all five allowed
simulations and improved the best reward, but found **no fully feasible design**.

## Exact changes

| File | Change and reason |
| --- | --- |
| `mcp_server.py` | Added backward-compatible optional `hypothesis`, limited to 300 characters, and stored it in the existing call log. This records a brief prediction supplied before simulation. Counter, lock, simulator calls and reward handling were preserved. |
| `GEMINI.md` | Retained topology, transistor roles, physical bounds, targets, objectives, tool rules and measurement caveats. Removed the starting design, fixed two-call experiment and specific capacitor suggestion. |
| `experiment.md` | New short experiment template with starting parameters, budget, feasibility-first objective and stopping rules. It prescribes no sizing change. |
| `run_experiment.py` | New thin CLI launcher for baseline/tool/autonomous modes. Records actual usage and runtime, joins existing simulator logs with final assessments, computes spec/parameter changes, and selects maximum logged reward. No custom agent loop or reward equation. |
| `.agents/mcp_config.json` | Removed the old fixed two-call environment override. Budget and run directory are inherited from the launcher's environment. |
| `../codex_tests/test_mcp_server.py` | Retained existing tests and added exact budget/invocation counting, hypothesis logging/validation and context-separation checks. |
| `README.md` | Updated launch commands, budgets, log locations, usage measurement and limitations. |
| `VALIDATION_REPORT.md` | This implementation, diagnostic and decision-history report. |

The existing Antigravity user registry's cad-simulator entry also had its fixed
CAD_MAX_SIMULATIONS=2 override removed using `agy mcp add`. It still points at
llm/mcp_server.py and preserves PYTHONDONTWRITEBYTECODE. Authentication and the
default model were not changed. The new per-run environment was verified from
the one-call and five-call audits, including remaining=0 at the correct count.

No dependencies were added. TD3, CircuitEnv, ngspice wrapper, measurement code,
netlist, YAML targets and TA CSV were verified unchanged by hashes. Nothing was
committed or pushed. Earlier test/pilot records remain archived separately.

## Budget verification

CircuitEnv increments counter immediately before its one call to the existing
ngspice wrapper. The wrapper launches exactly one subprocess. Measurement and
normalization do not launch extra ngspice processes. The MCP tool checks the
counter while holding its existing lock, which serializes concurrent requests.
There is no counter reset in the tool. Initialization occurs once per process.

The new focused test mocks the subprocess boundary and verifies a sequence in
one session: rejected input (0 calls), successful simulation (1), rejected input
(still 1), failed simulation (2), then three exhausted-budget requests (still 2).
Subprocess call count equals env.counter at every stage. Existing real-stdio
integration also verifies sequential counters 1 and 2 and rejects the third call.
The test fixture resets state between independent unit tests; production requests
do not execute that fixture. Failed launch attempts consume budget conservatively,
including an executable-start error. Failed netlist generation before launch
does not increment the simulator-attempt counter.

All **eight tests passed**, using **four actual full simulations**. Other failure
and budget tests used mocks. Log:
`../codex_tests/artifacts/mcp/milestone4_tests.txt`.
The limit is per process: restarting the server resets it. No persistent global
counter, database, extra analysis tools or orchestration framework was added.

## Token diagnostics

All runs used **gemini-3.8-flash-low**, the same model as the earlier experiment.
Each CLI invocation created a fresh user turn; none continued an old conversation.
The same persistent circuit context and tool registration were in scope.

| Diagnostic | Activity | Full ngspice calls | Input tokens | Output tokens | Total tokens | Wall seconds | CLI seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | Minimal READY request, no tools | 0 | 8,214 | 1 | 8,215 | 12.549 | 8.925 |
| B | One predefined design, no optimization | 1 | 17,929 | 412 | 18,341 | 17.245 | 13.780 |
| C | Autonomous baseline plus four modifications | 5 | 63,565 | 1,785 | 65,350 | 39.021 | 35.928 |

Credit consumption and monetary cost were **not supplied**. Exact backend LLM
call counts were also unavailable in the captured final JSON. The CLI's
num_turns=1 in each run means one user turn, not one backend model invocation.
All three usage envelopes report thinking_tokens=0 and cache_read_tokens=0;
these are reported counters, not proof about hidden internal reasoning.

Interpretation: A demonstrates a substantial input-context cost before simulation
or optimization. B adds 9,715 input tokens and C adds 45,636 more than B as tool
interactions and accumulated candidate history increase. This is consistent with
baseline CLI context plus repeated input context across tool round trips. The
diagnostics differ in prompt length and output schema too, so the differences
cannot be attributed solely to one tool call or to model reasoning. No per-call
token breakdown was supplied. The earlier 37,217-input-token two-call result is
therefore plausible, but its exact composition is not established. No model
comparison, monetary estimate or token-optimization system was implemented.

Recorded runs:
- A: `runs/baseline_2bcxiijz/`
- B: `runs/tool_oyy26p24/`
- C: `runs/autonomous_i7ydy4qp/`

Each has prompt.txt, cli_result.json and summary.json. Final user-facing responses
and concise engineering assessments are retained; streaming thought deltas and
private chain-of-thought are not requested or saved by this recorder.

## Autonomous decision history

The prompt supplied only the original physical parameters, budget, objectives
and stopping rules. It did not specify a parameter to change or a desired value.
Each following hypothesis is from the model's tool request, before execution.
Changes are relative to the immediately preceding design.

| Design | Model-chosen change | Pre-call prediction | Observed assessment |
| --- | --- | --- | --- |
| 1 | Original TA Design 4 sizing | Characterize baseline constraints | Gain and slew rate fail. |
| 2 | cap: 3.5 -> 1.0 pF | Increase slew rate and UGBW, retain PHM >60 degrees | Main trends supported. PHM is 65.02 degrees, so headroom is modest. Gain and slew rate still fail. |
| 3 | wn4: 1.5 -> 2.25 um | Increase tail current, raise gain toward 200 and slew rate above 15 | **Partly supported:** current and gain increase, but slew rate is only 12.55. The model's raw final label says supported; its explicit >15 prediction was not met. |
| 4 | cap: 1.0 -> 0.7 pF | Raise slew rate above 15 while preserving PHM >60 | Unsupported: slew rate falls and PHM drops below 60. |
| 5 | cap: 0.7 -> 1.0 pF; wn4: 2.25 -> 2.5 um; wn5: 0.5 -> 1.0 um | Relieve output slewing while recovering phase margin | Slew goal unsupported; gain collapses while PHM recovers. Because three parameters changed together, their individual causal effects are not isolated. |

| Design | Gain V/V | Slew V/us | PHM degrees | UGBW MHz | Actual reward | Violated hard constraints |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 188.355 | 5.95866 | 103.458 | 14.7006 | -0.442445 | gain, slewRate |
| 2 | 188.355 | 12.3595 | 65.0153 | 24.6732 | -0.0915198 | gain, slewRate |
| 3 | 271.464 | 12.5500 | 68.7549 | 41.0516 | **-0.0610232** | slewRate |
| 4 | 271.464 | 12.1351 | 58.1879 | 44.8644 | -0.0904293 | phm, slewRate |
| 5 | 86.4435 | 11.9088 | 80.8104 | 43.6185 | -0.485806 | gain, slewRate |

All five simulations succeeded numerically and returned seven finite metrics;
none met all five hard constraints. The counter progressed exactly 1,2,3,4,5 in
one evaluated MCP session, ending with remaining=0. Each design produced four
nonempty simulator output files. Tool runtime totaled 0.7051 seconds for C,
including netlist generation and measurement processing.

The model and Python agree that design 3 has the greatest actual course FoM.
Python selects max(reward) from valid logged evaluations, independently of the
model's prose. Its ID is **TwoStage_1793887100_kfdqhxzicg**. Relative to the initial
design, its only changes are cap=1.0e-12 F and wn4=2.25e-6 m. All 20 parameters,
seven specs, original hypothesis and assessment are saved in
`runs/autonomous_i7ydy4qp/best_design.json`.

| Best-design spec | Measured value |
| --- | ---: |
| area | 8.370672619e-10 m^2 |
| current | 1.483731e-4 A |
| gain | 271.46386 V/V |
| noise | 0.0048699687 V RMS |
| phm | 68.7548533 degrees |
| slewRate | 12.5500237 V/us |
| ugbw | 41051573.6 Hz |

The full chronological record is `runs/autonomous_i7ydy4qp/history.json`. It keeps
each ID, complete physical parameters, pre-call hypothesis, actual specs/reward,
feasibility, runtime, parameter/spec changes and the model's final assessment.
The original call journal remains in its simulations/session_* folder. The table
above flags the partial-hypothesis issue without overwriting the model's raw record.

## Execution flow and remaining limits

The launcher loads the initial design and experiment instructions, starts one
Antigravity process with its budget/output-directory environment, and supplies
the unchanged model choice. Antigravity calls the one MCP tool. The tool validates
inputs, checks the existing counter, launches the existing full ngspice evaluation,
rejects invalid numbers and returns compact measured results. The agent assesses
the result and chooses another design within budget. After exit, Python joins the
audit records with final assessments and selects the highest actual reward.

This task used **10 real full simulations total**: four regression-test calls,
one diagnostic-B call and five autonomous calls. Diagnostic A used zero. No
additional optimization attempt was made after the fifth design failed.

Tool execution, finite numerical measurements, hard-constraint feasibility and
TA-reference agreement remain distinct. The zero-UGBW/PHM convention and NaN/inf
failure behavior are preserved. The known slew-rate extraction discrepancy and
the YAML/TA slew-rate and UGBW target differences are not resolved by this work;
see `../codex_tests/REFERENCES_REPORT.md`. These runs use the existing YAML's
15 V/us and 1 MHz targets, not the TA CSV's implied 30 V/us and 100 MHz values.
The earlier action-grid reference mismatch also remains; the physical-parameter
MCP interface bypasses action_refine and does not repair that separate RL issue.

Before relying on an optimization claim, resolve those reference differences and
review engineering predictions rather than trusting the model's support labels.
The five-call experiment demonstrates autonomous proposal, evaluation and honest
failure retention; it does not demonstrate finding a feasible or TA-certified opamp.
