"""Offline cost curves and mocked process timing; no simulation or learning."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from llm.efficiency import summarize_efficiency, compare_efficiency
from llm import efficiency
from ngspice_interface.ngspice_wrapper import NgspiceWrapper


def candidate(index, reward, feasible=True, elapsed=None):
    return {'design_id': f'd{index}', 'source': 'TD3', 'reward': reward,
            'hard_satisfied': feasible, 'metadata': {'origin': 'TD3', 'phase': 'policy',
            'cumulative_simulation_count': index, 'elapsed_s': elapsed if elapsed is not None else index * 2.}}


class TestEfficiency(unittest.TestCase):
    def test_offline_comparison_cli_and_uncharged_external_data_guard(self):
        folder = REPO / 'codex_tests/artifacts/efficiency'
        folder.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=folder))
        for name, n, overhead in (('baseline', 10, 5), ('hybrid', 6, 17)):
            run = root / name
            (run / 'session_test').mkdir(parents=True)
            record = candidate(n, .6, elapsed=n+overhead)
            (run / 'candidates.jsonl').write_text(json.dumps(record)+'\n')
            (run / 'summary.json').write_text(json.dumps({'evaluated_design_ids': [record['design_id']],
                'ngspice_attempts': n, 'problem_id': 'same-setup', 'incomplete': False}))
            (run / 'manifest.json').write_text(json.dumps({'td3_settings': {'seed': 1},
                'plan': [{'tool': 'train' if name == 'baseline' else 'llm'}],
                'sha256': {'circuit_env.py': 'same-source'}}))
            events = [{'event': 'simulation_attempt', 'simulation_index': i, 'initiator': 'train',
                       'simulator_execution_s': 1.} for i in range(1, n+1)]
            (run / 'session_test/calls.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        output = root / 'comparison.json'
        argv = ['efficiency.py', str(root/'hybrid'), '--baseline', str(root/'baseline'),
                '--thresholds', '.5', '--output', str(output)]
        with patch.object(sys, 'argv', argv):
            efficiency.main()
        report = json.loads(output.read_text())
        self.assertEqual(report['comparisons'][0]['threshold_comparison'][0]['break_even_simulator_s'], 3.)
        with (root/'hybrid/candidates.jsonl').open('a') as target:
            target.write(json.dumps(candidate(99, .8))+'\n')
        with patch.object(sys, 'argv', argv):
            efficiency.main()
        report = json.loads(output.read_text())
        self.assertIsNone(report['comparisons'][0]['threshold_comparison'][0]['break_even_simulator_s'])
        self.assertEqual(report['runs'][0]['external_candidate_ids'], ['d99'])

    def test_counts_include_unarchived_resets_failures_and_all_sources(self):
        events = [{'event': 'simulation_attempt', 'simulation_index': i, 'initiator': phase,
                   'simulator_execution_s': 1., 'returncode': 1 if i == 3 else 0}
                  for i, phase in enumerate(('warmup', 'warmup', 'LLM', 'train', 'train'), 1)]
        report = summarize_efficiency([candidate(2, .2), candidate(4, .9, False), candidate(5, .6)],
                                      events, 5, (.2, .5, .8))
        self.assertEqual(report['actual_ngspice_attempts'], 5)
        self.assertEqual(report['attempts_by_initiating_phase'], {'warmup': 2, 'LLM': 1, 'train': 2})
        self.assertEqual([m['simulation_index'] for m in report['new_best_feasible']], [2, 5])
        self.assertEqual(report['curve'][1]['best_feasible_reward'], .2)
        self.assertEqual(report['thresholds'][1]['first_hit']['simulation_index'], 5)
        self.assertIsNone(report['thresholds'][2]['first_hit'])
        self.assertEqual(report['timing']['total_simulator_execution_s'], 5.)
        self.assertIsNone(report['timing']['pure_llm_inference_s'])

    def test_missing_timing_and_no_feasible_design_are_unknown(self):
        report = summarize_efficiency([candidate(3, 1., False)], [], 4, (.5,))
        self.assertIsNone(report['curve'][0]['best_feasible_reward'])
        self.assertIsNone(report['thresholds'][0]['first_hit'])
        self.assertFalse(report['attempt_log_complete'])
        self.assertIsNone(report['timing']['total_simulator_execution_s'])
        self.assertTrue(report['warnings'])

    def test_hypothetical_break_even_at_same_threshold(self):
        def report(n, overhead):
            events = [{'event': 'simulation_attempt', 'simulation_index': i,
                       'initiator': 'train', 'simulator_execution_s': 1.} for i in range(1, n + 1)]
            return summarize_efficiency([candidate(n, .6, elapsed=n+overhead)], events, n, (.5, .8))
        baseline, hybrid = report(10, 5), report(6, 17)
        comparison = compare_efficiency(baseline, hybrid)
        self.assertEqual(comparison[0]['simulations_saved'], 4)
        self.assertEqual(comparison[0]['break_even_simulator_s'], 3.)  # (17-5)/(10-6).
        self.assertTrue(comparison[0]['hypothetical'])
        self.assertIsNone(comparison[1]['break_even_simulator_s'])
        self.assertIsNone(compare_efficiency(baseline, hybrid, False)[0]['break_even_simulator_s'])
        self.assertIsNone(compare_efficiency(hybrid, baseline)[0]['break_even_simulator_s'])
        historical = summarize_efficiency([candidate(6, .6)], [], 6, (.5,))
        self.assertIsNone(compare_efficiency(baseline, historical)[0]['break_even_simulator_s'])

    def test_duplicate_or_missing_attempts_prevent_timing_claims(self):
        event = {'event': 'simulation_attempt', 'simulation_index': 1,
                 'initiator': 'LLM', 'simulator_execution_s': 1.}
        for events in ([event], [event, event]):
            report = summarize_efficiency([candidate(2, .6)], events, 2, (.5,))
            self.assertFalse(report['attempt_log_complete'])
            self.assertIsNone(report['thresholds'][0]['first_hit']['non_simulator_elapsed_s'])

    def test_wrapper_logs_success_failure_and_launch_error_without_real_processes(self):
        folder = REPO / 'codex_tests/artifacts/efficiency'
        folder.mkdir(parents=True, exist_ok=True)
        audit = Path(tempfile.mkdtemp(dir=folder)) / 'calls.jsonl'
        wrapper = NgspiceWrapper.__new__(NgspiceWrapper)
        wrapper.audit_path, wrapper.audit_phase, wrapper.audit_offset = audit, 'warmup', 4
        with patch.dict(os.environ, {'NGSPICE_EXECUTABLE': 'mock-ngspice', 'CAD_EXPERIMENT_START': '0'}), \
             patch('ngspice_interface.ngspice_wrapper.subprocess.run', side_effect=[
                 SimpleNamespace(returncode=0), SimpleNamespace(returncode=1), OSError('mock launch failure')]) as process, \
             patch('ngspice_interface.ngspice_wrapper.time.perf_counter', side_effect=[10., 12., 13., 20., 23., 24., 30., 31., 32.]):
            self.assertEqual(wrapper.simulate('first.cir'), 0)
            self.assertEqual(wrapper.simulate('second.cir'), 1)
            with self.assertRaises(OSError):
                wrapper.simulate('third.cir')
        entries = [json.loads(line) for line in audit.read_text().splitlines()]
        self.assertEqual([e['simulation_index'] for e in entries], [5, 6, 7])
        self.assertEqual([e['returncode'] for e in entries], [0, 1, None])
        self.assertEqual(wrapper.simulator_execution_s, 6.)
        self.assertEqual(process.call_args_list[0].args[0], ['mock-ngspice', '-b', 'first.cir'])


if __name__ == '__main__':
    unittest.main()
