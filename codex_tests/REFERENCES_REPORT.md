# TA reference validation — 4 November 2026

Created `test_references.py` in **codex_tests**, following the instruction that all new files must stay there. The script uses pandas and the existing CircuitEnv/DUT methods. No production code, YAML, netlist, CSV, or dependency files were edited. No TD3 run, commit, or push was performed. Hashes before and after the run confirmed the source and reference inputs were unchanged.

Input: `../../references.csv` relative to codex_tests (the supplied CSV in CADproject). It was read with `pd.read_csv(..., index_col='Attribute')`. `Unit` is metadata; the remaining five columns are designs. All supplied numbers are finite.

## What each check means

1. **Actions → physical parameters:** construct the 20 actions in `env.dict_params` order and call `action_refine`. Compare every result with its physical reference. This detects action-order, bound, scaling, and discretization errors.
2. **Specs → normalization:** pass the seven supplied physical specs to `normalize_specs` and compare every result with `norm_`. This isolates normalization and target settings from simulator behavior.
3. **Reward and feasibility:** call `reward_computation` on the computed normalized specs and compare with `reward`. Also call it with the CSV normalized specs to isolate the reward equation. Independently check all five physical hard constraints: noise <= target; gain, PHM, slew rate and UGBW >= target. This detects an incorrect reward equation or a wrongly reported feasible design. All five reference designs are infeasible under both sets of target values discussed below; this dataset does not test a fully feasible reference design.
4. **Five physical simulations:** call `env.simulate` once per design with the CSV `param_` values, regardless of action-test failures. Compare the seven returned measurements and check all four output files exist and are nonempty. This isolates the simulator and measurement pipeline from action conversion.
5. **Finite observations and rewards:** assemble float32 observations in YAML target order from the computed, CSV, and measured normalized specs; check each and its reward is finite. This validates these reference cases, not arbitrary invalid future measurements.
6. **No-UGBW fallback:** use a synthetic response of magnitude 0.5 at all frequencies. Existing DUT methods return UGBW=0 and PHM=0. Existing normalization returns -1 for each; reward is -2.0 with all other specs exactly at target, and feasibility=False. No additional ngspice call is needed. This preserves the user's zero-fallback policy.

The script collects discrepancies instead of stopping at the first comparison, so all five designs are evaluated. Nonzero exit code **1** is intentional when reference comparisons fail.

## Tolerances chosen before running

- Action parameters: relative tolerance 1e-8; absolute tolerance one millionth of the corresponding YAML parameter step. This handles floating-point representation across different physical units without accepting a full grid-step error.
- Normalized specs and rewards: relative tolerance 1e-8 and absolute tolerance 1e-10, allowing rounding of the published CSV decimals.
- Simulator measurements: relative tolerance **5%**, plus tiny explicit unit-specific absolute tolerances listed in the script. This is a transparent initial comparison criterion, not a TA-certified accuracy requirement. No tolerances were changed after seeing the results. Relative percentage error is reported as `100*abs(measured-reference)/abs(reference)`; a zero reference would instead be checked with the stated absolute tolerance and its relative error reported as undefined.

## Results

| Check | Result |
| --- | --- |
| Action parameters | **0/100 match**: all 100 outputs are one YAML step above their reference |
| Normalized specs | **25/35 match**: slew rate and UGBW differ for every design |
| Reward using CSV normalized specs | **5/5 match** |
| Reward using current normalize_specs output | **1/5 match**: only Design 1 |
| Feasibility flags | All five correctly False, with either source of normalization |
| Simulator executions | **5/5 completed**, four nonempty output files each |
| Measured specs at the stated 5% criterion | **30/35 match**: only slew rate fails |
| Finite observations/rewards for these cases | Pass |
| Synthetic no-UGBW/PHM fallback and penalties | Pass |

There are **119 individual discrepancies**: 100 action-parameter comparisons, 10 normalized-spec comparisons, four rewards downstream of normalization, and five slew-rate measurements. The suite therefore exits 1. These are comparison failures, not an installation failure.

The five simulator calls used the current environment's **TT process, 1.2 V, 27 degrees C**. Simulator calls used the supplied physical parameters directly; no action-derived parameters were substituted. Models and input netlist were copied unchanged into a working directory under codex_tests/artifacts so generated files stay there.

## Action conversion discrepancy

All outputs are exactly one allowed parameter step above the TA reference. For example, Design 1 expects mp1=6 but returns 7; wp1=2.25e-6 m but returns 2.50e-6 m; res=9500 ohm but returns 9600 ohm.

This systematic pattern points to a difference in grid endpoints and/or rounding/bin-index conventions, rather than floating-point precision or misordered actions. The current implementation scales over the inclusive min/max range and rounds to the nearest step. Confirm the TA discretization convention before changing it; blindly subtracting a step could break boundary actions. The implementation was not changed.

## Target mismatch explains normalization and downstream rewards

For the given normalization equation, a target can be inferred from a supplied raw spec x and normalized spec n as `target = x*(1-n)/(1+n)`. Across all five designs this gives:

| Target | Current YAML | Implied consistently by TA CSV |
| --- | ---: | ---: |
| Slew rate | 15 V/us | **30 V/us** |
| UGBW | 1 MHz | **100 MHz** |

The other five inferred targets agree with the YAML. These two setting differences explain the ten normalization failures. The reward function itself matches all five CSV rewards when supplied their normalized values.

| Design | Reward from current normalization | TA reward |
| --- | ---: | ---: |
| 1 | -0.252751449721 | -0.252751449721 |
| 2 | -0.925454060728 | -2.05803492421 |
| 3 | -0.477706720991 | -1.61006578483 |
| 4 | -0.381265899285 | -1.38098631784 |
| 5 | -1.08051716132 | -2.19043512492 |

Design 1's matching reward does not validate its normalization: both mismatched normalized quantities remain positive, and positive hard-constraint values contribute zero penalty. The other failed constraints and optimization terms give the same reward. No YAML or reward equation was edited.

## Slew-rate discrepancies

All six other metrics match within 5%. Across those metrics, the largest relative error is noise for Design 5 at **0.13052%**. Gain, current, area, UGBW and phase margin agree much more closely than the 5% criterion. Full measured/reference/error tables for all 35 measurements are in the saved output and comparison CSV.

| Design | Measured V/us | TA V/us | Absolute relative error |
| --- | ---: | ---: | ---: |
| 1 | 17.80821380 | 72.13265032 | 75.3119% |
| 2 | 3.01477641 | 4.93915592 | 38.9617% |
| 3 | 7.07951106 | 9.15732523 | 22.6902% |
| 4 | 5.95865880 | 6.89444485 | 13.5730% |
| 5 | 4.20237691 | 4.49630542 | 6.5371% |

Inspecting the saved transients confirms that the existing method averages both rising and falling threshold-crossing rates. Design 2, for example, has rising rates around **4.94664 V/us** and falling rates around **1.08292 V/us**. Their average is the reported 3.01478 V/us, while the reference is 4.93916 V/us. Design 5's rising rate is approximately 4.48424 V/us, close to the reference 4.49631 V/us, but averaging falling rates lowers the result.

This suggests a difference in which edge is measured and how the slope is extracted. However, selecting rising edges alone does **not** explain Design 1: its rising 10–90% rate is around 21.99894 V/us, still well below 72.13265 V/us. Confirm the TA threshold definition, edge selection, slope definition, and interpolation/timestep assumptions. The present code uses global waveform minima/maxima for the 10–90% thresholds and cubic interpolation of crossings. These are possible causes to investigate, not a confirmed replacement measurement method. No tolerance, transient settings, or measurement implementation was altered.

## Files and rerun

- `test_references.py`: the single new executable test script.
- `references_output.txt`: full validation output, including all parameter failures, normalization comparisons, rewards, and all seven measured specs per design.
- `references_diagnostics.txt`: threshold crossings and per-edge slew-rate diagnostics from saved outputs; no extra simulations were run.
- `artifacts/references_vgrihlf3/measurement_comparisons.csv`: machine-readable 35-row measured/reference/error table.
- `artifacts/references_vgrihlf3/discrepancies.txt`: all 119 failed comparisons.
- `artifacts/references_vgrihlf3/no_backup/`: five generated netlists and their simulator outputs.

From cad-git:

```powershell
.\.venv\Scripts\python.exe -B codex_tests\test_references.py
```

An explicit CSV path can be supplied as the final argument. Each run creates a fresh artifact directory; it runs exactly five circuit simulations and no training. The script's final diagnostic hints were added after the recorded run; they only print interpretation and do not change comparisons or tolerances.

The environment does not yet reproduce the full TA reference pipeline because action discretization, two target settings, and slew-rate extraction differ. The passing reward-equation and six-metric simulator checks narrow down the work needed before TD3 comparisons. This report supersedes the older codex_tests/REPORT.md only for validation against these newly supplied references.
