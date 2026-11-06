# Hybrid LLM–TD3 integration validation

2026-11-05, current checkout at d467f61 plus preserved local work. No commit,
push, dependency installation or model call was made. The actual updated TD3
implementation was inspected and exercised, rather than inferred from old reports.

## Implementation

`train_td3.py` is an optional launcher around the existing runner. It forwards
the existing learning arguments without changing defaults or equations. Its small
`HybridReplay` object holds one archive path, one ID set and two insertion points:

- After the first measured warmup reset, import at most `--llm-warmup` designs.
  Random actions fill the remaining warmup slots; there are no gradient updates.
- Once, before the next action after `--llm-after` policy steps, import at most
  `--llm-count` additional designs. A terminal episode resets first. The archive
  is read again at this checkpoint; new completed records can be appended beforehand.

Both paths call the unchanged `inject_llm_candidates`. It checks setup, units,
completion, physical grids, reward and feasibility; constructs float32 actions in
`dict_params` order; checks `action_refine` reconstruction; and calls the existing
ReplayBuffer.push. Candidate IDs are shared across both imports. Invalid entries
are reported; shortages leave random warmup slots. No simulation is run at import.
The live state, episode, network weights and optimizer state stay unchanged.

The four existing MCP tools and native agent files were not modified. No scheduler,
additional buffer, background poller, model launcher, accounting framework or
prediction system was added. Basic counts/results go in one training summary next
to the existing TD3 candidate JSONL. Original LLM runtime/tokens remain unknown
when absent; use source run summaries rather than treating that cost as zero.

## Current standalone TD3 status

Functional for this small local smoke with explicit numeric flags. Action selection
returns finite bounded noisy actions; the runner supplies the correct
`memory_batch` API and sample order `(state, action, next_state, reward, not_done)`.
Warmup pushes random experiences without updates. Actual PyTorch tests show critic
updates, delayed actor updates and target-network changes. Real ngspice runs
completed resets, steps, episode time limits and candidate exports successfully.

Pre-existing limitations were preserved:

- Five runner defaults remain `???`; supply noise_sigma, batch_size, w, pi_lr, q_lr.
- Standalone warmup and policy training finish episodes and can exceed w/T.
  Assisted warmup deliberately fills exactly w combined imported/random slots.
- NumPy/PyTorch are seeded, but Gym's action-space RNG is not seeded by the runner.
  The smoke explicitly seeds it in test setup. Future matched-seed studies need
  the TD3 owner's action-space seeding decision; `--seed` alone is insufficient.
- The cleanup call at multiples of 100 is Unix-specific; the smoke never reaches it.
- Time-limit done masks keep the existing convention. No terminated/truncated
  redesign was attempted. Final exploratory samples are not noise-free actor tests.

These limitations do not prevent the demonstrated insertion/update workflow.

## Exact validation

All commands used the existing `.venv/Scripts/python.exe -B` from the repository
root with MPLBACKEND=Agg and MPLCONFIGDIR under codex_tests/artifacts/hybrid.

1. Direct CPU API check: two `train_policy` calls with real TD3/ReplayBuffer;
   actor weights changed and selected action was finite. No simulator/model call.
2. `-m unittest codex_tests.test_hybrid_training codex_tests.test_replay_injection`
   initially exposed a test-only deepcopy of dict_keys; the new test now snapshots
   only relevant state fields. No production validation or tolerance was weakened.
3. `-m unittest codex_tests.test_hybrid_training codex_tests.test_replay_injection codex_tests.test_mcp_server codex_tests.test_reusable_tools codex_tests.test_multi_agent -v`:
   **32 passed, 2 failed, 1 skipped**. The two unchanged legacy regression tests
   are stale after the earlier upstream target update: their YAML mutation replaces
   absent `15.0`, and their historical reward is assigned the current setup ID.
   Current validation correctly rejects that inconsistent reward. Historical
   fixtures/tests were not edited or relabelled. See
   [offline_tests.txt](../codex_tests/artifacts/hybrid/offline_tests.txt).
4. Final focused suite: `-m unittest codex_tests.test_hybrid_training codex_tests.test_replay_injection codex_tests.test_mcp_server codex_tests.test_multi_agent -v`:
   **23 passed, 1 skipped** (the opt-in real smoke). See
   [focused_tests.txt](../codex_tests/artifacts/hybrid/focused_tests.txt).
5. With CAD_HYBRID_REAL=1:
   `-m unittest codex_tests.test_hybrid_training.TestRealHybrid -v`: **1 passed**.
   See [smoke.json](../codex_tests/artifacts/hybrid/real_4u71my18/smoke.json).
6. Changed Python files parse successfully; `git diff --check` passes. SHA256
   comparison against the pre-task snapshot confirms unchanged TD3 agent/buffer,
   CircuitEnv, DUT/wrapper, TwoStage YAML and input netlist.

The focused tests identify wrong update/sample APIs, missing/delayed learning,
learning during warmup, excess random warmup, wrong checkpoint timing, duplicate
imports, changed live state/weights/optimizers, wrong action mapping/time-limit
mask, invalid/current-state data, incompatible records and unexpected simulation
calls. Native role and zero-budget stdio checks retain the same four MCP tools.

## Real smoke and exact cost

Two fixed designs (initial sizes except res=6100/6200 ohm) were submitted through
the existing MCP function by the SDK test driver. They were actually measured by
ngspice and stored as completed records in a fresh current-setup archive. Their
`source=LLM` represents the MCP producer path; **no model proposed these designs**.
This is a data-integration smoke, not evidence about LLM design quality.

Both runs used the unmodified ten-step episode horizon, seed 123456, noise .03,
batch 2, w=2, T=12, actor lr .0005, critic lr .001 and replay capacity 32.
These small explicit test settings do not change production defaults.

| Measure | Standalone | Hybrid |
|---|---:|---:|
| Random warmup steps | 10 | 1 |
| Imported warmup / later experiences | 0 / 0 | 1 / 1 |
| Policy steps / critic updates | 10 / 10 | 10 / 10 |
| Delayed actor updates | 5 | 5 |
| Measured resets | 2 | 2 |
| Actual TD3 ngspice evaluations | 22 | 13 |
| Replay entries after run | 20 | 13 |
| Best exploratory policy reward | -2.128890 | -2.290469 |
| Final exploratory policy reward | -2.495714 | -2.733528 |
| Best/final policy sample feasible | No / No | No / No |
| Training-launch runtime seconds | 15.5213 | 3.9654 |

Total actual evaluations: **37 = 2 source MCP + 22 standalone + 13 hybrid**.
Replay insertion: **0 extra evaluations**. Model calls: **0**. No other actual
ngspice calls were made for this task. Unit/MCP-discovery tests use mocks/budget zero.
All real observations and rewards were finite; TD3 exports were available.

Warmup overshoot, different dataset sizes, first-run/plot overhead and this single
short trial prohibit a performance or speedup claim. The smoke demonstrates that
training continues on the same memory after both imports. It does not establish
statistical superiority, a feasible optimized solution or final actor-only quality.

## Changes outside llm/

This task modified **one existing source file outside llm/** and created one test
file. Integration logic remains inside llm/. Runner hooks are necessary to access
the actual measured state and existing buffer at the correct points; avoiding
them would require duplicating the training loops or runtime monkey-patching.

| File | Function/lines changed in final file | Why necessary | Effect on standalone TD3 |
|---|---|---|---|
| td3_runner.py | readParser, lines 19 and 67 | Accept argv forwarded by the optional launcher | No-argument parsing remains the same |
| td3_runner.py | train, lines 70–73, 77–78, 89 | Pass optional hook, run checkpoint, return basic counts | Default None skips checkpoint; action/update order unchanged |
| td3_runner.py | warmup_exploration, lines 93, 98–100 | Import after measured reset and fill remaining warmup slots | Default None retains whole-episode warmup |
| td3_runner.py | main, lines 116, 136–137 | Forward hook and return objects/counts for summary | Same initialization/learning; callers may ignore return |
| codex_tests/test_hybrid_training.py | New file, arguments/TestHybridTraining/TestRealHybrid | Focused and opt-in real validation | No production effect |

Generated test logs, pre-task diff/hash snapshots, figures, netlists and CSV outputs
are under codex_tests/artifacts/hybrid/ and codex_tests/artifacts/llm_simple/.
These are local runtime evidence, not project implementation changes. TD3 export
JSONL goes to ignored llm/runs/. Nothing in codex_tests was committed or pushed.

Inside llm/: new `train_td3.py` and this report; updated README.md. The existing
replay function, adapter, MCP tools, agent roles and TD3 exchange code were reused.

## Pre-existing changes preserved

Before editing, Git showed modifications to llm/.gitignore, GEMINI.md, README.md,
experiment.md, mcp_server.py, run_experiment.py and td3_runner.py; deletions of
llm/VALIDATION_REPORT.md and agent_settings.json; and untracked codex_tests/,
llm/.agents/agents/, .agents/settings.json, .agents/skills/, candidates.py,
circuit_adapter.py, replay_injection.py and td3_candidates.py. These were preserved,
including the existing 11-line logging-only runner diff. Only README.md was further
updated among those existing LLM changes. The snapshot and task-only runner diff
can be reconstructed from codex_tests/artifacts/hybrid/before.diff and
td3_runner_before.py.txt. No teammate learning implementation was reverted.

## Eventual experiment and one-minute oral explanation

README.md gives A (random), B (assisted warmup) and C (same warmup plus one later
import) commands. Fix the circuit setup, hyperparameters, initialization, action
sampling seeds and budgets; use horizon-aligned warmup and repeated trials. Charge
source LLM runtime/tokens once and count TD3 resets/steps separately. For LLMs,
evaluate best feasible FoM versus elapsed time; for TD3, learning versus steps/
evaluations and separately measured final actor quality; for hybrid, whether the
additional experiences improve learning. Extensive comparisons remain future work.

An LLM design enters memory only after MCP has measured it and saved a compatible
completed record. Python converts physical sizes to normalized absolute actions
and checks that the environment reconstructs the same circuit. It pairs the action
with the current measured state, stored reward and normalized measured next state,
then calls the existing buffer.push. This is allowed because TD3 is off-policy and
the current simulator evaluates complete absolute designs independently of earlier
sizes. The critic samples these experiences through ordinary replay; the actor
learns through the critic's existing gradient. Hybrid TD3 changes the data entering
memory, not its equations or optimizers. Insertion needs no new simulation because
the circuit's reward and next specifications were already measured.
