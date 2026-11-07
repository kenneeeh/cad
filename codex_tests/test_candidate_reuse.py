"""Measured-design reuse through real validation/reward code, mocked ngspice only."""
import json
import unittest
from unittest.mock import patch

from codex_tests import test_mcp_server as fixtures
from candidates import CandidateArchive

server = fixtures.server
PARAMETERS = fixtures.PARAMETERS


class TestCandidateReuse(unittest.TestCase):
    def setUp(self):
        fixtures.TestSimulatorTool.setUp(self)

    def test_duplicate_grid_vector_persists_without_new_measurement_or_reward(self):
        first = server.simulate_design(dict(PARAMETERS, res=6100.))
        original = self.archive.get(first['design_id'])
        self.measure.return_value = dict(server.env.dict_targets, gain=1.)
        reloaded = CandidateArchive(self.archive.path, self.archive.problem_id)
        with patch.object(server, 'archive', reloaded), patch.object(server, 'MAX_SIMULATIONS', 1):
            cached = server.simulate_design(dict(PARAMETERS, res=6100. + 1e-10))
        self.assertTrue(cached['cached'])
        self.assertEqual(cached['design_id'], first['design_id'])
        self.assertEqual(cached['specs'], first['specs'])
        self.assertEqual(cached['reward'], first['reward'])
        self.assertEqual(cached['hard_satisfied'], first['hard_satisfied'])
        self.assertEqual(cached['ngspice_attempts'], 0)
        self.assertEqual(cached['simulation_count'], 1)
        self.assertEqual(cached['measurement_simulation_count'], 1)
        self.assertEqual(cached['remaining'], 0)
        self.assertEqual(reloaded.records(), [original])
        self.assertEqual(self.engine.call_count, 1)
        self.assertEqual(self.measure.call_count, 1)

    def test_cached_result_keeps_original_parent_and_reports_request_parent(self):
        first = server.simulate_design(PARAMETERS)
        child = server.evaluate_candidate(first['design_id'], {'res': 6100.})
        cached = server.evaluate_candidate(child['design_id'], {'res': 6000.})
        self.assertEqual(cached['design_id'], first['design_id'])
        self.assertIsNone(cached['parent_id'])
        self.assertEqual(cached['requested_parent_id'], child['design_id'])
        self.assertEqual(self.archive.get(child['design_id'])['parent_id'], first['design_id'])
        self.assertEqual(len(self.archive.records()), 2)
        self.assertEqual(self.engine.call_count, 2)

    def test_noop_rejection_including_equivalent_grid_values(self):
        first = server.simulate_design(PARAMETERS)
        for change in ({}, {'res': 6000.}, {'res': 6000. + 1e-10}):
            result = server.evaluate_candidate(first['design_id'], change)
            self.assertFalse(result['success'])
            self.assertIn('change', result['error'])
        self.assertEqual(self.engine.call_count, 1)
        self.assertEqual(server.total_attempts(), 1)

    def test_probe_duplicates_do_not_consume_protocol_or_simulation_budget(self):
        protocol = {'plan': [{'tool': 'llm', 'steps': 3}], 'initial_design': PARAMETERS}
        with patch.object(server, 'PROTOCOL', protocol), patch.object(server, 'RUN', self.folder), \
                patch.object(server, 'MAX_SIMULATIONS', 3):
            first = server.simulate_design(PARAMETERS)
            result = server.probe_parameters(first['design_id'],
                [{'res': 6100.}, {'res': 6100.}, {'res': 6200.}])
            self.assertTrue(result['success'], result)
            self.assertEqual(result['probes'][0]['design_id'], result['probes'][1]['design_id'])
            self.assertTrue(result['probes'][1]['cached'])
            self.assertEqual(result['simulation_count'], 3)
            self.assertTrue(server.protocol_state()['complete'])
            cached = server.probe_parameters(first['design_id'], [{'res': 6100.}, {'res': 6200.}])
            self.assertTrue(all(p['cached'] for p in cached['probes']))
            self.assertTrue(server.protocol_state()['complete'])
            logs = [json.loads(line) for line in (self.folder / 'calls.jsonl').read_text().splitlines()]
            hits = [e for e in logs if e.get('result', {}).get('cached')]
            self.assertEqual(len(hits), 3)
            self.assertTrue(all(e['ngspice_attempts'] == 0 for e in hits))
        self.assertEqual(self.engine.call_count, 3)
        self.assertEqual(len(self.archive.records()), 3)

    def test_failed_attempt_is_charged_and_never_cached(self):
        self.engine.return_value = 1
        with patch.object(server, 'MAX_SIMULATIONS', 1):
            failed = server.simulate_design(PARAMETERS)
            self.assertFalse(failed['success'])
            self.assertEqual(failed['simulation_count'], 1)
            blocked = server.simulate_design(PARAMETERS)
            self.assertIn('budget', blocked['error'])
        self.assertEqual(self.engine.call_count, 1)
        self.assertEqual(self.archive.records(), [])

    def test_setup_and_fixture_isolation(self):
        first = server.simulate_design(PARAMETERS)
        record = self.archive.get(first['design_id'])
        key = server.adapter.parameter_key(PARAMETERS)
        setup = server.adapter.measurement_setup()
        self.assertIsNone(self.archive.find_measured(key, 'different-setup'))
        with patch.dict(server.env.pvt_corner, temp=85):
            self.assertNotEqual(server.adapter.measurement_setup(), setup)
            self.assertFalse(server.simulate_design(PARAMETERS)['cached'])
        other = CandidateArchive(self.folder / 'other.jsonl', 'different-problem')
        other.path = self.archive.path
        self.assertIsNone(other.find_measured(key, setup))
        record['metadata']['fixture'] = True
        self.archive.path.write_text(json.dumps(record) + '\n')
        self.assertIsNone(self.archive.find_measured(key, setup))
        del record['metadata']['fixture']
        del record['metadata']['measurement_setup']
        self.archive.path.write_text(json.dumps(record) + '\n')
        self.assertIsNone(self.archive.find_measured(key, setup))


if __name__ == '__main__':
    unittest.main(verbosity=2)
