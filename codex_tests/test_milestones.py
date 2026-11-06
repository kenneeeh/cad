r"""Run from cad-git: .venv\Scripts\python.exe -B codex_tests/test_milestones.py

Only the original design and __main__ smoke check launch ngspice: three calls.
All copied inputs, simulator outputs, and caches stay under codex_tests/artifacts.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
REPO = TEST_DIR.parent
ARTIFACTS = TEST_DIR / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix='run_', dir=ARTIFACTS))
os.environ['MPLCONFIGDIR'] = str(RUN / 'matplotlib')
os.environ['MPLBACKEND'] = 'Agg'
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))

import numpy as np
from circuit_env import CircuitEnv
from ngspice_interface import DUT

YAML = 'ngspice_interface/files/yaml_files/TwoStage.yaml'
UNITS = {'area': 'm^2', 'current': 'A', 'gain': 'V/V', 'noise': 'V rms',
         'phm': 'degrees', 'slewRate': 'V/us', 'ugbw': 'Hz'}


def original_parameters(dut):
    """Read all assignments, including multiple parameters on the same line."""
    sizes = {}
    units = {'': 1., 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'm': 1e-3, 'k': 1e3}
    for line in Path(dut.netlist_path).read_text().splitlines():
        if line.startswith('.param'):
            for name, number, unit in re.findall(r'(\w+)=([0-9.eE+-]+)([a-zA-Z]*)', line):
                if name in dut.param_names:
                    sizes[name] = float(number) * units[unit]
    assert sizes.keys() == set(dut.param_names)
    return sizes


def manual_reward(specs, env):
    """Independent expression of the course equation for these seven specs."""
    n = {s: (float(specs[s]) - t) / (float(specs[s]) + t)
         for s, t in env.dict_targets.items()}
    w = env.spec_weights
    hard = (w['gain'] * min(n['gain'], 0) - w['noise'] * max(n['noise'], 0)
            + w['phm'] * min(n['phm'], 0) + w['slewRate'] * min(n['slewRate'], 0)
            + w['ugbw'] * min(n['ugbw'], 0))
    success = hard >= env.success_threshold
    cost = -w['area'] * n['area'] - w['current'] * n['current']
    return n, hard + (0.3 + cost if success else 0.05 * cost), success


class MilestoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_cwd = Path.cwd()
        # The existing code uses cwd for paths; stage unchanged course inputs here.
        shutil.copytree(REPO / 'ngspice_interface/files', RUN / 'ngspice_interface/files')
        (RUN / 'no_backup/output_files').mkdir(parents=True)
        os.chdir(RUN)
        print('All test artifacts:', RUN, flush=True)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old_cwd)

    def test_original_circuit(self):
        dut = DUT(YAML)
        params = original_parameters(dut)
        # Deliberately bypass action_refine: mn1=38 and mn5=60 exceed RL bounds.
        self.assertEqual(params['mn1'], 38)
        self.assertEqual(params['mn5'], 60)
        netlist = dut.create_new_netlist(parameters=params)
        self.assertEqual(dut.simulate(netlist), 0)
        specs = dut.measure_metrics()
        self.assertEqual(set(specs), set(UNITS))
        for name, value in specs.items():
            print(f'Original {name}: {value:.10g} {UNITS[name]}', flush=True)
            self.assertTrue(np.isscalar(value) and np.isfinite(value), name)
            self.assertGreaterEqual(value, 0, name)
        for path in dut.output_files:
            self.assertTrue(Path(path).is_file(), path)
            self.assertGreater(Path(path).stat().st_size, 0)
        self.assertGreater(specs['gain'], 1)
        self.assertGreater(specs['ugbw'], 0)
        # Inspect stored output columns too; these are diagnostics, not TA references.
        raw_noise = np.genfromtxt(dut.output_files[-1], skip_header=1)
        raw_dc = np.genfromtxt(dut.output_files[-2], skip_header=1)
        env = CircuitEnv(run_id='original_manual_check')
        norm, reward, success = manual_reward(specs, env)
        np.testing.assert_allclose(list(env.normalize_specs(specs).values()), list(norm.values()))
        self.assertAlmostEqual(env.reward_computation(norm)[0], reward)
        report = {'parameters': params, 'specs': {s: float(v) for s, v in specs.items()},
                  'units': UNITS, 'manual_reward': reward, 'hard_satisfied': bool(success),
                  'raw_noise_columns': raw_noise.tolist(), 'raw_dc_columns': raw_dc.tolist(),
                  'files': dut.output_files}
        (RUN / 'original_results.json').write_text(json.dumps(report, indent=2))

    def test_environment_main(self):
        output = io.StringIO()
        # Execute the actual __main__, not a rewritten approximation.
        with contextlib.redirect_stdout(output):
            namespace = runpy.run_path(str(REPO / 'circuit_env.py'), run_name='__main__')
        (RUN / 'environment_main.txt').write_text(output.getvalue())
        print(output.getvalue(), flush=True)
        env = namespace['env']
        self.assertIsNone(env.simulation_error)
        self.assertEqual(env.simulation_count, 2)
        self.assertEqual((env.env_steps, env.episode_steps), (1, 1))
        self.assertEqual(namespace['ob'].shape, (7,))
        self.assertEqual(namespace['ob'].dtype, np.float32)
        self.assertTrue(np.isfinite(namespace['ob']).all())
        norm, reward, success = manual_reward(env.real_specs, env)
        np.testing.assert_allclose(namespace['ob'], list(norm.values()), rtol=1e-6, atol=1e-7)
        self.assertAlmostEqual(namespace['reward'], reward)
        self.assertEqual(namespace['info']['hard_satisfied'], success)
        self.assertFalse(namespace['info']['invalid_simulation'])
        self.assertFalse(namespace['done'])
        # Reset's printed observation must be finite as well.
        self.assertNotIn('nan', output.getvalue().lower())
        (RUN / 'environment_results.json').write_text(json.dumps({
            'parameters': env.param_values,
            'specs': {s: float(v) for s, v in env.real_specs.items()},
            'normalization': norm, 'manual_reward': reward,
            'reward': namespace['reward'], 'done': bool(namespace['done']),
            'info': namespace['info'], 'simulation_count': env.simulation_count,
            'env_steps': env.env_steps, 'episode_steps': env.episode_steps,
        }, indent=2))

    def test_reward_known_cases_and_zero_ugbw(self):
        env = CircuitEnv()
        self.assertEqual(env.reward_computation(dict.fromkeys(env.dict_targets, 0.0)), (0.3, True))
        specs = dict(env.dict_targets)
        specs['ugbw'] = 0.0
        norm = env.normalize_specs(specs)
        self.assertEqual(norm['ugbw'], -1.0)
        self.assertEqual(env.reward_computation(norm), (-1.0, False))
        # Exercise the optimization term in both branches of the existing equation.
        for gain in [100.0, 300.0]:
            specs.update(gain=gain, ugbw=2e6, area=1e-9, current=3e-4)
            n, reward, success = manual_reward(specs, env)
            actual = env.reward_computation(env.normalize_specs(specs))
            self.assertAlmostEqual(actual[0], reward)
            self.assertEqual(actual[1], success)

    def test_missing_unity_gain_crossing(self):
        dut = DUT(YAML)
        freq = np.array([1., 10., 100., 1000., 10000.])
        response = np.full(5, 0.5 + 0j)
        _, found = dut._get_best_crossing(freq, np.abs(response), 1)
        self.assertFalse(found)
        self.assertEqual(dut.find_ugbw(freq, response), 0)
        self.assertEqual(dut.find_phm(freq, response), 0)

    def test_zero_ugbw_stays_a_penalized_design(self):
        env = CircuitEnv()
        specs = dict(env.dict_targets, ugbw=0., phm=0.)
        with patch.object(env, 'simulate', return_value=specs):
            env.reset()
            ob, reward, done, info = env.step(np.zeros(env.n_actions))
        self.assertEqual(env.cur_norm_specs['ugbw'], -1.)
        self.assertEqual(env.cur_norm_specs['phm'], -1.)
        self.assertEqual(reward, -2.)
        self.assertFalse(info['invalid_simulation'])
        self.assertFalse(info['hard_satisfied'])
        self.assertTrue(np.isfinite(ob).all())

    @unittest.expectedFailure
    def test_negative_phase_margin_must_fail_hard_constraint(self):
        # Known limitation of the unchanged formula: (-70-60)/(-70+60)=+13.
        # Keep the regression visible until the user approves a policy for negative PM.
        env = CircuitEnv()
        specs = dict(env.dict_targets, phm=-70.)
        _, satisfied = env.reward_computation(env.normalize_specs(specs))
        self.assertFalse(satisfied)

    def test_nonfinite_measurements_and_rewards(self):
        env = CircuitEnv()
        for name in env.dict_targets:
            for bad in [np.nan, np.inf, -np.inf, None]:
                with self.subTest(spec=name, value=bad):
                    specs = dict(env.dict_targets, **{name: bad})
                    with patch.object(env.simulation_engine, 'create_new_netlist', return_value='mock.cir'), \
                         patch.object(env.simulation_engine, 'simulate', return_value=0), \
                         patch.object(env.simulation_engine, 'measure_metrics', return_value=specs):
                        reset_ob = env.reset()
                        ob, reward, done, info = env.step(np.zeros(env.n_actions))
                    self.assertTrue(np.isfinite(reset_ob).all())
                    self.assertTrue(np.isfinite(ob).all())
                    self.assertAlmostEqual(reward, -5.1)
                    self.assertFalse(info['hard_satisfied'])
                    self.assertTrue(info['invalid_simulation'])
                    self.assertIn(name, info['simulation_error'])
                    norm = dict.fromkeys(env.dict_targets, 0.0)
                    norm[name] = bad
                    direct_reward, success = env.reward_computation(norm)
                    self.assertAlmostEqual(direct_reward, -5.1)
                    self.assertFalse(success)

    def test_failed_simulation_and_counter(self):
        # An invalid simulation must stay unsuccessful even with a relaxed threshold.
        env = CircuitEnv(success_threshold=-10.)
        with patch.object(env.simulation_engine, 'create_new_netlist', return_value='mock.cir'), \
             patch.object(env.simulation_engine, 'simulate', return_value=1) as simulate:
            initial = env.reset()
            self.assertEqual((env.env_steps, env.episode_steps, env.simulation_count), (0, 0, 1))
            ob, reward, done, info = env.step(np.zeros(env.n_actions))
            self.assertEqual(simulate.call_count, 2)
        self.assertEqual((env.env_steps, env.episode_steps, env.simulation_count), (1, 1, 2))
        self.assertTrue(np.isfinite(initial).all() and np.isfinite(ob).all())
        self.assertAlmostEqual(reward, -5.1)
        self.assertTrue(info['invalid_simulation'])
        self.assertFalse(info['hard_satisfied'])
        self.assertIn('ngspice simulation failed', info['simulation_error'])

    def test_missing_key_and_singular_normalization(self):
        env = CircuitEnv()
        for specs in [{}, dict(env.dict_targets, phm=-env.dict_targets['phm'])]:
            with patch.object(env, 'simulate', return_value=specs):
                ob = env.reset()
                self.assertTrue(np.isfinite(ob).all())
                self.assertIsNotNone(env.simulation_error)


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
