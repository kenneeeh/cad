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
        self.assertNotIn('specs', audit['result'])  # Successful measurements are stored once.

    def test_invalid_values_do_not_simulate(self):
        for changes in ({'wp1': 1.6e-6}, {'mp1': 26.}, {'mp1': True}, {'cap': float('nan')}, {'bogus': 1.}):
            with self.subTest(changes=changes):
                self.assertFalse(server.simulate_design(dict(PARAMETERS, **changes))['success'])
        self.assertFalse(server.simulate_design({})['success'])
        self.engine.assert_not_called()
        self.assertEqual(server.env.counter, 0)

    def test_shared_budget_includes_failed_attempts(self):
        with patch.object(server, 'MAX_SIMULATIONS', 2):
            base = server.simulate_design(PARAMETERS)
            self.engine.return_value = 1
            failed = server.evaluate_candidate(base['design_id'], {'res': 6100.})
            self.assertFalse(failed['success'])
            self.assertEqual(failed['simulation_count'], 2)
            self.assertIn('budget', server.simulate_design(PARAMETERS)['error'])
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
        best = server.simulate_design(PARAMETERS)
        server.simulate_design(dict(PARAMETERS, res=6100.))
        ranked = server.get_candidates()['candidates']
        self.assertEqual(len(ranked), 2)
        self.assertNotIn('parameters', ranked[0])
        reloaded = CandidateArchive(self.archive.path, self.archive.problem_id)
        self.assertEqual(len(reloaded.records()), 3)
        self.assertEqual(reloaded.get(best['design_id'])['parameters'], PARAMETERS)
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
