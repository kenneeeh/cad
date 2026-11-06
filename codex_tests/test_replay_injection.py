"""Small replay insertion tests: actual ReplayBuffer, mocked simulator, no training."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
from circuit_env import CircuitEnv
from td3 import ReplayBuffer
from llm.circuit_adapter import CircuitAdapter
from llm.candidates import CandidateArchive
from llm.replay_injection import physical_to_action, inject_llm_candidates
PARAMETERS = json.loads((REPO / 'llm/initial_design.json').read_text())


class TestReplayInjection(unittest.TestCase):
    def setUp(self):
        root = HERE / 'artifacts/llm_simple'
        root.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix='replay_', dir=root))
        old_cwd = Path.cwd()
        os.chdir(REPO)
        self.addCleanup(os.chdir, old_cwd)
        self.env = CircuitEnv(run_id='MOCK-ONLY')
        self.env.simulation_engine.output_netlists_folder = str(self.folder / 'netlists')
        self.env.simulation_engine.output_files_folder = str(self.folder / 'outputs')
        self.engine = patch.object(self.env.simulation_engine, 'simulate', return_value=0).start()
        patch.object(self.env.simulation_engine, 'measure_metrics', return_value=dict(self.env.dict_targets)).start()
        action = physical_to_action(PARAMETERS, self.env)
        patch.object(self.env.action_space, 'sample', return_value=action).start()
        self.addCleanup(patch.stopall)
        self.obs = self.env.reset()
        self.adapter = CircuitAdapter(self.env, REPO)
        self.archive = CandidateArchive(self.folder / 'candidates.jsonl', self.adapter.context()['problem_id'])
        self.buffer = ReplayBuffer(7, 20, max_size=8)
        self.seen = set()

    def candidate(self):
        return self.archive.add(dict(PARAMETERS, res=6100.),
            self.adapter.assess(dict(self.env.dict_targets, gain=220., current=1.2e-4)),
            'LLM', 'MOCK-LLM', {'completed': True, 'simulator': 'ngspice', 'simulation_id': 'MOCK-evaluated'})

    def inject(self, **kwargs):
        return inject_llm_candidates(self.archive.path, self.buffer, self.env, self.seen, **kwargs)

    def test_action_reconstructs_endpoints_and_physical_grid(self):
        for end in (0, 1):
            parameters = {name: bounds[end] for name, bounds in self.env.dict_params.items()}
            action = physical_to_action(parameters, self.env)
            self.assertEqual(action.shape, (20,))
            self.assertEqual(action.dtype, np.float32)
            actual = self.env.action_refine(action)
            for name, (_, _, step) in self.env.dict_params.items():
                self.assertAlmostEqual((actual[name]-parameters[name])/step, 0., places=7)
        with self.assertRaises(ValueError):
            physical_to_action(dict(PARAMETERS, res=6150.), self.env)

    def test_transition_uses_current_state_and_keeps_episode_unchanged(self):
        record = self.candidate()
        fields = ('counter', 'episode_steps', 'env_steps', 'param_values', 'cur_norm_specs', 'real_specs', 'reward_history')
        before = deepcopy({n: getattr(self.env, n) for n in fields})
        calls = self.engine.call_count
        result = self.inject()
        self.assertEqual(result['injected'], 1)
        np.testing.assert_array_equal(self.buffer.state[0], self.obs)
        expected = self.env.normalize_specs(record['specs'])
        np.testing.assert_array_equal(self.buffer.next_state[0],
                                     np.array([expected[n] for n in self.env.dict_targets], dtype=np.float32))
        self.assertAlmostEqual(self.buffer.reward[0, 0], record['reward'])
        self.assertEqual(self.buffer.not_done[0, 0], 1.)
        self.assertEqual(self.engine.call_count, calls)
        self.assertEqual({n: getattr(self.env, n) for n in fields}, before)
        self.assertEqual(self.buffer.sample(1)[2].shape[1], 7)

    def test_terminal_flag_matches_environment_time_limit(self):
        self.candidate()
        self.env.episode_steps = self.env.max_steps_per_episode-1
        self.inject()
        self.assertEqual(self.buffer.not_done[0, 0], 0.)
        self.assertEqual(self.env.episode_steps, self.env.max_steps_per_episode-1)
        self.env.episode_steps = self.env.max_steps_per_episode
        with self.assertRaises(ValueError):
            self.inject()

    def test_duplicate_ids_are_not_inserted_again(self):
        record = self.candidate()
        self.assertEqual(self.inject(limit=1)['candidate_ids'], [record['design_id']])
        again = self.inject()
        self.assertEqual(again['skipped_duplicates'], 1)
        self.assertEqual(again['injected'], 0)
        self.assertEqual(self.buffer.size, 1)

    def test_rejects_unmeasured_inconsistent_and_old_designs(self):
        record = self.candidate()
        bad = [dict(record, problem_id='old-slew-definition'), dict(record, parameters=dict(PARAMETERS, res=6150.)),
               dict(record, reward=999.), dict(record, metadata={'completed': False}),
               dict(record, metadata={**record['metadata'], 'fixture': True})]
        self.archive.path.write_text(''.join(json.dumps(r)+'\n' for r in bad))
        result = self.inject()
        self.assertEqual(len(result['rejected']), len(bad))
        self.assertEqual(self.buffer.size, 0)
        self.assertEqual(self.seen, set())

    def test_requires_a_current_measured_state(self):
        self.candidate()
        self.env.cur_norm_specs['gain'] = .5
        with self.assertRaises(ValueError):
            self.inject()
        self.assertEqual(self.buffer.size, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
