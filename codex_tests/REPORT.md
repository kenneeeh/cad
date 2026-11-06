# Milestones 1–2 validation

Validated on 3 November 2026 using the checkout's Python 3.12 environment and ngspice 47. No dependencies were added. No training or LLM calls were made.

## Scope and preserved work

The only existing file edited in this task is `circuit_env.py`. Hashes taken at the beginning confirm that `dut_testbench.py`, `ngspice_wrapper.py`, the original circuit and YAML, the existing unit test, TD3 files, and runner are unchanged. In particular, the user's updated `np.abs(vout)` UGBW calculation and its zero return on missing crossings were preserved.

All new files are under `codex_tests/`, including these tests, reports, the before-edit snapshot, and an exact task-specific patch. All runtime artifacts and copied inputs are inside `codex_tests/artifacts/`. The artifacts are locally ignored by `codex_tests/.gitignore`; no parent ignore file was edited. Existing uncommitted work from earlier tasks was preserved. Nothing was committed, pushed, or pulled.

## Tests and results

Eight distinct tests passed; one additional regression is explicitly marked `expectedFailure` because it exposes a real, unresolved normalization problem.

| Test | Result |
| --- | --- |
| Original sizing through DUT, all seven metrics and four output files | Pass |
| Actual `circuit_env.py` main block: reset and one step, seven-element float32 observation, counters, manual reward and normalization | Pass |
| Known reward cases, optimization term in both branches, UGBW zero penalty | Pass |
| Synthetic response with no unity-gain crossing | Pass: found=False, UGBW=0, PHM=0 |
| NaN, positive/negative infinity, and None injected into each of seven measurements; direct reward checks too | Pass: finite reset/step outputs, reward -5.1, hard_satisfied=False |
| Failed simulator and simulation counter, including a relaxed success threshold | Pass |
| Missing measurement and zero normalization denominator | Pass |
| UGBW=0 and PHM=0 are penalized without classifying the simulator as failed | Pass: reward -2.0 when other specs equal targets |
| Negative phase margin below -60 degrees must not satisfy the PHM constraint | **Expected failure: unresolved** |

Only three real simulator calls were made: one original-circuit evaluation, plus the main block's reset and step. Pure Python follow-up checks used mocks and synthetic data. Mock call counters in those tests do not represent additional physical simulations. No TA reference measurements were invented.

`test_output.txt` records the first seven tests. `additional_test_output.txt` records the zero-UGBW case and known negative-PHM failure. `finite_checks_output.txt` records the final four pure-Python guard checks. PowerShell rendered unittest's stderr as NativeCommandError records in those early logs even though the Python exit codes were zero; the final runner now prints unittest output to stdout. A harmless docstring escape warning in the first run was fixed in the test file.

## Original circuit results

The original sizing was read from **all** `.param` assignments in `TwoStage.cir` and passed directly into DUT, bypassing `action_refine()`. `mn1=38` and `mn5=60` were retained despite the YAML's action maximum of 25. The original temperature of 25 degrees C and other circuit settings were retained. The original circuit file was not edited.

| Specification | Measured value | Unit |
| --- | ---: | --- |
| area | 1.111874571e-9 | m² (1111.874571 µm²) |
| current | 1.0779095e-4 | A (107.79095 µA) |
| gain | 1.1778811 | V/V |
| noise | 4.4794519e-5 | V RMS (44.794519 µV RMS) |
| phm | 144.5535599 | degrees |
| slewRate | 4.068209968 | V/µs |
| ugbw | 606369.9333 | Hz |

The four transient, AC, DC and noise files exist and contain data. The low-frequency AC magnitude agrees with the reported gain; the DC current is the negated supply-current column. Both columns in this particular integrated-noise output contain the same RMS value, agreeing with the parser's noise result. Gain is linear V/V, not dB; noise is integrated output noise over the netlist's 1 Hz–1 THz sweep, not a noise density.

These are finite, numerically plausible outputs, **not certified reference values**. The low gain is visible in the raw AC output and is far below the target of 200; this design also misses the 15 V/µs slew-rate target and 1 MHz UGBW target. A high reported phase margin does not mean the design meets the other requirements. Original-design reward from the unchanged equation: **-1.7773834924**, hard_satisfied=False.

Detailed original outputs: `artifacts/run_juiv65d1/original_results.json` and the CSVs it names. These are real run results, not substitutes for the TA reference CSV.

## Environment run

The actual main block completed two simulator calls, returned seven-element finite float32 observations, and printed physical parameters, raw specs, reward, done and info. The step's manually calculated reward was **-1.5586657417**, equal to the environment reward. `done=False`, `hard_satisfied=False`, `invalid_simulation=False`. After reset plus one step: env_steps=1, episode_steps=1, simulation_count=2.

Full output: `artifacts/run_juiv65d1/environment_main.txt`. Final-step parameters, metrics, normalized values and counters: `artifacts/run_juiv65d1/environment_results.json`. Random initial/action values vary on reruns; these numbers describe this saved run.

## Exact source changes and why

See `circuit_env_changes.patch` for changes against the user's file at the start of this task, rather than against Git HEAD (which also includes the user's earlier implementation).

1. Added `simulation_count`, incremented immediately before calling the simulator. It counts reset evaluations and failed simulator attempts; a failure during netlist generation is not counted because the simulator was not called. It is conservative if the executable cannot launch. No 5,000-call budget enforcement was added.
2. Ensure the simulator output directory exists before launch. A clean clone does not contain ignored scratch directories.
3. Normalize in YAML target order, so observations always have the same seven positions. Reject missing/None/non-finite measurements, zero denominators, and normalized values that are non-finite or cannot fit into float32. The equation for accepted inputs is unchanged.
4. At `evaluate()`, clear stale results, catch the specific simulation/file/numerical failures, retain raw metrics when available, and record `simulation_error`. Return a pessimistic finite normalized observation: area/current/noise=+1; gain/PHM/slewRate/UGBW=-1. Unexpected programming errors are not covered by a blanket catch.
5. Added a small `np.isfinite` guard at the start of `reward_computation()` and a final finite/float32-range check. Invalid reward inputs return a finite negative reward and False. Valid inputs use the existing course equation.
6. Derived `failure_reward = -sum(hard weights) - 0.05*sum(optimization weights)`, which is **-5.1** for the provided YAML. This matches the pessimistic limiting observation in the original failure branch for nonnegative physical metrics. It is not a universal mathematical lower bound for negative PHM, which has a separate unresolved problem below. `step()` explicitly uses this reward and hard_satisfied=False on simulator/measurement failure even if success_threshold is relaxed.
7. Added `invalid_simulation` and `simulation_error` to step info. A finite poor design, including the retained UGBW=0/PHM=0 convention, stays distinct from a simulator failure or non-finite measurement. Reset keeps the existing array-only interface; inspect `env.simulation_error` after reset if needed.
8. The main block now prints info and simulation count. Four blank lines had trailing whitespace removed. No other source files were edited.

The guards protect observations and rewards returned to the existing TD3 interface; TD3 and its replay buffer were not modified.

## Important unresolved issues

**Negative phase margin can be rewarded incorrectly by the existing normalization.** The reset in this run returned PHM=-62.3026175 degrees. With a target of 60, `(value-target)/(value+target)` gives **+53.114605**, a positive observation that is treated as satisfying that hard constraint. A synthetic PHM=-70 case gives +13 and, with other specs at their targets, incorrectly reports all hard constraints satisfied. This is finite, so `isfinite` cannot fix it. Exactly -60 is now handled as a division failure, but nearby and more negative values still need a domain policy. The expected-failure test keeps this visible. No normalization/reward redesign was made without approval.

Other inspected limitations were left unchanged: `_get_best_crossing()` brackets only the first and last sweep frequencies, so internal or multiple crossings need more validation; slew-rate extraction pairs threshold crossings by position and needs comparison with real reference transients. `reset(seed=...)` does not explicitly seed the separately sampled action space. These do not invalidate the specific passing checks, but they limit the conclusions.

The existing `ngspice_interface/unit_test.py` bypasses the portable wrapper and invokes a Unix shell command, including `/dev/null`. It also switches to the real repository directory and would write files outside codex_tests. It was inspected but not executed or modified. The new integration test uses the actual DUT and wrapper in an isolated working directory. Measurement-function tests were not broadly duplicated.

**Readiness:** the simulator → metrics → environment pipeline executes, and invalid-number/failure guards pass, but a long TD3 run should wait for a decision on negative-PHM normalization. This validation did not certify all measurements or the full TD3 training loop.

## Simulation budget

Episode steps count calls to step in the current episode. Environment steps count lifetime calls to step. Actual circuit evaluations include reset as well as step. With 10 steps per episode, 500 complete episodes require **5,500** simulator calls, not 5,000. Use `simulation_count` when comparing methods; failed attempts also consume the recorded budget. Extra standalone DUT calls are not automatically included in an environment instance's counter and must be included in the overall experiment budget separately.

## Re-run

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B codex_tests\test_milestones.py
```

Each run creates a separate directory under codex_tests/artifacts, copies only course inputs unchanged, and changes the test working directory there. The real project modules are imported from the checkout. No original circuit data or project scratch files are overwritten.

## Still requires the TA CSV

Reference accuracy of gain, noise, phase margin, slew rate, UGBW, area, current and the corresponding rewards remains unverified. Add comparisons against actual `reference_designs.csv` when supplied. Do not treat the saved simulator measurements as independent reference data.
