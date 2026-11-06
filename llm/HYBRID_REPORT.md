# Persistent hybrid architecture: implementation and validation

2026-11-05, checkout d467f61 plus preserved local changes. No model call,
dependency installation, commit or push. This report supersedes the offline
checkpoint workflow; its report/source/evidence remain in codex_tests/llm_history/.

## Existing code reused

- **llm/replay_injection.py is byte-for-byte unchanged.** Every LLM insertion calls
  its existing inject_llm_candidates. No second action conversion or replay path.
- **td3_runner.train and warmup_exploration are called directly.** Their existing
  action selection, env.step, ReplayBuffer.push and training-update sequence is
  retained. train_policy's complete function body is unchanged.
- TD3 actor/critic, losses, optimizers, target updates, exploration noise and
  ReplayBuffer are unchanged. No learning loop was implemented inside llm/.
- The existing export_td3_candidate function is unchanged and now receives the
  shared archive path from the runner. Its obsolete offline import/CLI was archived.
- CircuitEnv, ngspice wrapper/DUT, YAML, netlist, reward, measurement extraction,
  candidate archive and adapter are unchanged. No TA sizing_tools.py was found.

Standalone TD3 was verified before edits using its existing two CPU tests: bounded
finite actions, actual critic/actor/target updates and original random warmup with
no updates. Both passed. Its implementation was inspected in the actual checkout.

## Architecture and seven tools

README.md contains the architecture diagram and commands. Only coordinator and
circuit-sizing-specialist are active native Antigravity roles. The specialist
combines diagnosis and experiment design, returning bottleneck, absolute changes
and a short hypothesis/trade-off. It inherits neither MCP nor shell/write tools.
Both existing physics/sizing skills remain. Native delegation is used; no Python
agent scheduler or model-based evaluator was added.

| Tool | Implementation/use |
|---|---|
| get_problem | Current grids/targets/reward, total remaining evaluations, TD3 status/settings |
| get_candidates | Existing compact distinct ranking across measured LLM/TD3; full sizes by ID |
| simulate_design | Existing validation/evaluation path, archive, insertion or explicit deferral |
| evaluate_candidate | Existing base-ID absolute refinement path, same replay insertion |
| probe_parameters | 1-5 independent evaluate_candidate calls against one unchanged base |
| warmup | Existing runner warmup adds random samples without updates or clearing memory |
| train | Existing runner training continues the same agent/buffer/episode for a bounded batch |

One TD3Session object lives in the server process. It creates one TD3 agent and
one ReplayBuffer lazily at the first warmup/train call. Networks, optimizer state,
ID set and observation/terminal continuation persist across later calls. A separate
CircuitEnv instance protects the TD3 episode from targeted LLM evaluations; both
use the same existing simulation/measurement implementation.

LLM calls before a measured TD3 state are saved and returned as deferred. The next
warmup/train establishes a measured reset, then calls the unchanged insertion
function. Nonterminal interventions insert immediately without simulation; terminal
states defer to the next reset. The initial tool evaluation is now source=LLM too,
so it can be imported; historical records were not relabelled. Insertion reconstructs
physical grid points through action_refine and preserves current observation,
episode counters and network/optimizer state. No artificial predecessor states.

All seven tools share a small count of actual attempts from the two environments.
Before a TD3 batch, required steps plus resets must fit; an oversized batch is
rejected before initialization/simulation. There is no background budget service.
The coordinator chooses guided evaluations, random diversity and later interventions;
no fixed mixture or automatic LLM invocation during warmup/training.

TD3 learning settings are read unchanged from the existing committed
output_figs/2026-11-05--18-35-18/params.json, or an explicit --td3-config file.
Only output routing and per-tool batch lengths change. The new wrapper seeds its
action space; original standalone RNG/cleanup/default behavior is retained.

## Tests and exact cost

Default command from the repository root:

    .venv/Scripts/python.exe -B -m unittest codex_tests.test_persistent_session codex_tests.test_replay_injection codex_tests.test_mcp_server codex_tests.test_multi_agent -v

Final result: **26 passed, 1 skipped** (the opt-in real smoke). These use actual
TD3/buffer code with mocked circuits, mocked CLI outcomes and zero-budget stdio
schema discovery. They verify both reused runner functions/insertion are actually
called; persistent identity/updates; guided plus random replay; no warmup gradients;
independent/invalid probes; deferred/duplicate insertion; unchanged live episode;
resume/reset after failure; compact retrieval; standalone random-only behavior;
two native roles/seven schema tools; and launcher success/error/timeout/bad-JSON
handling without losing measured results. See
[final_unit_output.txt](../codex_tests/artifacts/persistent/final_unit_output.txt).

Opt-in command, with CAD_PERSISTENT_REAL=1:

    .venv/Scripts/python.exe -B -m unittest codex_tests.test_persistent_session.TestRealPersistentMCP -v

**1 passed.** This uses an actual stdio MCP client/server, unmodified current TD3
and ngspice, and the existing saved learning settings (batch 64, noise .03,
actor lr .0005, critic lr .001, original ten-step horizon). No Antigravity/model.

| Operation in the same MCP session | Actual ngspice attempts | Critic updates |
|---|---:|---:|
| SDK-provided initial design | 1 | 0 |
| One independent res=6100 ohm probe | 1 | 0 |
| warmup(2), including first measured reset | 3 | 0 |
| train(2) | 2 | 2 |
| SDK-provided res=6200 ohm intervention | 1 | 0 |
| train(2), continuing original learner | 2 | 2 |
| **Total** | **10** | **4** |

There were **2 delayed actor updates**, **3 imported experiences**, **9 final
replay entries**, **1 TD3 reset**, **6 TD3 step evaluations**, and **0 model calls**.
Replay insertion itself performed **0 additional ngspice evaluations**. The three
source=LLM designs were supplied by the SDK test driver, not invented by a model.
All nine archived measurements/rewards were finite. Best measured reward was
-1.371410706196 and infeasible (gain, slewRate, UGBW violations). No learning-benefit,
feasibility or superiority claim is supported by this deliberately small smoke.
Evidence: [smoke.json](../codex_tests/artifacts/persistent/real_7vt1nx13/smoke.json).
No other real simulator attempts occurred for this task.

Protected-file SHA256 checks confirm unchanged replay insertion, TD3 agent/buffer,
environment, simulator, YAML and netlist. AST comparison confirms unchanged
train_policy and exporter bodies. Changed Python files parse and git diff --check
passes. The new specialist's native configuration/access restrictions were checked
offline; live Antigravity delegation was not exercised because no model run was made.

## Cleanup and preserved work

Archived under codex_tests/llm_history/pre_persistent/: prior train_td3.py offline
checkpoint launcher, old report/prompts/runner snapshots, obsolete three specialist
configs, offline import source, and old workflow tests (as .py.txt). The old
train_td3.py and td3_refine mode are removed from active code. The exporter remains;
no teammate actor/critic/training equations or measured experiment data were deleted.
Older historical records and llm/runs/ were left in place.

The pre-existing tracked/untracked LLM changes, earlier logging-only runner hooks,
and codex_tests contents were inspected and preserved before editing; the snapshot
includes before.diff and protected hashes. The new task intentionally replaces
previous launcher/agent instructions rather than leaving two orchestration systems.
The old two stale offline tests are preserved as history; current tests validate
current settings without relabelling historical measured rewards.

## Changes outside llm/

| File | Exact changed function/lines in final file | Why required | Standalone effect |
|---|---|---|---|
| td3_runner.py | export_evaluation, lines 12 and 15 | Forward optional shared archive path to existing exporter | Default path behavior retained |
| td3_runner.py | train, lines 70-89 | Optional continuation/bounded batches, shared export routing; skip standalone shell cleanup in MCP | Defaults retain original automatic warmup, episode completion and update order |
| td3_runner.py | warmup_exploration, lines 95-109 | Resume measured state and bound random batch without clearing memory | Defaults retain whole-episode random-only warmup |
| td3_runner.py | main, lines 119 and 139 | Remove obsolete offline hybrid callback parameter | Original standalone CLI unchanged |
| codex_tests/test_persistent_session.py | New TestPersistentSession and TestRealPersistentMCP | Focused reusable-backend/launcher and real stdio integration tests | None |
| codex_tests/test_multi_agent.py | test_native_roles_restrict_specialist_tools line 21; prompt assertions lines 38-39; discovery lines 52-53 | Check current two roles/seven tools instead of obsolete roles/schema | None |
| codex_tests/test_hybrid_training.py | Archived whole obsolete test module | Removed launcher is no longer an active API | None |
| codex_tests/test_reusable_tools.py | Archived whole obsolete test module | Removed offline td3_refine/import workflow is no longer an active API | None |

The runner additions are necessary to pause/resume its actual tested loops rather
than duplicating them or monkey-patching a second learner in llm/. train_policy,
readParser and all learning hyperparameters remain untouched by this task.
Local generated logs/netlists/CSV outputs and historical snapshots are confined to
codex_tests/artifacts/ and codex_tests/llm_history/; these are runtime/test evidence.
No files outside llm/ other than the runner and these Codex tests/evidence changed.

Inside llm/: new td3_session.py; updated MCP server, native coordinator/settings,
new sizing specialist, prompts, run_experiment, README and this report; trimmed
unused importer from td3_candidates while retaining its exporter verbatim; removed
the old launcher/three specialist configs. Candidates/adapter/replay/physics skills
and existing MCP registry remain unchanged.

## Limits and oral-exam explanation

State persists only for this MCP process, not after restart. Five standalone ???
defaults, standalone action-space seeding, Unix cleanup and time-limit masks remain
teammate-owned behavior. Failed/reset attempts count even without replay entries.
The summary records final measured best, counts, elapsed time and CLI tokens;
deterministic final actor quality and controlled repeated A/B/C comparisons remain
future experiments. Use matched seeds/settings and account for LLM preparation
cost; no single short trial proves a hybrid learning benefit.

The coordinator asks one sizing specialist for physical advice, then measures a
few informed designs through MCP. Python validates and archives their real specs.
Once TD3 has a measured state, the existing insertion function converts each design
to a checked normalized action and adds its reward/next state to the same replay
buffer. Warmup adds random diversity without learning. Train calls reuse the
existing TD3 loops and keep the same networks, optimizers and episode across calls.
The coordinator can inspect TD3 candidates, measure an intervention, and continue
training. Off-policy TD3 can learn from both sources through its ordinary critic
and actor updates. Replay insertion costs no new simulation; the original design
was already measured. Physics directs experiments; TD3 supplies numerical learning.
