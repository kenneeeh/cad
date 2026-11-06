# LLM experiences into TD3: implementation and validation

Implemented 2026-11-05. No paid LLM experiment or TD3 training was run. The existing
actor, critic, buffer implementation, environment, reward, targets, netlist and
measurement code were left unchanged. Their source checksums match the pre-task files.

## What an injected transition means

The input is a completed, compatible source=LLM candidate, not a proposed action.
The new function reuses the adapter to validate all physical values, fingerprint,
units, measured specs, reward and feasibility. It rejects known fixtures and
incomplete/inconsistent records. TD3 and initial-reference records are not injected.

Physical values become float32 normalized absolute actions in env.dict_params
order using `2*(p-low)/(high-low)-1`. The actual action_refine verifies the same
physical grid point after clipping/rounding. Binary floating-point differences
are allowed within the existing adapter's grid tolerance, not by changing parameters.
Next state is the candidate's measured specs normalized in environment order.

Preceding state is the actual current successfully measured reset/step observation,
checked against its physical design/specifications. Each imported candidate is a
counterfactual branch from that same state, not a fabricated sequence between
unrelated episodes. The current step uses complete absolute sizes and a fresh
ngspice process with fixed PVT/testbench, so next specs/reward do not depend on
previous sizing. This was verified in source and tested from two measured states.
This assumption is specific to the current environment, not all RL problems.

done is the current hypothetical next-step time-limit flag:
`episode_steps + 1 >= max_steps_per_episode`. A feasible design is not terminal.
The existing time-limit masking convention is preserved; no terminated/truncated
redesign was made. The function requires an active nonterminal episode after a
successful reset/step; callers must not invoke it after a failed evaluation.

Exactly one existing ReplayBuffer.push call inserts each validated transition.
There is no simulator call, active-observation replacement, episode advancement,
network reset, second buffer or sampling change. A run-local ID set prevents
repeated insertion. A small slot-provenance map records IDs/origins; ordinary
runner pushes clear overwritten slots, allowing current LLM replay fraction reporting.

## Warmup and training hooks

All options default to disabled/zero. Standard behavior is retained without an
archive. With --llm-warmup N, at most N experiences replace random warmup samples;
the remainder uses the original random loop. Missing/rejected candidates fall
back to random sampling. A measured reset is still required and charged.
Assisted warmup caps its combined count at w. Original disabled warmup still
finishes episodes and can overshoot w; use horizon-aligned w for first comparisons.

--llm-every K and --llm-per-check M enable explicit between-batch checkpoints,
using the same function, buffer and ID set after warmup. Newly appended completed
candidates are read synchronously; terminal checkpoints wait for the next reset.
No thread, shared-memory replay access, daemon, LLM replay tool or polling service
was added. No learning equations, initialization or hyperparameters changed.

## Accounting

Optional operation logs contain actual local counter deltas for resets, random
warmup, actor exploration and update calls, including raised simulator calls.
Imports are recorded separately with zero new simulation attempts. Future MCP
audit/archive metadata contains stable process-session IDs; audits also have UTC
completion timestamps. Historical logs were not rewritten.

The reconciler accepts explicit completed TD3 logs, full MCP call audits and CLI
usage summaries. It sums TD3 operation deltas and each MCP session's maximum once,
deduplicating copied event/session records. It does not merge process-local counters
into a live global counter. Source simulation IDs missing from supplied audits
are reported. Include original LLM baseline, failed and unused attempts, not only
successful candidates imported into replay. Importing an experience charges no
additional simulation. Missing token summaries remain unknown, not free.
Update-call counts are not independently verified actor/critic optimizer-step counts.

## Tests and exact real cost

**46 test cases passed:** 16 new mocked/offline replay tests, 23 existing
archive/runner/multi-agent tests, 6 existing mocked MCP tests, and one small real test.

The new unit checks cover inverse mapping and float32/grid reconstruction, tuple
values and specification ordering, current/terminal episode flags, actual buffer
API/sampling order, unchanged active state, same result from different preceding
states, duplicates/limits, rejected incompatible/incomplete/unverified/fixture
data, warmup mixture, new checkpoint data, shared warmup/training IDs, terminal
checkpoint deferral, disabled behavior, provenance overwrite, and accounting for
failures/imports/copied logs. Their circuits and learning updates are mocked.
An initial generated endpoint fixture exceeded the strict cap maximum by floating
point noise; the fixture now uses the exact configured endpoint. No tolerance or
production validation was weakened.

The real test used actual CircuitEnv, MCP and ReplayBuffer:

- **1** full ngspice evaluation to obtain a measured reset anchor.
- **1** full evaluation for a fixed SDK candidate (res=6100 ohm).
- **1** replay insertion, with **0** additional simulations.
- **0** LLM/model calls, **0** gradient updates and **0** training runs.

The active environment/counters/observation stayed unchanged during insertion.
Reconciliation reports two attempts (one reset plus one separate MCP session),
one imported experience and no missing source evaluation. The candidate reward
was -0.395247123196666 and it remained infeasible. This tests data integration,
not optimization improvement. The proposal was supplied by the SDK test driver,
not generated by an LLM; source=LLM denotes the MCP producer path in this isolated test.

Real evidence: `artifacts/replay/real_qnh5jx51/replay_smoke.json` and its associated
TD3-cost/MCP-audit files. The real test is opt-in with CAD_REPLAY_REAL=1; the default
unit class uses no ngspice. Earlier historical experiments were not rerun.

## Files changed for this task

- New `llm/replay_injection.py`: inverse action map, checked replay insertion,
  optional operation/event accounting and retrospective reconciliation. Independent
  of MCP and Antigravity; uses the existing adapter/archive/buffer API.
- `td3_runner.py`: optional warmup/training checkpoint flags and hooks, common
  run-local IDs, ordinary-slot provenance maintenance and optional accounting.
  The original select_action/train_policy/update call semantics remain.
- `llm/candidates.py`: optional unfiltered archive read so incompatible entries
  can be explicitly reported rather than disappearing from import counts.
- `llm/mcp_server.py`: session IDs in future metadata/audits and audit timestamps;
  no extra tool, simulator or reward change.
- `llm/run_experiment.py`: detailed decision records are counted when present,
  instead of treating their absence as a missing expected record.
- `llm/experiment.md`, `.agents/agents/coordinator.md` and
  `.agents/agents/experiment-designer.md`: short hypotheses are standard;
  detailed decisions and numerical intervals are optional and defensible.
- `llm/README.md`: current direction, API, assumptions, flags, accounting and
  the unexecuted A/B/C comparison plan.
- New `codex_tests/test_replay_injection.py`, this report and local test artifacts.

No commit/push, package installation, extra agent, replay prioritization, actor
loss, circuit probing or historical-data modification was performed.

## What the TD3 owner must finish

select_action still returns no action; update_parameters has no learning body.
The runner passes keyword memory, while the method expects memory_batch. The
owner must align that call and complete the methods and placeholder hyperparameters.
ReplayBuffer.sample actually returns `(state, action, next_state, reward, not_done)`;
the runner's variable labels are confusing, but its tuple currently retains that
order. These issues were documented and deliberately not independently rewritten.
The ordinary cleanup shell command/episode-horizon behavior are also pre-existing.

## Prepared comparison and remaining work

A: random warmup, no imports. B: N LLM warmup experiences, no later imports.
C: same warmup as B plus K-step checkpoints with up to M new candidates.
Keep the completed learner, problem fingerprint, network initialization/seed,
hyperparameters and uniform buffer capacity/sampling consistent. Reserve and charge
LLM preparation calls, resets and failures in a comparable total simulator budget;
T by itself is not that budget. Charge reused precomputed data consistently.

Measure best feasible reward, work until first feasible, best reward versus
cumulative timestamped evaluation work, final actor-only evaluation quality/cost,
current LLM replay fraction, updates, runtime and separate CLI tokens. Repeat matched
seeds; a small LLM dataset may have little influence under uniform sampling.
No A/B/C learning experiment was executed. It remains to complete standalone TD3,
produce compatible actual LLM campaigns, allocate matched budgets and perform
those controlled trials. There is no evidence of learning benefit yet.

Oral-exam explanation: the LLM supplies a measured absolute design. Python checks
it, converts its sizes into TD3's action and inserts a transition from the current
measured state to that design's normalized measurements. The live episode stays
unchanged. TD3 later samples that experience through its usual uniform buffer;
original LLM simulation cost is counted once and replay insertion costs zero.
