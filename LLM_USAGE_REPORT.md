# LLM harness: usage analysis

Measured on macOS with `agy` 1.5.1. Each claim is tagged **measured**, **inferred** or **not tested**.

## TL;DR

1. LLM cost is driven by the **number of model turns**, not by the number of simulations. Every turn re-sends the whole context.
2. The old workflow used tiny budgets (20-100 simulations) and tiny TD3 batches (5-20 steps): many expensive turns, almost no learning. ngspice takes about 0.05-0.1 s per simulation, so such budgets are unnecessarily small.
3. A prompt-only change (few large TD3 batches, no specialist, no initial reads, at most 3 LLM interventions) cut input tokens roughly in half and turned an infeasible result into a feasible one.
4. With the current setup the LLM adds **little** on top of TD3. Where it helped (one Sonnet run) it polished a design that already met all hard constraints.
5. Runs do **not** depend on each other. `cache_read_tokens` is the provider's prefix cache, not agent memory.
6. Open question for the owner: the YAML targets for `ugbw` and `slewRate` seem to differ from the TA reference.

## What the repo does

Size a TwoStage op-amp (20 discrete parameters) so 5 hard constraints hold (gain >= 200, noise <= 0.03, phase margin >= 60 deg, slew rate >= 30 V/us, UGBW >= 100 MHz) while minimizing area and current.

```
ngspice_interface/  simulator wrapper
circuit_env.py      Gymnasium env: action in [-1,1]^20 -> grid parameters -> specs -> reward
td3/, td3_runner.py TD3 agent
llm/                MCP server (7 tools) + one headless `agy` call with a coordinator agent
```

`llm/run_experiment.py` launches one `agy -p` call. The coordinator talks to `llm/mcp_server.py`, which keeps one persistent TD3 learner, one replay buffer and a JSONL archive. The simulation budget is shared: LLM evaluations, TD3 steps and TD3 episode resets all count.

## 1. Why usage was high, and what the new prompt changes

Hybrid mode, model `gemini-3.8-flash-low`, default TD3 config.

| Run | Budget | Input tokens | Tool calls | Best reward | Feasible |
|---|---|---|---|---|---|
| Original prompt | 20 | 167,506 | 10 | -0.755 | no |
| Original prompt | 100 | 131,955 (+152,645 cached) | 14 | -0.642 | no |
| **Lean prompt** | 1000 | **59,378** | **6** | **+0.610** | **yes** |

Call sequences:
- Original, budget 100: `eval x5, warmup20, train20, train20, eval x4, train20, eval` (TD3 trained only 60 steps).
- Lean, budget 1000: `warmup200, train200 x3, train100, eval`.

Comments:
- Tokens do not scale with simulations: 100 simulations used fewer tokens than 20. They scale with turns.
- A 200-step TD3 call costs the same tokens as a 5-step call but trains 40x more.
- Fixed context per call is about 5-6k tokens (**inferred**; the CLI does not expose it).
- The lean prompt is still a soft control: token use varied between 59k and 109k across seeds, because the model decides how many interventions to make.

## 2. Why the LLM adds little right now

Lean prompt, budget 1000, hybrid vs TD3 alone (same seed, same protocol: warmup 200 then batches 200, 200, 200, 100):

| Seed | LLM evaluations | Best design from | Input tokens | Hybrid reward | TD3 only |
|---|---|---|---|---|---|
| 1 | 6 | TD3 | 108,712 | 0.551 | 0.431 |
| 2 | 1 | LLM | 59,425 | 0.619 | 0.609 |
| 3 | 0 | TD3 | 74,409 | 0.460 | 0.460 |
| mean | | | ~80k | 0.543 | 0.500 |

Free baselines (zero tokens):

| Method | Simulations | Best reward | Feasible |
|---|---|---|---|
| TD3 only, seeds 1-5 | ~990 | 0.431, 0.609, 0.460, -0.005, 0.425 (mean 0.384, sd 0.23) | 4/5 |
| scipy differential evolution (population 200) | 12,200 | 0.657 | yes (first feasible ~1,300) |

Comments:
- The best design came from TD3 in 4 of 5 lean runs. The only LLM gain was 0.609 -> 0.619 (seed 2).
- Seed 3: the LLM made no evaluations and the result is identical to TD3 alone. This also shows runs are deterministic for a given seed.
- Seed 1: hybrid is +0.12 over TD3 alone, but the best design was still TD3's, so the gap comes from how the LLM evaluations changed TD3's trajectory, not from an LLM discovery.
- The mean difference (+0.04) is smaller than the seed-to-seed spread (n=3), so it is not a real effect.
- Feasibility is easy: a random warmup sample was already feasible within about 18 evaluations in seed 1. The hard part is raising the reward, which TD3 and DE do numerically.

### Model comparison (one run each, budget 1000, lean prompt)

| Model | Input tokens (fresh / cached) | Output tokens | Time | Best reward | Best from |
|---|---|---|---|---|---|
| gemini-3.8-flash-low | 59,378 / 0 | 1,183 | 108 s | 0.610 | TD3 |
| claude-sonnet-4-6 | 29,099 / 173,924 | 6,103 | 190 s | 0.603 | LLM |

In the Sonnet run TD3 reached 0.5838. Three independent current-reduction probes from that design (tail multiplier -1, stage-2 multiplier -2, tail width -1 step) gave 0.6026 with every hard constraint kept. A follow-up probe (`mn5` 18 -> 16) violated UGBW and was rejected. This is the useful role: **local polishing of an already feasible design**. One run, one seed: not statistically meaningful. How Google counts cached tokens against the quota is unknown.

## 3. Runs are independent (the cache is not memory)

`cache_read_tokens` is the provider's prefix cache: an identical prompt prefix is processed and billed more cheaply. It never changes the output. Evidence (**measured**):
- `run_experiment.py` calls `agy -p` without `--continue`/`--conversation`, so each run gets a new conversation.
- The archive is per run (`llm/runs/<run>/candidates.jsonl`) unless `--archive` is passed, which is the only way to share designs between runs.
- TD3 lives in the MCP process, created and destroyed with each run.
- Searching one conversation for design IDs of all other runs found 0 matches.
- Cache was 0 for flash-low and large for Sonnet, so it depends on model/provider, not the project.

Not checked: whether `agy` has memory features outside its conversation database.

## 4. Other findings

- `codex_tests/test_references.py` (needs `../references.csv`): the simulator **matches** the five TA designs within 5 % on all seven specs. The remaining 14 discrepancies are all in `normalize_specs` for `slewRate` and `ugbw`.
- Solving `n = (v - t) / (v + t)` for `t` on the reference rows gives targets of about **UGBW = 1 MHz and slew rate = 15 V/us** (checked on Design 4: 14.7 MHz and 6.89 V/us). `TwoStage.yaml` uses 100 MHz and 30 V/us. **Inferred**; the owner should confirm which the assignment requires, since it changes the difficulty.
- An episode has 10 steps and each reset costs one simulation, so about 10 % of the budget goes to resets (990 attempts for 900 steps).
- With batch size 64 and a replay buffer of 9-18 transitions, `ReplayBuffer.sample` samples with replacement. It works but repeats data; a large first warmup avoids this.
- `clean.sh` has mode 644, so `td3_runner.py` prints "Permission denied" every 100 steps.
- `summary['success']` is `true` even when no design is feasible.

## 5. Action steps for Codex

### A. Already in this branch (keep)

1. `llm/run_experiment.py`: new hybrid `workflow` text. Warmup once, then large train batches, at most 3 LLM interventions, no specialist, no initial `get_problem`/`get_candidates`. Batch size is `w = b = max(1, budget // 5)`:
   ```
   Call warmup(n_steps={w}) once right away (skip other exploration), then call train with LARGE batches of about {b} steps.
   TD3 steps cost no tokens; each model turn does, so use few, large calls. After each train batch you may use at most one
   targeted evaluate_candidate/probe_parameters on the best measured design (max 3 interventions in total). Do not consult the
   specialist and skip the initial get_problem/get_candidates reads (this overrides earlier instructions). Stop when budget is nearly used.
   ```
2. `llm/run_experiment.py`: `MODEL = os.environ.get('CAD_MODEL', 'gemini-3.8-flash-low')` to choose the model (`agy models` lists them).
3. Use budgets of several hundred to a few thousand, for example `python -B llm/run_experiment.py --budget 1000`.

### B. Next changes (small, not tested)

1. `llm/mcp_server.py`, `_td3_batch`: reject `n_steps` below a minimum (for example 50) with a clear error.
2. `llm/mcp_server.py`, `_evaluate`: cap LLM evaluations per run (for example 8) and return a clear error afterwards.
3. `llm/run_experiment.py`: inject `adapter.problem(adapter.context())` (about 1.4 KB JSON) into the prompt and remove the mandatory initial reads from `llm/experiment.md`.
4. `llm/run_experiment.py`: make `summary['success']` require `best['hard_satisfied']`.
5. Remove duplicated rules ("small change", "wait for measurement", "no scripts") that appear in `experiment.md`, `coordinator.md`, `GEMINI.md` and both skills.
6. Shorten tool results: drop the empty `replay` dict and `units` in `evaluate_candidate`; return deltas against the base in `probe_parameters`; report area in um^2 and current in uA (a model once wrote "0.83 nm^2" for 6.99e-10 m^2).
7. `chmod +x clean.sh`.

### C. Make the LLM useful (design idea, not tested)

1. **Search-space prior (recommended).** Call the LLM once for tighter per-parameter bounds from circuit physics and the five TA designs in `references.csv`, then let TD3 or DE search inside that box. Motivation: top feasible TD3 designs cluster in a small region (channel lengths 90-180 nm of 45-225, `cap` 0.5-4.3 pF of 0.1-10, `res` 1.6-7.3 kohm of 0-9.9). Do not derive bounds from TD3 results (leakage). Implement in `CircuitEnv.param_ranges` or a wrapper in `llm/td3_session.py`.
2. **Final polish.** One LLM intervention after the numerical phase lowering area/current while keeping hard-constraint margins.
3. **Rationale writer.** LLM explains the final design's trade-offs for the report.

### D. How to evaluate

- Compare simulations until the first feasible design and reward at 50/100/200/500 simulations, not final reward at 1000.
- At least 5 seeds per arm, same budget and seeds, count fresh and cached tokens separately.
- Arms: TD3 only; lean hybrid; hybrid with the bounds prior; optionally DE.

### E. Confirm with the owner

Which `ugbw` and `slewRate` targets does the assignment require (100 MHz / 30 V/us in the YAML vs about 1 MHz / 15 V/us in the TA reference)?

## 6. Reproduction

Python 3.12 venv, `pip install -r requirements.txt`, `brew install ngspice`, `agy` signed in. `AGY` in `run_experiment.py` points to a Windows path; on macOS a symlink at `../.tools/antigravity/agy.exe` was used.

```bash
source .venv/bin/activate
python -B -m unittest codex_tests.test_persistent_session codex_tests.test_replay_injection codex_tests.test_mcp_server codex_tests.test_multi_agent
python -B llm/run_experiment.py --budget 1000
CAD_MODEL=claude-sonnet-4-6 python -B llm/run_experiment.py --budget 1000
python -B llm/run_experiment.py --budget 1000 --td3-config path/to/params.json   # another seed
```

Each run writes `llm/runs/<run>/summary.json` (`usage`, `best`) and `session_*/calls.jsonl` (tool-call audit). The free baselines used scratch scripts: TD3 alone via `TD3Session.run('warmup', 200)` then `train` batches 200, 200, 200, 100 with seeds 1-5 (copies of `output_figs/2026-11-05--18-35-18/params.json` with `seed` changed); DE via `scipy.optimize.differential_evolution` over grid indices with `CircuitAdapter.assess` as the objective.

## Limits

Single runs for most conditions, 3-5 seeds for the main comparison. Differences below about 0.1 reward should not be called real. Fixed per-call context and Google quota accounting are estimates.
