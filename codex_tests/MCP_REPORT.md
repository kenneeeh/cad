# Initial MCP implementation — 5 November 2026

## Changes

The framework now lives in `../llm/`; its test is `test_mcp_server.py` in
this folder. Simulator, environment and TD3 source files were not modified. Antigravity registration added one entry to its existing user MCP config.
Hash verification included CircuitEnv, DUT, the ngspice wrapper, YAML,
TD3 files, its runner, and the TA CSV. Git reports no tracked changes. No commits
or pushes were made; the earlier instruction to keep codex_tests local is preserved.

| File | Reason |
| --- | --- |
| `../llm/mcp_server.py` | One validated, synchronous physical-parameter simulation tool over stdio |
| `../llm/.agents/mcp_config.json` | Inspectable MCP config and SDK integration-test launch settings |
| `../llm/agent_settings.json` | Per-run execution permission for just the simulator MCP tool |
| `../llm/GEMINI.md` | One short sizing-agent instruction and reusable circuit context |
| `../llm/initial_design.json` | Exact TA Design 4 physical parameters for the first experiment |
| `test_mcp_server.py` | Five focused adapter/protocol tests, with no new measurement formulas |
| `../llm/.gitignore` | Keep runtime artifacts and caches out of source control |
| `../llm/README.md` | Commands, code explanations, SDK terminology, limits and pending setup |
| `MCP_REPORT.md` | Results and remaining validation |

Archived files under `artifacts/mcp/` include captured CLI help, schema, test
output, per-session netlists/CSV outputs and audit records. The CLI binary and
manifest have moved to ignored `../llm/.tools/`. Future normal runs write to
`../llm/runs/`; tests write to `artifacts/mcp/`. No new Python dependencies or API keys were added. CLI was absent;
its official release binary was downloaded locally and SHA512 verified. The
earlier slow, incomplete download was cancelled. The executable is now `../llm/.tools/agy.exe`.

## Request-to-result path

MCP client supplies `{"parameters": {...20 physical SI values...}}`. SDK schema
checks numeric argument types. The tool checks exact names, finite values, inclusive
YAML bounds and step alignment before any simulator attempt. Inputs are not clipped
or rounded. Existing CircuitEnv performs netlist generation, ngspice and measurement;
its normalization and reward methods are reused. The tool checks finite results
and hard constraints, then returns compact structured JSON. Waveforms, netlists
and full parameter audit records stay local.

The tool keeps zero-UGBW/PHM behavior. Invalid measurements or failed simulations
produce success=false and hard_satisfied=false; no synthetic measurements/reward
are returned. Valid but infeasible circuits produce success=true and feasibility=false.
Default budget is five simulator attempts per server process, configurable through
CAD_MAX_SIMULATIONS. The current CLI registration and project config select two
for the first experiment, as did the SDK workflow test. A lock
protects the existing DUT's mutable filenames from overlapping tool calls.

## Tests

| Focused test | Result |
| --- | --- |
| TA Design 4: tool vs existing direct interface, all seven specs and reward | Pass; two real simulations, rtol=1e-6 for specs |
| Range, off-grid, boolean, NaN, extra and missing input | Pass; no simulator call |
| Simulator nonzero exit | Pass; explicit failure, no invented specs/reward; mocked ngspice |
| NaN/infinite/None measurements; preserved zero-UGBW/PHM penalty | Pass; mocked measurements |
| Real stdio discovery, valid invocation, two-candidate workflow and exhausted budget | Pass; two real simulations |

**Five tests passed. Four real ngspice simulations total.** Test execution took
17.386 seconds, including client/server startup during the protocol test. Failed
simulator tests use mocks; their attempt counters do not represent additional real
ngspice executions. Log: `artifacts/mcp/test_output.txt`.

An additional check loaded the **exact prepared MCP config**, initialized its
server over stdio, found only simulate_design, verified SDK-level boolean rejection,
and verified an invalid physical value left the count at zero. It added no real
simulations. The catalog/schema is saved as `artifacts/mcp/tool_schema.json`.

The adapter matches the existing interface, not every TA reference measurement:
the previous slew-rate discrepancy and current YAML/TA target differences remain.
This implementation intentionally does not change those methods or settings.

## Recorded first workflow

This is an **MCP SDK client smoke test**, not an Antigravity model run. The candidate
was chosen explicitly for the test; it is not evidence of autonomous model behavior.

Baseline is TA Design 4. Main violations are gain and slew rate. Change only cap
from 3.5 pF to 2.5 pF. Hypothesis: less Miller capacitance improves slew rate while
retaining PHM >=60 degrees.

| Result | Baseline | Candidate |
| --- | ---: | ---: |
| Gain V/V | 188.35509 | 188.35509 |
| Slew rate V/us | 5.958659 | 7.889327 |
| PHM degrees | 103.45801 | 93.47579 |
| UGBW Hz | 14700608.52 | 16806653.99 |
| Reward | -0.442445 | -0.316254 |
| All hard constraints satisfied | False | False |
| Tool runtime seconds | 0.1354 | 0.1628 |

The hypothesis was supported in this test. Gain and slew rate still fail current
targets. Next decision: investigate those remaining violations before another
candidate; no more calls were made in this two-call session. The full seven-field
decision record, candidate parameters and measured specs are in
`artifacts/mcp/session_qsmmt3br/workflow_smoke.json`. Per-simulation runtime includes
netlist generation and measurement processing as well as the ngspice process.

## Completed Antigravity integration

Consulted course slide 4 plus Google's official installation, MCP, customization
and headless documentation. Actual CLI 1.5.1 help was inspected after download.
After user sign-in, CLI 1.5.1 still ignored the documented workspace config in
its MCP listing. Its actual add command has no project-scope flag. The supported
`agy mcp add` command registered cad-simulator in the existing user file
`~/.gemini/config/mcp_config.json`, preserving the prior contents in ignored
`artifacts/mcp/antigravity-mcp-before.jsonc`. No authentication data or default model
settings were edited. `mcp list` now shows it enabled. Both prepared and active
configs enforce two calls for this initial experiment.

**Live integration passed.** One Gemini 3.8 Flash Low agent turn discovered the
tool and made exactly two successful simulator calls. Shell execution, file
changes and web access were denied by session-only settings; only the simulator
MCP execution was allowed. The model override applied to this run only. No API
key or new paid service was added.

The live model chose cap=2.5 pF from the 3.5 pF baseline and observed the same
improvement as the protocol smoke test: slew rate 5.958659 -> 7.889327 V/us,
PHM 103.45801 -> 93.47579 degrees, reward -0.442445 -> -0.316254. Both designs
remain infeasible due to gain and slew rate. Actual simulation IDs were
TwoStage_1793884337_ccuxcdljuz and TwoStage_1793884343_jhnzrgkanh. The audit file
`artifacts/mcp/session_uwcy63my/calls.jsonl` verifies two successful calls, final
counter=2, remaining=0. No additional optimization run was started.

**Total actual ngspice calls for this implementation: six** (four focused-test
calls plus two live-agent calls). Live CLI duration: 37.44598 s; end-to-end wall
time: 40.357 s. Tool runtimes were 1.3722 s and 0.1790 s, summing to 1.5512 s,
including netlist generation and measurement processing.

The CLI usage envelope reported 37,217 input tokens, 1,020 output tokens,
38,237 total tokens, zero reported thinking tokens and zero cache-read tokens.
Credit consumption was not supplied and is recorded as unavailable. The model's
prose said usage was unavailable, but its outer CLI JSON supplies these actual
counts. The totals include CLI/model context and tool round trips; a finer
breakdown was not supplied. No token savings or monetary cost were invented.
The large input count is a measured baseline for future efficiency work, not
evidence that the whole agent context contains only the short prompt.

Saved records: artifacts/mcp/live_agent_result.json (CLI result),
artifacts/mcp/live_decision_record.md (the model's engineering record),
artifacts/mcp/live_summary.json (verified counts/usage/runtime), and
artifacts/mcp/live_run_meta.json (process duration and exit status).

One limitation in the model's next-step suggestion was caught: it described mn5
as a tail-bias control. In this netlist mn4 is the input-stage tail sink and mn5
is the second-stage sink. GEMINI.md now explicitly identifies these roles. The
suggestion was not executed, and no additional model calls were spent on it.
The capacitor hypothesis was supported; future sizing suggestions still need
review and the known measurement/TA differences remain.

README contains the working registration and headless-run commands. No custom
token framework, database, agent framework, TD3 integration or subagent was added.

Official references:
- https://antigravity.google/docs/getting-started/
- https://antigravity.google/docs/mcp
- https://antigravity.google/docs/customization-discovery/
- https://antigravity.google/docs/cli/headless/

The installed Python SDK's MCPServer API was inspected locally; no v1/v2 package
upgrade or downgrade was needed.

## Folder reorganization

Framework source/configuration/instructions are now in `llm/`. The executable is
`llm/.tools/agy.exe`, the active registration points to `llm/mcp_server.py`, and
`codex_tests/test_mcp_server.py` imports it from there. Archived raw results retain
the original paths as historical evidence; do not use those old command paths.
Use `llm/README.md` for current commands.

Relocation validation passed: the three mocked input/failure/measurement tests,
module imports, exact configured server launch, stdio tool discovery and invalid
input rejection. All test scratch output stayed in codex_tests/artifacts/mcp.
This reorganization used zero real ngspice simulations and zero model calls.
