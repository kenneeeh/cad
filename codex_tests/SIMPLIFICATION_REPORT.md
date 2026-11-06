# LLM simplification report

The implementation now targets the current TwoStage course testbench only.
No LLM calls, ngspice evaluations or TD3 training were run for this cleanup.

## Size and responsibilities

Python line counts include comments and blank lines:

| File | Before | After |
|---|---:|---:|
| llm/run_experiment.py | 237 | 81 |
| llm/mcp_server.py | 179 | 121 |
| llm/circuit_adapter.py | 98 | 76 |
| llm/candidates.py | 74 | 69 |
| llm/td3_candidates.py | 120 | 100 |
| llm/replay_injection.py | 209 | 81 |
| **Active LLM Python total** | **917** | **528** |

That is about 42% less Python, with the runner about two-thirds shorter.
The adapter remains because MCP, TD3 export/import and replay insertion share its
actual bounds/grid, finite-number and reward checks. Keeping those checks together
is easier to follow than duplicating them in several files.

## Preserved

- Four tools, native coordinator/diagnostician/designer and optional strategist.
- Grid/bounds validation, finite measurements and normalization, existing reward
  and physical feasibility checks, shared per-process simulator budget and errors.
- Immutable base designs, full measured candidate records, parent IDs, hypotheses,
  stable IDs, distinct reward ranking and persistent JSONL history.
- TD3 completed-evaluation export/import, with no re-simulation or learning changes.
- Small explicit LLM-to-TD3 memory insertion, following the user's final clarification.

## Removed or simplified

- Source/model/executable hashing, package-version tracking and general compatibility
  fingerprints became a short TwoStage YAML hash and rising-edge setup label.
- Prediction/decision tool arguments, text-interval parsing, agent self-assessment
  comparisons, streaming tool-event parsing and structured final-response schemas
  were removed. One short hypothesis and actual measurements remain.
- The runner no longer produces handoff, consultation, verbose history, memory,
  separate CLI-result or best-design files. It saves summary.json; candidate JSONL
  and a small attempt/failure log hold the evaluation history.
- Candidate creation dates, duplicate original reward copies and import-file/line
  provenance were removed. TD3 exports now use the same candidate record format.
- Automatic replay checkpoints/CLI options, slot-provenance maps and the replay
  accounting framework were removed. The user requested keeping a simpler manual
  insertion function, so that function remains rather than restoring the machinery.

Old experiment records were not rewritten. Obsolete replay tests/report were
archived in llm_history; a smaller current replay test replaces them. No active
source file needed to disappear simply to reduce the number of files.

## Files changed

- The six Python files in the table: simpler storage/tools/runner/data exchange,
  plus the replacement two-function replay module.
- td3_runner.py: removed only the old replay/checkpoint/accounting additions;
  retained logging-only evaluated-candidate exports.
- llm/experiment.md, four native agent instruction files and two skills: shorter
  responsibilities, optional consultations, one hypothesis and no final schema.
- llm/README.md: concise current usage, records, limitations and oral-exam flow.
- codex_tests/test_mcp_server.py, test_reusable_tools.py, test_multi_agent.py,
  test_replay_injection.py and the TD3 JSONL fixture: updated to current interfaces.
- This report and the historical-evidence index.

Actor/critic, ReplayBuffer, CircuitEnv and measurement source checksums are unchanged.
An AST comparison confirms TD3 control flow matches Git HEAD after excluding the
logging-only export helper/calls. No learning equation or hyperparameter changed.

## Execution and errors

The runner selects an initial physical vector or an evaluated TD3 ID and launches
Antigravity with a short prompt. The coordinator optionally asks specialists for
advice, then calls MCP. Python validates sizes, simulates and computes the existing
reward/feasibility. Measured candidates append to JSONL. Python selects the highest
actual reward and writes it with status, attempt count, time and tokens in summary.json.
CLI errors, nonzero exits, malformed JSON and timeouts return failure while retaining
available measured results. The agent's final prose cannot override the measured best.

## Small memory-insertion API

inject_llm_candidates reads completed source=LLM records, checks measurements and
setup, converts physical sizes to float32 absolute actions and verifies reconstruction
through action_refine. It inserts current measured state, action, reward, normalized
candidate specs and current time-limit done into the existing buffer. The active
episode is unchanged, and a caller-owned set prevents repeated design IDs.
This relies on the current absolute-action, fixed-setup environment; it does not
invent trajectories from arbitrary states. Six focused tests check this API.

No automatic warmup/training insertion is installed. The TD3 owner must finish
the existing unfinished action-selection/update methods and select explicit call
points for the small function. No second replay buffer or simulator call is needed
for insertion. Original LLM evaluations still count in future experiment budgets.

## Validation and limitations

**27 focused tests pass**, including mocked tool evaluations, invalid grids,
failed-attempt budget enforcement, ID modification, ranking/persistence, TD3
export/import, measured-best selection, CLI errors/timeouts/nonzero exits, restricted
native permissions and replay correctness/duplicates. A zero-budget MCP test checks
the actual protocol/schema without simulating. No new real or paid experiment ran.

The setup identifier detects YAML changes only. It does not detect altered source,
PVT, models, package versions or ngspice binaries. These are deliberately fixed
course assumptions, not automatic compatibility guarantees. Old setup IDs are not
relabelled, and old rise/fall-averaged slew results are not treated as current
rising-only measurements. Re-evaluate when the simulation setup changes.

For another circuit, parameter definitions, measurements/targets, its adapter and
physics skill would change. The coordinator/MCP pattern could remain similar;
there is no implemented cross-circuit plugin layer. No commit or push was made.

Oral-exam explanation: MCP lets the agents call a few Python functions. The
coordinator uses specialist advice to choose physical size changes. Python checks
them, runs ngspice and calls CircuitEnv for reward/feasibility. JSONL stores actual
evaluations and hypotheses. A separate short function can put those measured
designs into TD3's existing memory without another simulation.
