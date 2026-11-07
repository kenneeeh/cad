"""Protocol/selection regression and independent published-log checks; no simulation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'llm'))
import run_experiment as runner
import deliverables


def candidate(index, feasible, reward, source='LLM'):
    return {'design_id': f'design_{index}', 'parent_id': None, 'problem_id': 'test',
            'source': source, 'parameters': {'w': 1}, 'specs': {'area': 1., 'current': 1.},
            'reward': reward, 'hard_satisfied': feasible,
            'metadata': {'cumulative_simulation_count': index, 'elapsed_s': float(index),
                         'origin': 'LLM' if source == 'LLM' else 'TD3'}}


class TestLLMLedProtocol(unittest.TestCase):
    def setUp(self):
        self.plan = runner.make_plan('llm_led', 30, 120, 130)

    def test_empty_and_partial_progress_are_not_completion(self):
        state = runner.check_completion(self.plan, [])
        self.assertFalse(state['complete'])
        self.assertTrue(state['within_resource_ceilings'])
        final = runner.finish_llm_led(state, {'status': 'SUCCESS'}, 0, 300, [])
        self.assertEqual(final['status'], 'voluntary_early_stop')
        self.assertFalse(final['complete'])
        self.assertFalse(final['td3_training_used'])

    def test_feasible_stagnation_ignores_infeasible_high_rewards_and_resets(self):
        records = [candidate(1, True, .4)] + [candidate(i, False, 5.) for i in range(3, 11)]
        events = [{'event': 'reset_measurement', 'simulation_index': 2, 'reward': 10., 'hard_satisfied': True}]
        final = runner.finish_llm_led(runner.check_completion(self.plan, []),
            {'status': 'SUCCESS'}, 10, 300, records, events)
        self.assertEqual(final['status'], 'completed_optimization')
        self.assertEqual(final['stop_reason'], 'feasible_stagnation')
        self.assertEqual(final['non_improving_candidate_streak'], 8)
        self.assertTrue(final['complete'])
        early = runner.finish_llm_led(runner.check_completion(self.plan, []),
            {'status': 'SUCCESS'}, 9, 300, records[:-1], events)
        self.assertEqual(early['status'], 'voluntary_early_stop')

    def test_resource_and_execution_outcomes_are_distinct(self):
        progress = runner.check_completion(self.plan, [])
        exhausted = runner.finish_llm_led(progress, {'status': 'SUCCESS'}, 300, 300, [])
        self.assertEqual(exhausted['status'], 'resource_exhaustion')
        failed = runner.finish_llm_led(progress, {'status': 'ERROR'}, 1, 300, [], exit_code=1)
        self.assertEqual(failed['status'], 'execution_failure')
        self.assertFalse(failed['complete'])
        calls = [{'tool': 'evaluate_candidate', 'ngspice_attempts': 131, 'result': {'success': True}}]
        exceeded = runner.check_completion(self.plan, calls)
        self.assertFalse(exceeded['within_resource_ceilings'])
        self.assertEqual(runner.finish_llm_led(exceeded, {'status': 'SUCCESS'}, 131, 300, [])['status'],
                         'execution_failure')

    def test_missing_process_indices_cannot_validate_stagnation(self):
        records = [candidate(i, True, .4) for i in range(1, 10)]
        del records[0]['metadata']['cumulative_simulation_count']
        final = runner.finish_llm_led(runner.check_completion(self.plan, []),
                                     {'status': 'SUCCESS'}, 9, 300, records)
        self.assertFalse(final['stagnation_order_verified'])
        self.assertFalse(final['complete'])

    def test_failed_simulation_is_charged_and_blocks_false_completion(self):
        calls = [{'tool': 'evaluate_candidate', 'ngspice_attempts': 1,
                  'result': {'success': False, 'error': 'simulator failed'}}]
        state = runner.check_completion(self.plan, calls)
        self.assertEqual(state['counts']['llm'], 1)
        self.assertTrue(state['errors'])

    def test_method_ceiling_exhaustion_and_actual_updates(self):
        plan = runner.make_plan('llm_led', 0, 1, 1)
        events = [{'event': 'tool_call', 'tool': 'train', 'ngspice_attempts': 2,
                   'result': {'success': True, 'steps': 1, 'critic_updates': 1}},
                  {'event': 'tool_call', 'tool': 'simulate_design', 'ngspice_attempts': 1,
                   'result': {'success': True}}]
        result = runner.finish_llm_led(runner.check_completion(plan, events),
                                      {'status': 'SUCCESS'}, 3, 300, [], events)
        self.assertEqual(result['status'], 'resource_exhaustion')
        self.assertEqual(result['stop_reason'], 'resource_ceiling_exhausted')
        self.assertTrue(result['td3_training_used'])
        self.assertTrue(result['phases'][0]['complete'])

    def test_feasible_selection_and_source_use_actual_process_indices(self):
        records = [candidate(1, False, 9.), candidate(4, True, .4, 'TD3'), candidate(7, True, .5)]
        result = deliverables.summarize_measurements(records, [], 8)
        self.assertEqual(result['best_measured_reward'], 9.)
        self.assertEqual(result['best_feasible_fom'], .5)
        self.assertEqual(result['first_feasible_simulation'], 4)
        self.assertEqual(result['best_feasible_source'], 'LLM')
        self.assertIsNone(result['efficiency']['curve'][0]['best_feasible_reward'])
        self.assertEqual([p['simulation_index'] for p in result['efficiency']['new_best_feasible']], [4, 7])
        self.assertFalse(result['hybrid_training_executed'])
        none = deliverables.summarize_measurements([records[0]], [], 1)
        self.assertIsNone(none['best_feasible_fom'])

    def test_guards_bound_td3_and_require_measured_reason(self):
        from codex_tests import test_mcp_server as fixtures
        server = fixtures.server
        state = runner.check_completion(self.plan, [])
        with patch.object(server, 'protocol_state', return_value=state), \
                patch.object(server.archive, 'records', return_value=[{'design_id': 'design_base'}]):
            self.assertIsNone(server.protocol_guard('train', 30, reason='refine design_base'))
            self.assertTrue(server.protocol_guard('train', 41, reason='design_base')['protocol_rejected'])
            self.assertTrue(server.protocol_guard('train', 30)['protocol_rejected'])
            self.assertIsNone(server.protocol_guard('warmup', 30))
            state['counts']['warmup'] = 1
            self.assertTrue(server.protocol_guard('warmup', 1)['protocol_rejected'])


class TestPublishedLLMLedRun(unittest.TestCase):
    def test_published_specs_match_existing_reward_and_feasibility(self):
        from codex_tests import test_mcp_server as fixtures
        folder = REPO / 'results/llm_led_seed123456'
        for line in (folder / 'candidates.jsonl').read_text().splitlines():
            record = json.loads(line)
            fixtures.server.adapter.validate_parameters(record['parameters'])
            assessed = fixtures.server.adapter.assess(record['specs'])
            self.assertEqual(assessed['hard_satisfied'], record['hard_satisfied'])
            self.assertAlmostEqual(assessed['reward'], record['reward'], places=9)

    def test_ported_seed_configs_change_only_seed(self):
        default = json.loads((REPO / 'output_figs/2026-11-05--18-35-18/params.json').read_text())
        for seed in (1, 2):
            config = json.loads((REPO / f'llm/configs/td3_seed{seed}.json').read_text())
            self.assertEqual(config, {**default, 'seed': seed})

    def test_independent_reconstruction_and_parent_206_to_218(self):
        folder = REPO / 'results/llm_led_seed123456'
        records = [json.loads(line) for line in (folder / 'candidates.jsonl').read_text().splitlines()]
        events = deliverables.read_events(folder)
        attempts = [e for e in events if e.get('event') == 'simulation_attempt']
        self.assertEqual([e['simulation_index'] for e in attempts], list(range(1, 229)))
        measured = deliverables.summarize_measurements(records, events)
        self.assertEqual(measured['candidate_counts_by_phase'], {'LLM': 63, 'warmup': 30, 'policy': 120})
        self.assertEqual(measured['first_feasible_simulation'], 216)
        self.assertEqual(measured['best_feasible_simulation'], 218)
        self.assertAlmostEqual(measured['best_feasible_fom'], .6837858803353272, places=14)
        self.assertEqual(measured['successful_td3_training_updates'], 120)
        self.assertEqual(measured['td3_actor_updates'], 60)
        reviewed = deliverables.verify_saved_run(folder, records, events, measured)
        self.assertTrue(all(reviewed['published_numerical_agreement'].values()))
        self.assertEqual(reviewed['recorded_td3_reset_measurements'], 15)
        self.assertEqual(reviewed['best_parent']['metadata']['cumulative_simulation_count'], 206)
        self.assertEqual(reviewed['best_parent']['source'], 'TD3')
        self.assertEqual(reviewed['best_changes_from_parent'], {'wn4': {'from': 2.75e-6, 'to': 3e-6}})
        self.assertEqual(reviewed['protocol_review']['non_improving_candidate_streak'], 10)
        self.assertEqual(reviewed['protocol_review']['stop_reason'], 'feasible_stagnation')

    def test_offline_exports_do_not_modify_the_published_run(self):
        folder = REPO / 'results/llm_led_seed123456'
        before = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        output_root = REPO / 'codex_tests/artifacts/llm_led'
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temporary:
            output = Path(temporary)
            result = deliverables.write_deliverables(folder / 'candidates.jsonl', folder, folder.name,
                                                      output_dir=output)
            self.assertEqual(result['actual_ngspice_attempts'], 228)
            for name in ['max_reward.png', 'best_feasible_fom.png', 'pareto.png', 'Solutions/solutions.csv']:
                self.assertTrue((output / name).is_file(), name)
            self.assertEqual(len(list((output / 'Solutions').glob('*.cir'))), 2)
        self.assertEqual(before, {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main(verbosity=2)
