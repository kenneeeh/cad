# Reusable tools and TD3 candidate refinement

The tools do deterministic bookkeeping; the LLM chooses engineering experiments.
The existing simulator, targets and reward are unchanged. No extra dependency or
Python agent-orchestration framework is required.

## Four MCP tools

| Tool | Purpose | Simulator cost |
|---|---|---|
| `get_problem()` | Current names, physical bounds/steps/units, targets/directions, reward convention and budget | 0 |
| `get_candidates(k=5)` | Highest-reward distinct measured designs for this configuration; compact IDs, sources, specs, violations, rewards | 0 |
| `get_candidates(design_id=id, include_parameters=True)` | One complete stored record, including physical parameters/provenance | 0 |
| `simulate_design(parameters, hypothesis='')` | Original full-parameter evaluation, plus archive ID | 1 attempt |
| `evaluate_candidate(base_design_id, changes, hypothesis='')` | Copy the measured base, apply absolute values, validate and evaluate | 1 attempt |

Invalid requests and read-only calls consume no simulator budget. Failed ngspice
attempts count. Both evaluation entry points share the same lock and existing
CircuitEnv counter; an import cannot reset it. Restarting the server resets its
per-process counter and is prohibited as a way of extending an experiment.

`changes` contains absolute physical values, not percentages or normalized RL actions.
For example `{"res": 6100}` means set resistance to 6100 ohm, not add 6100 ohm.
This is an API example, not a prescribed sizing experiment. Python constructs and
validates the full dictionary; the base is immutable. Unknown names, off-grid,
non-finite, out-of-range, empty and no-op changes are rejected before simulation.
The response adds parent ID, actual old/new changes and measured spec differences.
Optional pre-call `predictions`/`decision` work as in simulate_design.

`get_problem` reads numerical values from the existing environment/YAML; units,
direction mapping and simulator knowledge live in the small TwoStage adapter.
Topology/physical heuristics remain in the existing opamp skill. The experiment
skill asks for current tool metadata instead of copying numerical grids and targets.

## Archive and compatibility

Each successful evaluation appends a JSONL candidate with unique `design_id`,
`problem_id`, source, run ID, all physical parameters, measured specs, Python reward,
feasibility/violations, units, parent ID, hypothesis and simulation metadata.
Sources are `TD3`, `LLM`, or `initial reference` for a direct simulation matching
initial_design.json. Failed attempts stay in per-session calls.jsonl, without an
invented measured candidate. Existing experiment files are not migrated or overwritten.

Default archive: `CAD_RUNS_DIR/candidates.jsonl`, keeping ordinary baseline runs
isolated. For a reusable archive set `CAD_ARCHIVE_PATH`; td3_refine and the importer
default to `llm/runs/candidates.jsonl`. `--archive` selects another file. Runtime
archives stay under ignored runs/; tests use codex_tests/artifacts/.

Ranking is descending actual Python reward. Identical physical parameter vectors
appear once in default retrieval; all actual evaluations remain in the append log.
The complete record can still be retrieved by its ID. Different configurations
are filtered by problem_id and incompatible new imports are explicitly rejected.

The conservative fingerprint covers actual parameter/target/reward configuration,
PVT, CircuitEnv and simulator/extraction/area code, YAML, netlist, model files,
ngspice executable hash and numpy/scipy versions. It prevents the earlier
rise/fall-versus-rising-only mismatch being silently combined. Even comment, line
ending or unused model-file changes may invalidate compatibility: reject and
review rather than silently pretending such results are comparable. Configuration
and source files must stay fixed during an exporting run/server session.

There is one writer at a time: import offline, then start refinement. JSONL is
simple persistence, not a multi-process database or a crash-recovery framework.
Do not manually edit candidate records or import historical results with guessed
fingerprints. The fingerprint is a compatibility check, not a digital certificate
that an external file is authentic.

## TD3 output: what exists and what was added

The current TD3 runner had no completed-candidate export. Its existing CSV helper
is unused and has no feasibility/completion/configuration provenance. Actor/model
weights or normalized actions alone cannot demonstrate a completed circuit evaluation.
No usable real saved TD3 candidates were found. Several TD3 methods/default arguments
remain unfinished; this extension does not fix them or claim TD3 trained successfully.

Two logging calls were added immediately after successful `env.step` returns in
td3_runner.py. They change no actions, warmup lengths, learning updates, networks,
buffer operations or hyperparameters. The exporter writes:

`llm/runs/td3_<sanitized-run-id>/candidates.jsonl`

Each JSONL record has:

```text
format: cad-evaluated-candidate-v1
source: TD3
run_id, problem_id, circuit, pvt
parameters: complete physical dictionary
specs: seven actual measured values
units, reward, hard_satisfied
evaluation: {completed: true, simulator: ngspice, simulation_id,
             simulation_count, phase: warmup | policy}
```

The exporter checks the existing current evaluation fields, matching physical
parameters, finite measurements and original reward/feasibility. It never samples
or simulates. A logging failure is reported without altering the training transition.
Reset evaluations are not exported by these hooks; only completed steps are.
`source=TD3` identifies the runner, while `phase` distinguishes random warmup
from actor-selected policy evaluations; it does not certify successful learning.

## Import and refine

After genuine compatible TD3 evaluated exports are available, from repository root:

```powershell
.\.venv\Scripts\python.exe -B llm\td3_candidates.py llm\runs\td3_RUN_ID\candidates.jsonl
.\.venv\Scripts\python.exe -B llm\run_experiment.py td3_refine --budget 2
```

Replace RUN_ID with the actual exported folder. For a chosen shared file, pass
`--archive <path>` to both commands. Import runs no model and no ngspice; refinement
uses model credits and at most the specified number of NEW simulator attempts.
The initial TD3 evaluation is reused, not charged again.

The importer reads JSONL, requires a completed evaluation marker and full data,
checks the fingerprint/units/grid, recomputes the existing reward/feasibility, and
rejects inconsistencies. Original reward/feasibility are retained in `original`;
no record is silently rescored under another configuration. Accepted IDs and
line-numbered rejections are printed; any rejection makes the importer exit nonzero.
Repeated imports of the same run/simulation ID reuse its ID; conflicting contents
are rejected. Legacy CSV, action-only files, weights and unknown-provenance old logs
are not promoted to verified measurements.

td3_refine performs a read-only preflight and refuses to launch an agent without
a compatible non-fixture TD3 candidate. It starts from the highest-reward TD3
evaluation. The coordinator retrieves metadata/specs and full parameters only when
needed; specialists receive small relevant packets. The designer proposes changes;
the coordinator calls evaluate_candidate. Only it retains simulation access.
The strategist is optional, for stagnation or a real allocation question.

Existing `single_agent`/`autonomous` and `multi_agent` still use their original
templates and initial-design workflow. No new agents were added. Token/runtime
reporting is retained. Post-run Python compares new results with all compatible
archived candidates, preserving a better imported design if refinement fails.
History includes exact parent-relative changes and spec differences.

## Generic versus circuit-specific code

- `candidates.py`: plain JSONL records, IDs, copying changes, distinct ranking and
  compact/full retrieval. It knows no transistor names or reward equation.
- `circuit_adapter.py`: TwoStage units/directions, source/config fingerprint,
  parameter validation and calls to existing CircuitEnv normalization/reward.
  Simulator execution remains env.simulate; measurements remain the existing DUT.
- `td3_candidates.py`: the explicit export/import schema plus admission validation
  through the adapter. MCP registration remains in mcp_server.py.

Another circuit would supply its own adapter metadata/directions, dependency
fingerprint and existing environment/simulator, then reuse archive/import operations.
No second circuit, registry, dynamic discovery or inheritance hierarchy was built.

## Plain-language walkthrough for the oral examination

TD3 first evaluates designs in its own normal loop. Immediately after a completed
step, a logging hook saves the physical design and actual measurements. An offline
importer checks compatibility and consistency and gives each accepted design an ID.
It does not repeat the simulation.

The coordinator asks Python what the problem is and retrieves a promising measured
TD3 design. Specialists help interpret its weaknesses and propose a small change.
The coordinator sends the ID and changed values. Python copies the original,
validates it and spends one shared simulator call. Python computes reward,
constraints, differences and ranking, saves the parent/child relationship and
returns a compact result. The coordinator decides the next engineering experiment.
If it fails to improve, the earlier best measured design remains available.

## Tests

Default tests use mocks and no model:

```powershell
.\.venv\Scripts\python.exe -B codex_tests\test_reusable_tools.py
```

The optional protocol test performs exactly ONE real full simulation:

```powershell
$env:CAD_TEST_REAL = '1'
.\.venv\Scripts\python.exe -B -m unittest codex_tests.test_reusable_tools.TestProtocol -v
Remove-Item Env:CAD_TEST_REAL
```

TD3 import is tested with the clearly labelled fixture in
`codex_tests/fixtures/td3_evaluated_fixture.jsonl`. The test binds its placeholder
fingerprint to the current configuration only in an isolated scratch archive.
It is not a real TD3 training result; the paid refinement launcher rejects fixtures.
