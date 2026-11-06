r"""Validate the five TA designs without changing project code or references.

From cad-git: .venv\Scripts\python.exe -B codex_tests/test_references.py
Optional CSV path: append the path to references.csv to that command.

Checks: action ordering/scaling, normalization, reward/feasibility, five real
simulations, finite float32 observations/rewards, and the zero-UGBW fallback.
Failures are collected so one mismatch does not prevent the other designs
from being checked. A nonzero exit status means discrepancies were found.
"""
from pathlib import Path
import os
import shutil
import sys
import tempfile

TEST_DIR = Path(__file__).resolve().parent
REPO = TEST_DIR.parent
CSV = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO.parent / 'references.csv'
ARTIFACTS = TEST_DIR / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix='references_', dir=ARTIFACTS))
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
os.environ['MPLCONFIGDIR'] = str(RUN / 'matplotlib')
os.environ['MPLBACKEND'] = 'Agg'

import numpy as np
import pandas as pd
from circuit_env import CircuitEnv

# Set before looking at simulator results. Do not widen these to hide failures.
ARITHMETIC_RTOL = 1e-8
ARITHMETIC_ATOL = 1e-10
MEASUREMENT_RTOL = 0.05  # Initial 5% comparison criterion, not a TA guarantee.
MEASUREMENT_ATOL = {'area': 1e-18, 'current': 1e-12, 'gain': 1e-9,
                    'noise': 1e-12, 'phm': 1e-6, 'slewRate': 1e-6, 'ugbw': 1.0}


def main():
    references = pd.read_csv(CSV, index_col='Attribute')
    designs = [column for column in references.columns if column != 'Unit']
    assert len(designs) == 5 and references.index.is_unique, 'Expected five designs and unique attributes'
    assert np.isfinite(references[designs].to_numpy(dtype=float)).all(), 'CSV contains invalid numbers'

    # The starter code resolves inputs relative to cwd. Use unchanged copies in
    # codex_tests so netlists, CSV outputs, and any caches stay inside that folder.
    shutil.copytree(REPO / 'ngspice_interface/files', RUN / 'ngspice_interface/files')
    previous_cwd = Path.cwd()
    os.chdir(RUN)
    failures = []
    measurement_rows = []
    try:
        env = CircuitEnv()
        assert len(env.dict_params) == 20 and len(env.dict_targets) == 7
        assert len(env.hard_constraints) == 5
        print(f'CSV: {CSV}\nArtifacts: {RUN}')
        print('PVT from existing environment:', env.pvt_corner)
        print(f'Measurement criterion: rtol={MEASUREMENT_RTOL}, atol={MEASUREMENT_ATOL}')

        for design in designs:
            print(f'\n--- {design} ---')
            params = {name: float(references.at['param_' + name, design]) for name in env.dict_params}
            action = np.array([references.at['action_' + name, design] for name in env.dict_params], dtype=float)
            assert action.shape == (20,) and np.isfinite(action).all()

            # Detect wrong action order, scaling, quantization, or bounds.
            refined = env.action_refine(action)
            parameter_errors = []
            for name in env.dict_params:
                # Unit-aware atol: a millionth of one allowed parameter step.
                atol = env.param_ranges[name]['step'] * 1e-6
                if not np.isclose(refined[name], params[name], rtol=ARITHMETIC_RTOL, atol=atol):
                    failures.append(f'{design}: action_refine {name}: {refined[name]:.12g} != {params[name]:.12g}')
                    parameter_errors.append({'parameter': name, 'returned': refined[name], 'reference': params[name]})
            print(f'Action mapping: {20 - len(parameter_errors)}/20 parameters match')
            if parameter_errors:
                print(pd.DataFrame(parameter_errors).to_string(index=False))

            # Use supplied specs, isolating the math from simulator measurements.
            specs = {name: float(references.at['spec_' + name, design]) for name in env.dict_targets}
            reference_norm = {name: float(references.at['norm_' + name, design]) for name in env.dict_targets}
            normalized = env.normalize_specs(specs)
            normalization_rows = []
            for name in env.dict_targets:
                match = np.isclose(normalized[name], reference_norm[name],
                                   rtol=ARITHMETIC_RTOL, atol=ARITHMETIC_ATOL)
                normalization_rows.append({'spec': name, 'computed': normalized[name],
                                           'reference': reference_norm[name], 'pass': bool(match)})
                if not match:
                    failures.append(f'{design}: normalize_specs {name}: {normalized[name]:.12g} != {reference_norm[name]:.12g}')
            print('Normalization:\n' + pd.DataFrame(normalization_rows).to_string(index=False))

            expected_feasible = all(specs[s] <= env.dict_targets[s] if s == 'noise'
                                    else specs[s] >= env.dict_targets[s] for s in env.hard_constraints)
            expected_reward = float(references.at['reward', design])
            # Both paths distinguish a reward-equation error from a normalization error.
            for label, norm in [('computed normalization', normalized), ('CSV normalization', reference_norm)]:
                observation = np.array([norm[name] for name in env.dict_targets], dtype=np.float32)
                reward, feasible = env.reward_computation(norm)
                if not np.isfinite(observation).all() or not np.isfinite(reward):
                    failures.append(f'{design}: non-finite observation/reward from {label}')
                if not np.isclose(reward, expected_reward, rtol=ARITHMETIC_RTOL, atol=ARITHMETIC_ATOL):
                    failures.append(f'{design}: reward from {label}: {reward:.12g} != {expected_reward:.12g}')
                if feasible != expected_feasible:
                    failures.append(f'{design}: feasibility from {label} != five physical hard constraints')
                print(f'Reward ({label}): {reward:.12g}; reference={expected_reward:.12g}; '
                      f'feasible={feasible}; physical constraints={expected_feasible}')

            # Exactly one ngspice call per design, using TA physical parameters.
            # Do not use refined parameters here: action errors must stay isolated.
            try:
                measured = env.simulate(params)
                if set(measured) != set(env.dict_targets):
                    raise ValueError('Measured specification keys do not match the seven targets')
                measured_norm = env.normalize_specs(measured)
                measured_observation = np.array([measured_norm[s] for s in env.dict_targets], dtype=np.float32)
                measured_reward, _ = env.reward_computation(measured_norm)
                if not np.isfinite(measured_observation).all() or not np.isfinite(measured_reward):
                    failures.append(f'{design}: measured observation/reward is non-finite')
                design_rows = []
                for name in env.dict_targets:
                    actual, reference = float(measured[name]), specs[name]
                    # Relative error is undefined at reference=0; use the stated atol there.
                    percent = 100 * abs(actual - reference) / abs(reference) if reference != 0 else None
                    match = np.isfinite(actual) and np.isclose(actual, reference,
                        rtol=MEASUREMENT_RTOL, atol=MEASUREMENT_ATOL[name])
                    row = {'design': design, 'spec': name, 'unit': references.at['spec_' + name, 'Unit'],
                           'measured': actual, 'reference': reference, 'error_%': percent, 'pass': bool(match)}
                    design_rows.append(row)
                    if not match:
                        failures.append(f'{design}: measured {name}: {actual:.12g} != {reference:.12g} '
                                        f'(relative error {percent}%)')
                measurement_rows.extend(design_rows)
                print('Measurements:\n' + pd.DataFrame(design_rows).drop(columns='design').to_string(
                    index=False, float_format=lambda x: f'{x:.8g}', na_rep='undefined'))
                for output in env.simulation_engine.output_files:
                    if not Path(output).is_file() or Path(output).stat().st_size == 0:
                        failures.append(f'{design}: missing or empty simulator output {output}')
            except (OSError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
                failures.append(f'{design}: simulation/measurement failed: {type(error).__name__}: {error}')
                print(f'SIMULATION/MEASUREMENT FAILED: {error}')

        # No ngspice needed: an amplifier below unity at every frequency has no UGBW.
        freq = np.logspace(0, 4, 5)
        response = np.full(5, 0.5 + 0j)
        ugbw = env.simulation_engine.find_ugbw(freq, response)
        phm = env.simulation_engine.find_phm(freq, response)
        fallback_specs = dict(env.dict_targets, ugbw=ugbw, phm=phm)
        fallback_norm = env.normalize_specs(fallback_specs)
        fallback_reward, fallback_feasible = env.reward_computation(fallback_norm)
        fallback_observation = np.array(list(fallback_norm.values()), dtype=np.float32)
        assert ugbw == 0 and phm == 0, 'No crossing must use the existing zero fallback'
        assert fallback_norm['ugbw'] == -1 and fallback_norm['phm'] == -1
        assert np.isfinite(fallback_observation).all() and np.isfinite(fallback_reward)
        assert not fallback_feasible
        assert np.isclose(fallback_reward, -env.spec_weights['ugbw'] - env.spec_weights['phm'])
        print(f'\nPASS no-UGBW fallback: UGBW=0, PHM=0, normalized=-1 each, reward={fallback_reward}, feasible=False')
        print(f'Simulator attempts: {env.counter} (expected five)')
        assert env.counter == 5

        pd.DataFrame(measurement_rows).to_csv(RUN / 'measurement_comparisons.csv', index=False)
        summary = '\n'.join(failures) if failures else 'All reference comparisons passed.'
        (RUN / 'discrepancies.txt').write_text(summary, encoding='utf-8')
        print(f'\n{len(failures)} discrepancies\n{summary}')
        if any(': action_refine ' in item for item in failures):
            print('Action discrepancies: inspect grid endpoints and rounding/bin-index conventions; '
                  'do not hide a whole-step offset with a larger tolerance.')
        if any(': normalize_specs ' in item for item in failures):
            print('Normalization discrepancies: compare YAML targets with the targets used by the TAs.')
        if any(': measured slewRate:' in item for item in failures):
            print('Slew-rate discrepancies: the current method averages rising and falling 10-90% '
                  'crossing rates. Confirm the TA edge, threshold and interpolation definition.')
        return 1 if failures else 0
    finally:
        os.chdir(previous_cwd)


if __name__ == '__main__':
    sys.exit(main())
