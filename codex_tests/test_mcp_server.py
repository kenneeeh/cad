"""Current MCP tool checks. All simulator calls are mocked."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'llm'))
os.environ['CAD_RUNS_DIR'] = str(HERE / 'artifacts/llm_simple')
import mcp_server as server
from candidates import CandidateArchive

PARAMETERS = json.loads((REPO / 'llm/initial_design.json').read_text())


class TestSimulatorTool(unittest.TestCase):
    def setUp(self):
        server.env.counter = 0
        root = HERE / 'artifacts/llm_simple'
        root.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix='tools_', dir=root))
        self.archive = CandidateArchive(self.folder / 'candidates.jsonl', server.context['problem_id'])
        patch.object(server, 'archive', self.archive).start()
        self.engine = patch.object(server.env.simulation_engine, 'simulate', return_value=0).start()
        self.measure = patch.object(server.env.simulation_engine, 'measure_metrics', return_value=dict(server.env.dict_targets)).start()
        self.addCleanup(patch.stopall)

    def test_valid_evaluation_uses_existing_reward_and_stores_hypothesis(self):
        result = server.simulate_design(PARAMETERS, 'Measure the initial design.')
        self.assertTrue(result['success'], result)
        expected = server.env.reward_computation(server.env.normalize_specs(result['specs']))
        self.assertEqual((result['reward'], result['hard_satisfied']), expected)
        record = self.archive.get(result['design_id'])
        self.assertEqual(record['parameters'], PARAMETERS)
        self.assertEqual(record['hypothesis'], 'Measure the initial design.')
        self.assertTrue(record['metadata']['completed'])
        self.assertEqual(result['simulation_count'], 1)
        audit = json.loads((server.RUN / 'calls.jsonl').read_text().splitlines()[-1])
        self.assertEqual(audit['arguments']['hypothesis'], 'Measure the initial design.')
        self.assertEqual(audit['result']['specs'], record['specs'])
        self.assertEqual(audit['event'], 'tool_call')

    def test_archive_clock_includes_model_delay_and_preserves_origins(self):
        import candidates
        with patch.dict(os.environ, {'CAD_EXPERIMENT_START': '100'}), \
             patch.object(candidates, 'perf_counter', return_value=125.):
            result = server.simulate_design(PARAMETERS, 'One short measured hypothesis.')
        record = self.archive.get(result['design_id'])
        self.assertEqual(record['metadata']['elapsed_s'], 25.)
        self.assertEqual(record['metadata']['cumulative_simulation_count'], 1)
        self.assertEqual(record['metadata']['origin'], 'LLM')
        for phase, origin in (('warmup', 'random_warmup'), ('policy', 'TD3')):
            record = self.archive.add(PARAMETERS, server.adapter.assess(dict(server.env.dict_targets)),
                'TD3', 'mock', {'phase': phase, 'simulation_count': 3, 'cumulative_simulation_count': 7})
            self.assertEqual(record['metadata']['origin'], origin)
            self.assertEqual(record['metadata']['cumulative_simulation_count'], 7)

    def test_invalid_values_do_not_simulate(self):
        for changes in ({'wp1': 1.6e-6}, {'mp1': 26.}, {'mp1': True}, {'cap': float('nan')}, {'bogus': 1.}):
            with self.subTest(changes=changes):
                self.assertFalse(server.simulate_design(dict(PARAMETERS, **changes))['success'])
        self.assertFalse(server.simulate_design({})['success'])
        self.engine.assert_not_called()
        self.assertEqual(server.env.counter, 0)

    def test_backend_schedule_guard_and_reset_measurement_audit(self):
        from llm.td3_candidates import record_reset_evaluation
        protocol = {'initial_design': PARAMETERS, 'plan': [
            {'tool': 'llm', 'steps': 1, 'label': 'initial_design'},
            {'tool': 'warmup', 'steps': 1}, {'tool': 'train', 'steps': 2}]}
        with patch.object(server, 'PROTOCOL', protocol), patch.object(server, 'RUN', self.folder), \
             patch.object(server.env.simulation_engine, 'audit_path', self.folder/'calls.jsonl'):
            self.assertTrue(server.train(2)['protocol_rejected'])
            self.assertTrue(server.simulate_design(dict(PARAMETERS, res=6100.))['protocol_rejected'])
            self.engine.assert_not_called()
            self.assertTrue(server.simulate_design(PARAMETERS)['success'])
            self.assertEqual(server.protocol_state()['next_phase']['tool'], 'warmup')
            self.assertTrue(server.train(2)['protocol_rejected'])
            with patch.object(server.td3_session, 'run', return_value={'success': True, 'steps': 1}):
                self.assertTrue(server.warmup(1)['success'])
            self.assertTrue(server.train(3)['protocol_rejected'])
            self.assertIsNone(server.td3_session.agent)
            self.assertEqual(self.engine.call_count, 1)
        server.env.reset()  # Mocked measurements only; no learner or simulator process.
        record_reset_evaluation(server.env)
        log = [json.loads(line) for line in Path(server.env.simulation_engine.audit_path).read_text().splitlines()]
        reset = [e for e in log if e.get('event') == 'reset_measurement'][-1]
        self.assertEqual(reset['specs'], server.env.real_specs)
        self.assertEqual(reset['simulation_index'], server.env.counter)
        self.assertTrue(reset['design_id'].startswith('reset_'))

    def test_shared_budget_includes_failed_attempts(self):
        with patch.object(server, 'MAX_SIMULATIONS', 2):
            base = server.simulate_design(PARAMETERS)
            self.engine.return_value = 1
            failed = server.evaluate_candidate(base['design_id'], {'res': 6100.})
            self.assertFalse(failed['success'])
            self.assertEqual(failed['simulation_count'], 2)
            self.assertTrue(server.simulate_design(PARAMETERS)['cached'])
            self.assertIn('budget', server.evaluate_candidate(base['design_id'], {'res': 6200.})['error'])
            self.assertEqual(self.engine.call_count, 2)
            self.assertEqual(len(self.archive.records()), 1)

    def test_base_changes_are_absolute_and_original_is_unchanged(self):
        base = server.simulate_design(PARAMETERS)
        before = self.archive.get(base['design_id'])
        child = server.evaluate_candidate(base['design_id'], {'res': 6100.}, 'Test one grid step.')
        self.assertTrue(child['success'])
        self.assertEqual(child['changes'], {'res': {'from': 6000., 'to': 6100.}})
        self.assertEqual(self.archive.get(child['design_id'])['parent_id'], base['design_id'])
        self.assertEqual(self.archive.get(child['design_id'])['parameters']['res'], 6100.)
        self.assertEqual(self.archive.get(base['design_id']), before)
        for design_id, changes in ((base['design_id'], {}), (base['design_id'], {'res': 6150.}), ('missing', {'res': 6100.})):
            calls = self.engine.call_count
            self.assertFalse(server.evaluate_candidate(design_id, changes)['success'])
            self.assertEqual(self.engine.call_count, calls)

    def test_distinct_ranking_persistence_and_compact_retrieval(self):
        self.measure.return_value = dict(server.env.dict_targets, gain=190.)
        server.simulate_design(PARAMETERS)
        self.measure.return_value = dict(server.env.dict_targets)
        best = server.simulate_design(dict(PARAMETERS, res=6100.))
        server.simulate_design(dict(PARAMETERS, res=6200.))
        server.simulate_design(dict(PARAMETERS, res=6200.))  # Reuse, no extra archive row.
        ranked = server.get_candidates()['candidates']
        self.assertEqual(len(ranked), 3)
        self.assertNotIn('parameters', ranked[0])
        reloaded = CandidateArchive(self.archive.path, self.archive.problem_id)
        self.assertEqual(len(reloaded.records()), 3)
        self.assertEqual(reloaded.get(best['design_id'])['parameters'], dict(PARAMETERS, res=6100.))
        self.assertEqual(ranked[0]['reward'], .3)

    def test_nonfinite_measurements_and_zero_fallback(self):
        self.measure.return_value = dict(server.env.dict_targets, gain=float('nan'))
        bad = server.simulate_design(PARAMETERS)
        self.assertFalse(bad['success'])
        self.assertNotIn('reward', bad)
        self.measure.return_value = dict(server.env.dict_targets, phm=0., ugbw=0.)
        result = server.simulate_design(PARAMETERS)
        self.assertTrue(result['success'])
        self.assertFalse(result['hard_satisfied'])
        self.assertEqual(result['violated_constraints'], ['phm', 'ugbw'])
        self.assertEqual(result['reward'], -2.)

    def test_problem_is_read_only_and_uses_yaml_values(self):
        problem = server.get_problem()
        self.assertEqual(problem['parameters']['cap'], [*server.env.dict_params['cap'], 'F'])
        self.assertEqual(problem['hard_targets']['noise'], ['<=', server.env.dict_targets['noise'], 'V RMS'])
        self.assertEqual(problem['simulation_count'], 0)
        self.engine.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
