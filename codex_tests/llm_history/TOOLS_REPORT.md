# Reusable MCP tools and TD3 import: implementation report

Implemented 2026-11-05. This extends the existing harness without changing
CircuitEnv, reward, targets, measurements, actor/critic, replay buffer, learning
updates or hyperparameters. No dependency, agent or orchestration framework was added.
Historical experiment records, including the 0.8597 five-call run, were preserved.

## New behavior

- `get_problem()` returns current physical grids/units, hard-target directions,
  optimization scales, reward weights/convention, available evaluation operations
  and remaining budget. Numerical values come from the existing environment/YAML.
- `get_candidates(k=5)` returns distinct designs ranked by measured Python reward,
  with IDs/specs/violations and no full parameter dictionaries by default.
  A design ID plus `include_parameters=True` retrieves a complete record.
- `evaluate_candidate(base_design_id, changes, hypothesis)` copies the stored base,
  validates absolute changed values and evaluates through the original simulator.
  It returns parent ID, exact old/new values and measured spec differences.
- `simulate_design` keeps its arguments and existing result fields; it additionally
  archives valid measured results and returns a design ID. Both entry points use
  the same lock/counter, including failed simulator attempts.

The append-only JSONL archive keeps full measured records, provenance, parentage
and original imported reward/feasibility. Failed attempts remain in calls.jsonl
without invented measurements. Retrieval filters by a conservative compatibility
fingerprint; imports reject unknown/different configurations explicitly.

## TD3 inspection and smallest export change

No usable saved TD3 evaluations were present. The runner did not call the existing
CSV helper; that helper lacks feasibility/completion/configuration metadata.
Model save/load methods exist, but weights/actions alone are not measured designs.
The agent still has unfinished select_action/update_parameters implementations;
the runner has placeholder defaults and an existing update-call mismatch. These
pre-existing training issues were left untouched; no TD3 training was claimed.

The only TD3-runner change is an export helper and one call after each successful
env.step in the policy and warmup loops. It saves the exact physical parameters,
seven measurements, reward, feasibility, run/simulation IDs, units, fingerprint
and phase. Logging errors are reported while the transition/update path continues.
Warmup exports are explicitly labelled warmup, not trained-policy results.

The offline importer accepts the explicit completed-evaluation JSONL format,
checks bounds/grids, units, completion metadata and compatibility, and recomputes
the existing reward/feasibility to check the originals. It never simulates or
trains. Repeated imports are idempotent by run/simulation ID; conflicts are rejected.
Each rejected input line is reported and makes the importer exit nonzero.

## Multi-agent adaptation and preservation

`single_agent`/`autonomous` and `multi_agent` retain their original initial-design
templates. `td3_refine` is a separate mode in the same runner: preflight selects a
compatible non-fixture TD3 record, then the existing coordinator uses tool metadata,
candidate IDs and small changes. An empty/incompatible/fixture-only archive fails
before a paid agent launch. No fake TD3 fixture is promoted into that live workflow.

The coordinator supplies task-specific packets instead of repository files/full
histories. The designer returns only targeted changed values. The strategist is
optional in refinement; no new agents were added. Existing specialist MCP/write/
shell restrictions remain. Session permission settings allow the four tools only
to the coordinator's MCP-capable context.

Python saves exact parent-relative changes and spec differences. Post-run ranking
includes previously archived results, so a worse refinement cannot discard a better
imported candidate. Token/runtime recording and native handoff metadata remain.
No new live Antigravity run was needed: discovery/integration were verified via MCP.
Token savings are an intended benefit of smaller payloads/fewer consultations;
no numerical LLM-cost improvement is claimed without a measured run.

## Tests and actual execution cost

**29 test cases passed across the focused runs:**

- 14 new mocked/offline tests: metadata/units, base reconstruction and immutability,
  invalid changes before simulation, distinct ranking/reload, mixed-tool budget,
  TD3 import/export and idempotence, incompatible/unverified/inconsistent rejection,
  PVT/target identity changes, generic parameter copying, export-failure safety,
  fixture-only preflight rejection, legacy runner behavior and retaining an imported
  best when a mocked refinement is worse.
- 8 existing multi-agent tests, including real stdio discovery at zero budget.
- 6 original mocked MCP regression tests, including finite fallback behavior and
  unchanged parameter-only/hypothesis calls.
- 1 actual MCP protocol test with **exactly one full ngspice attempt**.

The protocol test imported a clearly labelled TD3 fixture with no simulation,
discovered all four tools, rejected invalid changes at count zero, evaluated a
single resistance-grid change by base ID, retrieved its complete child, verified
the base was unchanged, and blocked further calls through BOTH evaluation tools
at count one. The real child was finite, reward **-0.395247123196666**, with gain
and slew still violated. This was a tool-integration check, not an optimization
success or a trained TD3 result. Tool runtime was 0.2425 seconds; the protocol test
including server startup took 21.819 seconds.

Actual test evidence:
`codex_tests/artifacts/reusable_tools/live_9wutqy7x/protocol_smoke.json`.
Fixture: `codex_tests/fixtures/td3_evaluated_fixture.jsonl`, explicitly marked
TEST FIXTURE ONLY, with a context placeholder bound only in scratch test files.
It reuses stored baseline ngspice values as synthetic TD3-file data. Import was
tested with fixtures/mocks, **not real trained-policy output**.

Total for this extension: **1 actual ngspice call, 0 LLM calls, 0 TD3 training runs**.
Mocked runner logs live only under codex_tests and do not represent extra real
experiments. The optional live test is skipped by the default mocked suite.

## Exact files for this extension

New framework files:

- `llm/circuit_adapter.py`: small TwoStage metadata/validation/compatibility adapter;
  delegates normalization/reward to CircuitEnv.
- `llm/candidates.py`: generic JSONL archive, IDs, copying changes and distinct ranking.
- `llm/td3_candidates.py`: completed-evaluation exporter, checked offline importer and CLI.
- `llm/multi_agent/refinement.md`: ID-based TD3 refinement template.
- `llm/TOOLS.md`: usage, schemas, persistence limits and oral-exam walkthrough.
- `llm/TOOLS_REPORT.md`: this report.

Modified existing framework files:

- `llm/mcp_server.py`: registers the three new tools; reuses validation/assessment
  through the adapter and archives successful evaluations with additional IDs.
- `llm/run_experiment.py`: adds td3_refine/--archive, read-only preflight and preserved
  archived-best selection; keeps the same launcher and usage recorder.
- `llm/README.md`, `llm/multi_agent/README.md`: links and current launch/interface notes.
- `llm/multi_agent/GEMINI.md`: permits the new tools in refinement scope.
- `llm/multi_agent/agent_settings.json`: explicit permissions for the added tools.
- `llm/multi_agent/.agents/agents/coordinator.md`: metadata/ID/difference workflow
  with small packets and optional strategy consultation.
- `llm/multi_agent/.agents/agents/experiment-designer.md`: exact changes from tool metadata.
- `llm/multi_agent/.agents/agents/optimization-strategist.md`: imported TD3 evidence
  is allowed; new training is still prohibited.
- `llm/multi_agent/.agents/skills/sizing-experiments/SKILL.md`: uses current tool
  grids/targets instead of a second numerical copy.

Other changes:

- `td3_runner.py`: logging-only helper and two post-step export hooks, with phase labels.
- New `codex_tests/test_reusable_tools.py` and the labelled JSONL fixture.
- `codex_tests/test_multi_agent.py`, `codex_tests/test_mcp_server.py`: discovery
  assertions now expect the four additive tools; previous behavior checks remain.
- New runtime test scratch files under codex_tests/artifacts only.

No changes to historical reports/recorded experiments, TD3 agent/buffer,
CircuitEnv, YAML, netlists or extraction. No package install, commit or push.

## Interfaces, limitations and next manual step

Candidate storage/copying/ranking is circuit-independent. The adapter holds
TwoStage units/directions and the dependencies used for compatibility, while actual
simulation/reward remain in the existing code. Another circuit would supply adapter
metadata and its existing environment/simulator; no second circuit or plugin registry
was implemented.

JSONL assumes one writer at a time. Import offline before starting refinement.
Fingerprints are deliberately conservative, so even some harmless source/line-ending
changes require review; unknown old outputs are not silently accepted. Completion
markers describe trusted local exports, not cryptographic proof of an arbitrary
external file's authenticity. Configuration/source changes during a run are unsupported.
Historical five-call logs have no new compatibility marker and are not auto-imported.

The remaining prerequisite for a real TD3-to-LLM experiment is genuine completed
TD3 evaluations from a functioning training workflow. Once available, import them
and use the commands in TOOLS.md. No extra account setup is needed, and no expensive
autonomous experiment was launched merely to test deterministic code.

Plain language: TD3 evaluates independently and logs the result. Python checks and
imports it, assigning an ID. The LLM asks for current requirements and the measured
candidate, chooses a targeted engineering change with specialist advice, and sends
only the ID plus changes. Python validates, simulates once, computes all numerical
results and saves the parent/child record. The best measured design is retained
even when the new hypothesis fails.
