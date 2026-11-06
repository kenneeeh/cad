# TwoStage LLM sizing

This course project uses native Antigravity agents to choose sizing experiments.
Python handles validation, ngspice, reward and storage. It supports only the current
TwoStage.yaml/testbench. No custom agent scheduler or circuit-plugin system is used.

## Files

| File | Responsibility |
|---|---|
| mcp_server.py | Four MCP tools and one shared simulation budget |
| circuit_adapter.py | TwoStage units, grids, finite checks and calls to CircuitEnv reward |
| candidates.py | JSONL candidate records, ID lookup, changes and distinct ranking |
| run_experiment.py | Launch Antigravity, collect evaluations and write one summary |
| td3_candidates.py | Save/import completed TD3 evaluations without re-simulation |
| replay_injection.py | Explicit insertion of measured LLM designs into an existing buffer |
| train_td3.py | Optional warmup replacement and one later replay checkpoint |
| experiment.md / GEMINI.md | Short experiment prompt and shared restrictions |
| initial_design.json | Starting physical sizes |
| .agents/ | Native roles, two skills, tool permissions and MCP launch settings |

The Antigravity binary remains in the workspace `.tools/antigravity` directory,
outside this repository. Existing sign-in and MCP registration are unchanged.
Runtime data goes in ignored llm/runs/. Tests and historical evidence stay in
codex_tests/, which must not be pushed.

## Run from the repository root

```powershell
.\.venv\Scripts\python.exe -B llm\run_experiment.py --budget 5
```

The default multi_agent mode measures initial_design.json once, then refines by ID.
The coordinator selects experiments and owns the budget. It can consult the circuit
diagnostician or experiment designer when useful. The strategist is optional and
is not required every iteration. Specialists have no MCP inheritance, shell or
write tools. Native messaging handles their replies; Python does not schedule agents.

```powershell
.\.venv\Scripts\python.exe -B llm\td3_candidates.py PATH_TO_TD3_CANDIDATES.jsonl
.\.venv\Scripts\python.exe -B llm\run_experiment.py td3_refine --budget 2
```

Import uses no simulator/model. Refinement starts from an already measured TD3 ID,
not another baseline simulation. Pass --archive PATH to both commands for a chosen
shared archive; the default shared file is llm/runs/candidates.jsonl. Fixture-only
or missing TD3 data is rejected before a paid agent starts. The current TD3 learner
is implemented. Its five `???` runner defaults still require explicit numeric flags.

## Four tools

| Tool | Use |
|---|---|
| get_problem() | Read current grids, units, targets, reward convention and remaining budget |
| get_candidates(k=5) | Read compact, distinct designs ranked by actual reward |
| get_candidates(design_id=id, include_parameters=True) | Retrieve one full stored record |
| simulate_design(parameters, hypothesis='') | Measure a complete physical sizing vector |
| evaluate_candidate(base_design_id, changes, hypothesis='') | Copy a base and test absolute changed values |

Only the last two consume simulator attempts. They share the same lock and counter.
Invalid grids/bounds/non-finite values are rejected before simulation. Failed
simulator attempts count; restarting a server must not be used to renew the budget.
Changes are physical absolute values, not percentages or normalized RL actions.
Use one short engineering hypothesis; there are no decision/prediction arguments
or required output schemas. Measured results, rather than agent claims, determine
reward and feasibility. A positive reward alone does not establish feasibility.
Zero UGBW/PHM remains a finite penalized fallback.

## Records and results

A candidate JSONL line contains a stable ID, setup ID, source, run ID, all physical
parameters, measured specs/units, reward/feasibility/violations, parent ID, hypothesis
and completion/simulation metadata. Only completed measured data enters this archive.
Repeated physical vectors appear once in best-candidate lists; the full history
remains available by ID. Imports retain their IDs and original checked reward.
TD3 warmup/policy origin is kept as one phase field; it does not prove learning.

Successful measurements are stored once in candidates.jsonl. Session calls.jsonl
records actual attempt counts and failures, including failed parameters/hypotheses.
The runner saves only summary.json: best measured record, evaluated IDs, archive
path, actual observed attempts, wall-clock time, CLI status/error, final reply and
reported tokens. A CLI error always returns failure even if good candidates exist.
Timeouts or malformed CLI responses still preserve available measured results.
There are no handoff traces, consultation files, memory snapshots or text-interval parsers.

The setup ID is `TwoStage-rising-` plus a short hash of TwoStage.yaml. It detects
YAML changes, not source/model/ngspice/PVT/library changes. It intentionally differs
from the old broad fingerprints; historical records are not relabelled or migrated.
Do not compare or import results from different targets, testbenches or slew-rate
extraction without re-evaluation. In particular, old rise/fall averages are not
current rising-only measurements. Keep the current setup fixed during an experiment.

## Put measured LLM designs into TD3 memory

The existing replay function is reused by the optional launcher below. It can also
be called directly after a successful reset/step in an active episode:

```python
from llm.replay_injection import inject_llm_candidates

seen = set()  # Create once; reuse for the entire training run.
summary = inject_llm_candidates(archive_path, existing_buffer, env, seen, limit=3)
```

It validates completed LLM records, converts physical parameters to float32 absolute
actions and verifies them through action_refine. The transition is current measured
state, action, existing reward, normalized candidate specs, and the current next-step
time-limit flag. It calls the existing buffer.push, without re-simulation or changing
obs/episode counters. Because this environment evaluates complete absolute sizes
in a fresh simulation, the next specs/reward do not depend on previous sizes. All
candidates branch from the current measured state; they are not chained into an
invented episode. Feasibility does not terminate the episode; done matches the
existing time-limit convention. Failed/finished episodes require a successful reset.

The seen set prevents duplicate insertion; the returned IDs/rejections provide a
small record of what was added. There is no second buffer, new actor loss or replay
prioritization. Original LLM simulation costs still belong in any future TD3
comparison; inserting an existing evaluation costs no additional simulation.
Actor/critic/buffer code is unchanged. The runner has optional hooks at measured
warmup states and between policy actions, retaining its existing TD3 export hooks.

## Standard and hybrid TD3

Run from the repository root. These are future experiment commands, not a claim
that these settings are optimal. The numeric settings below come from the saved
run `output_figs/2026-11-05--18-35-18/params.json`; choose and hold them fixed before
comparing methods. No command starts an LLM or re-simulates an imported design.

```powershell
$common = @('--seed', '123456', '--noise_sigma', '0.03', '--batch_size', '64',
            '--w', '100', '--T', '2000', '--pi_lr', '0.0005', '--q_lr', '0.001')

# A: unchanged standalone TD3 (random warmup).
.\.venv\Scripts\python.exe -B llm\train_td3.py @common --run_id standard_A

# B: up to three already measured LLM designs replace random warmup slots.
.\.venv\Scripts\python.exe -B llm\train_td3.py @common --run_id assisted_B --llm-archive llm\runs\candidates.jsonl --llm-warmup 3

# C: same warmup, plus up to three distinct designs after 200 policy steps.
.\.venv\Scripts\python.exe -B llm\train_td3.py @common --run_id hybrid_C --llm-archive llm\runs\candidates.jsonl --llm-warmup 3 --llm-after 200 --llm-count 3
```

Use a different run ID each time. The original `td3_runner.py` command also still
works with the five numeric flags. All learning options are forwarded unchanged.
With no injection enabled the launcher passes no hybrid object to the runner.

Warmup starts with a measured reset, imports at most `--llm-warmup` candidates
(never more than `--w`), then uses random actions for the remaining slots. Rejected
or missing compatible candidates leave more random slots. Warmup performs no
learning. Assisted warmup stops at exactly `w` combined slots; the unchanged
standalone runner finishes its whole episode and may exceed `w`. Use a multiple
of the ten-step episode horizon for planned A/B/C warmup counts.

`--llm-after N` means one import before the next policy action after N actual
policy steps, excluding warmup/imports/resets. The same archive is read afresh
once, so appended candidates can be used. A terminal step is followed by reset
before import; an unreached checkpoint is recorded as such. The same ID set is
used throughout. No polling, agent launch, optimizer reset or extra buffer is used.
`T` keeps the runner's existing meaning: combined warmup slots plus policy steps;
policy episodes still finish and may exceed it. Imports at the later checkpoint
do not advance that counter or the active episode.

`llm/runs/td3_<run_id>/training_summary.json` records random warmup/policy counts,
reset and step evaluations, imports/rejections/IDs, update count, elapsed time,
rewards in TD3 step order and best/final exported policy samples. Candidate JSONL
retains physical sizes/specs and simulation IDs. Reset evaluations are charged
separately. Export errors remain visible; unavailable best/final exports are null.
Policy samples include exploration noise; deterministic final actor quality needs
a separately counted evaluation, not a claim based on those samples.

For LLM optimization, use best feasible FoM versus elapsed time, feasibility and
reported CLI tokens; evaluation count is descriptive. For TD3, use progress versus
actual TD3 steps/evaluations and best/final actor quality. For hybrid, compare A/B/C
under matched initialization, hyperparameters and repeated seeds, including the
original LLM preparation cost. That cost is not a new ngspice call at insertion.
The training summary leaves original LLM runtime/tokens null: consult the original
LLM run summaries using each candidate's run ID; missing costs are unknown.

Two existing runner limitations matter for future comparisons: it seeds NumPy and
PyTorch but does not seed Gym's separate action-space RNG, and its `clean.sh` call
at multiples of 100 is Unix-specific. The short validation seeds the action space
explicitly in its test setup and never reaches that cleanup. These behaviors are
preserved for the TD3 owner; matching `--seed` alone does not guarantee matching
random warmup. Time-limit `done` masks also retain the existing learner convention.

## Tests and report

```powershell
.\.venv\Scripts\python.exe -B -m unittest codex_tests.test_hybrid_training codex_tests.test_replay_injection codex_tests.test_mcp_server codex_tests.test_multi_agent

# Opt-in real simulator integration smoke, no model call:
$env:CAD_HYBRID_REAL = '1'
.\.venv\Scripts\python.exe -B -m unittest codex_tests.test_hybrid_training.TestRealHybrid -v
Remove-Item Env:CAD_HYBRID_REAL
```

The default tests use mocked simulations, the actual TD3 networks/buffer and a
zero-budget MCP protocol check. The opt-in smoke uses ngspice and small actual
learning updates. Neither calls a model. See [HYBRID_REPORT.md](HYBRID_REPORT.md)
for measured results, exact file changes and limitations. Older reports describe
the implementation at their own dates, not the current learner or launch commands.

## Oral-exam explanation

MCP gives the LLM a small set of Python functions to call. The coordinator can ask
specialists for physical advice, then sends a base ID and size changes to Python.
Python validates the sizes, runs the existing ngspice interface and calls CircuitEnv
to normalize specs and calculate reward/feasibility. JSONL records retain measured
designs and hypotheses; the runner selects the highest actual reward. A separate
small Python function can insert those measured designs into TD3's existing buffer.
For another circuit, parameter definitions, measurements, targets, adapter and
physics skill would change; the coordinator/MCP workflow could remain similar.
TD3 is off-policy, so its critic can train on measured actions from another policy.
The physical sizes are converted back to absolute actions and checked through the
environment's own mapping. The critic learns their measured rewards and next
states through ordinary uniform replay; the actor then learns through the critic's
existing gradient update. Hybrid TD3 changes which experiences enter memory, not
the TD3 equations. Insertion reuses a completed evaluation, so no new simulation
is needed. This branch-from-current-state construction relies on the current
static, absolute-sizing environment, not a general stateful circuit process.
