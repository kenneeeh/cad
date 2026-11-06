# Specialized CAD agents

This is a native Antigravity workflow, using the same `../run_experiment.py`,
`../mcp_server.py`, initial design, simulator and Python reward as V1. No new
Python dependencies, numerical optimizer or simulator were added.
The later reusable-tool/TD3-import extension is documented in [../TOOLS.md](../TOOLS.md)
and [../TOOLS_REPORT.md](../TOOLS_REPORT.md). `multi_agent` preserves the original
initial-design experiment; `td3_refine` uses archived TD3 measurements with an
optional strategist. REPORT.md and recorded_run.json retain the earlier experiment.

## Run

From the repository root, using the existing signed-in account and registered MCP server:

```powershell
.\.venv\Scripts\python.exe -B llm\run_experiment.py agents_check
.\.venv\Scripts\python.exe -B llm\run_experiment.py multi_agent --budget 5
.\.venv\Scripts\python.exe -B llm\run_experiment.py single_agent --budget 5
```

Each command starts a fresh conversation and uses model credits. Do not run them
as routine unit tests. `agents_check` has a zero simulator budget; it uses a clearly
synthetic packet to test handoffs and tool access. `single_agent` is the existing
`autonomous` workflow under an explicit alias. It runs from `llm/`. Multi-agent
modes run from `llm/multi_agent/`, where the local GEMINI scope overrides only
the parent's prohibition on delegation. The V1 prompt files are unchanged.

## Native agents and skills

Files in `.agents/agents/` are Markdown with native YAML frontmatter, not Python
classes or another vendor's agent format. The installed CLI is 1.5.1. Explicit
coordinator tools are necessary; invalid tool names fail executor construction.
MCP tools come from `inheritMcp: true`, not a `call_mcp_tool` registry entry.

| Agent | Job | Simulation access |
|---|---|---|
| coordinator | Maintain current/best and budget; request advice, construct candidates, call MCP, report evidence | Yes |
| circuit-diagnostician | Rank measured violations versus small margins; identify plausible mechanisms and relevant devices | No |
| experiment-designer | Propose one exact grid-valid physical change with benefit and risks | No |
| optimization-strategist | Advise local refinement versus exploration, stagnation and preserving verified progress | No |

Specialists use `model: inherit`, `inheritMcp: false`, `tools: []` and command
execution off. Their runtime tool audit is part of the communication check.
Antigravity retains basic native messaging/resource tools; these do not authorize
circuit simulation, arbitrary shell execution or file writes. Invocation also
requests MCP/write disabled. The coordinator has native delegation, messaging,
waiting and structured finish tools. Session settings deny shell/edit/web actions.
This is capability configuration, not just a sentence asking agents to behave.

`invoke_subagent` creates a fresh specialist context. Messages wake existing idle
specialists. The coordinator waits for replies and sends only a role-specific
packet: measured specs/limits for diagnosis; diagnosis/current parameters/grid/
tested changes for design; rewards/history/budget for strategy. Native IDs connect
requests and replies. Missing advice must be reported rather than impersonated.

The two `.agents/skills/*/SKILL.md` files are reusable native skills:

- `opamp-physics`: topology/roles, approximate gm/ro and bias relationships,
  compensation, phase margin, slew and noise/current/area trade-offs.
- `sizing-experiments`: units, physical grids, targets, controlled hypotheses,
  compact history and budget-aware search.

The CLI discovers `.agents/` in its workspace and parents. Local discovery
manifests explicitly name the agent/skill directories. Agent frontmatter selects
the relevant skills. Skill descriptions support discovery; their bodies supply
instructions. General principles and approximations are labelled separately from
ngspice evidence. No skill prescribes one fixed candidate or invents DC operating points.

Format references: [native agents](https://antigravity.google/docs/subagents?tab=cli),
[customization discovery](https://antigravity.google/docs/customization-discovery),
[skills](https://antigravity.google/docs/skills),
[headless output](https://antigravity.google/docs/cli/headless/).
Locally available course material was Sessions 1&2 and the project/introduction
PDFs; Sessions 3&4 were not found. Do not claim this implementation was checked
against unavailable slides.

## Complete execution flow for the oral exam

1. Python reads the same initial physical design, chooses the workspace and mode,
   creates one run directory, passes the budget to the MCP child and launches the
   same Flash Low model. It does not decide sizing changes.
2. The coordinator measures the unchanged starting circuit through MCP. The
   existing server validates all 20 names, finite values, bounds and grid steps.
   Its lock and CircuitEnv counter enforce the per-process budget. Failed simulator
   attempts consume calls; invalid inputs do not. The access check sets this limit to zero.
3. The coordinator consults the specialists. Diagnosis explains the bottleneck;
   design suggests one candidate; strategy advises how to spend remaining effort.
   These are three distinct advisory jobs, not three competing simulation loops.
4. The coordinator forms the full parameter dictionary. Before each candidate it
   supplies `hypothesis` and four short `decision` strings. Optional numeric
   `predictions` map metric names to `[lower, upper]` intervals. Units are SI,
   except phase margin in degrees and slew in V/us. For example a prediction of
   slew at least 15 in an expected range up to 25 is `{"slewRate": [15, 25]}`;
   this is a logging example, not a prescribed sizing change.
5. The unchanged simulator returns seven measurements. Python computes normalized
   specs, reward and feasibility with CircuitEnv. Each numeric prediction is
   checked against the actual measurement. A result of 12 V/us fails `[15,25]`
   even if an agent says it succeeded. Qualitative causes remain interpretations;
   no automatic test proves a physical mechanism from correlated outcomes.
6. The coordinator updates a small in-conversation memory: current and best,
   tested changes/observed trade-offs, remaining budget. It reuses idle specialists
   and consults strategy when progress fails. It stops within the limit and returns
   short evaluations and consultation summaries, not private chain-of-thought.
7. Python independently reconstructs the history from simulator audits, calculates
   exact parameter/spec differences, flags disagreement with numeric prediction
   checks and selects the largest actual reward. An agent's final ranking cannot
   override the saved `best_design.json`.

## Memory and evidence

Ignored `../runs/<mode>_*/` contains `prompt.txt`, final CLI response/usage,
`consultations.json`, filtered `tool_steps.json`, simulator `calls.jsonl`,
`history.json`, `best_design.json`, `memory.json` and `summary.json`.
During a run, memory is the coordinator's concise context; `memory.json` is the
deterministically reconstructed final snapshot, not an automatic resume service.
There is no database, vector store, transcript replay or Python orchestration loop.

Candidate logs retain complete parameters, pre-call diagnosis/proposal/prediction/
strategy, actual results and numeric checks. History adds differences and the
agent's explicitly attributed interpretation. Consultations retain short public
engineering advice and IDs. Filtered streaming metadata records actual native
handoffs, without copying thought deltas or transcript/tool output. Antigravity
may retain its own normal application logs outside this project's recorder.

The runtime cap is per MCP process. Restarting creates a fresh counter, so it is
prohibited; summary counts attempts across any sessions and flags over-budget runs.
Only the coordinator receives the simulator, preventing specialists opening their
own simulator paths through their normal toolset.

## Validation

```powershell
.\.venv\Scripts\python.exe -B codex_tests\test_multi_agent.py
```

These eight focused tests use no model and no actual ngspice calls. They check:

- Native role/skill configuration: catches accidental specialist MCP inheritance
  or missing referenced skills.
- Numeric prediction checking/audit persistence: catches optimistic success labels
  when actual slew misses a stated threshold, without changing reward.
- Invalid prediction/decision rejection: catches malformed pre-call evidence
  before any simulator attempt.
- Zero-budget enforcement: catches a discovery run launching a valid circuit.
- Stream filtering/failure handling: catches private text/transcript copying or
  accepting a truncated CLI stream as a completed result.
- Real stdio discovery/schema and zero-budget rejection: catches MCP integration
  mismatches that direct Python calls alone would miss.
- Logged text intervals with unit conversion: catches a missing structured
  prediction argument and flags incorrect supported labels from pre-call evidence.
- The saved experiment: checks parameter grids, finite normalized measurements,
  existing reward/feasibility calculations and best-design selection offline.

Existing mocked MCP regression checks also verify names/grids, failures, finite
fallbacks, compatibility and budget counting. Live native communication and the
single bounded experiment are recorded separately in REPORT.md; a passing static
configuration test alone does not prove working delegation or model availability.
