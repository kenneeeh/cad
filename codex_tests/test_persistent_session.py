"""Persistent hybrid backend: actual TD3, mocked circuits by default, no models."""
import asyncio
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import numpy as np
import torch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from codex_tests.test_mcp_server import server, PARAMETERS
from llm.candidates import CandidateArchive
from llm.td3_session import TD3Session, DEFAULT_CONFIG
from llm import td3_session as backend
import td3_runner


class TestPersistentSession(unittest.TestCase):
    def setUp(self):
        os.chdir(REPO)
        torch.set_num_threads(1)
        root = REPO / 'codex_tests/artifacts/persistent'
        root.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix='unit_', dir=root))
        settings = json.loads(DEFAULT_CONFIG.read_text())
        settings.update(batch_size=2, replay_size=32)  # Small explicit unit-test settings only.
        config = self.folder / 'settings.json'
        config.write_text(json.dumps(settings))
        self.archive = CandidateArchive(self.folder / 'candidates.jsonl', server.context['problem_id'])
        self.session = TD3Session(self.archive, self.folder, config)
        self.llm_sim = patch.object(server.env.simulation_engine, 'simulate', return_value=0).start()
        self.td3_sim = patch.object(self.session.env.simulation_engine, 'simulate', return_value=0).start()
        for env in (server.env, self.session.env):
            patch.object(env.simulation_engine, 'measure_metrics', return_value=dict(env.dict_targets)).start()
        patch.object(server, 'archive', self.archive).start()
        patch.object(server, 'td3_session', self.session).start()
        patch.object(server, 'MAX_SIMULATIONS', 100).start()
        patch('circuit_env.plotLearning').start()
        patch('circuit_env.plot_running_maximum').start()
        self.addCleanup(patch.stopall)
        server.env.counter = 0

    def initial(self):
        result = server.simulate_design(PARAMETERS, 'MOCK-only guided initial design.')
        self.assertTrue(result['success'], result)
        return result

    def test_guided_then_random_warmup_reuses_both_tested_functions(self):
        base = self.initial()
        self.assertEqual(base['replay']['deferred'], 1)
        probes = server.probe_parameters(base['design_id'], [{'res': 6100.}, {'res': 6200.}])
        self.assertTrue(probes['success'])
        with patch.object(td3_runner, 'warmup_exploration', wraps=td3_runner.warmup_exploration) as warmup, \
             patch.object(backend, 'inject_llm_candidates', wraps=backend.inject_llm_candidates) as inject:
            result = server.warmup(2)
            warmup.assert_called_once()
            inject.assert_called_once()
        self.assertTrue(result['success'], result)
        self.assertEqual(result['replay']['injected'], 3)
        self.assertEqual(result['buffer_size'], 5)
        self.assertEqual(result['critic_updates'], 0)
        self.assertEqual(self.session.agent.total_it, 0)
        self.assertEqual(self.td3_sim.call_count, 3)  # One measured reset, two random steps.
        self.assertEqual(len(self.session.seen), 3)
        self.assertTrue(np.isfinite(self.session.buffer.state[:5]).all())
        again = self.session.flush()
        self.assertEqual(again['injected'], 0)
        self.assertEqual(again['skipped_duplicates'], 3)

    def test_multiple_train_calls_keep_agent_buffer_and_optimizer_state(self):
        self.initial()
        server.warmup(1)
        agent, buffer = self.session.agent, self.session.buffer
        original_actor = [p.detach().clone() for p in agent.actor.parameters()]
        original_critic = [p.detach().clone() for p in agent.critic.parameters()]
        with patch.object(td3_runner, 'train', wraps=td3_runner.train) as train:
            first, second = server.train(1), server.train(1)
            self.assertEqual(train.call_count, 2)
        self.assertTrue(first['success'] and second['success'])
        self.assertIs(self.session.agent, agent)
        self.assertIs(self.session.buffer, buffer)
        self.assertEqual(agent.total_it, 2)
        self.assertEqual(first['actor_updates'], 0)
        self.assertEqual(second['actor_updates'], 1)
        self.assertTrue(any(not torch.equal(a, b) for a, b in zip(original_actor, agent.actor.parameters())))
        self.assertTrue(any(not torch.equal(a, b) for a, b in zip(original_critic, agent.critic.parameters())))
        self.assertTrue(agent.actor_optimizer.state)
        self.assertTrue(agent.critic_optimizer.state)
        self.assertEqual(self.session.env.counter, 4)  # One reset across all three calls.
        self.assertEqual(self.session.env.episode_steps, 3)
        td3 = [r for r in self.archive.records() if r['source'] == 'TD3']
        self.assertEqual(len(td3), 3)
        self.assertEqual({r['source'] for r in server.get_candidates()['candidates']}, {'LLM', 'TD3'})

    def test_llm_intervention_does_not_touch_live_td3_episode_or_networks(self):
        base = self.initial()
        server.warmup(1)
        server.train(2)
        env, agent = self.session.env, self.session.agent
        fields = ('counter', 'env_steps', 'episode_steps', 'param_values', 'real_specs', 'cur_norm_specs')
        state = deepcopy({name: getattr(env, name) for name in fields})
        obs = self.session.state['obs'].copy()
        weights = deepcopy(agent.actor.state_dict())
        size, calls = self.session.buffer.size, self.td3_sim.call_count
        result = server.evaluate_candidate(base['design_id'], {'res': 6300.}, 'MOCK intervention.')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['replay']['injected'], 1)
        self.assertEqual(self.session.buffer.size, size + 1)
        self.assertEqual(self.td3_sim.call_count, calls)
        self.assertEqual({name: getattr(env, name) for name in fields}, state)
        np.testing.assert_array_equal(self.session.state['obs'], obs)
        for name, value in agent.actor.state_dict().items():
            self.assertTrue(torch.equal(value, weights[name]))
        self.assertEqual(agent.total_it, 2)

    def test_probes_are_independent_and_invalid_probe_does_not_simulate(self):
        base = self.initial()
        result = server.probe_parameters(base['design_id'], [{'res': 6100.}, {'cap': 1e-12}])
        records = [self.archive.get(r['design_id']) for r in result['probes']]
        self.assertEqual(records[0]['parameters']['res'], 6100.)
        self.assertEqual(records[1]['parameters']['res'], PARAMETERS['res'])
        before = self.llm_sim.call_count
        bad = server.probe_parameters(base['design_id'], [{'res': 6150.}])
        self.assertFalse(bad['success'])
        self.assertEqual(self.llm_sim.call_count, before)
        self.assertFalse(server.probe_parameters(base['design_id'], [{}] * 6)['success'])

    def test_terminal_state_defers_until_next_measured_reset(self):
        self.session.env.max_steps_per_episode = 2  # Unit-only boundary check.
        base = self.initial()
        server.warmup(2)
        self.assertTrue(self.session.state['done'])
        result = server.evaluate_candidate(base['design_id'], {'res': 6100.})
        self.assertEqual(result['replay']['deferred'], 1)
        before = self.td3_sim.call_count
        result = server.train(1)
        self.assertEqual(result['replay']['injected'], 1)
        self.assertEqual(self.td3_sim.call_count - before, 2)  # Reset + policy action, no insertion simulation.
        self.assertEqual(self.session.env.episode_steps, 1)

    def test_budget_rejects_whole_batch_before_initialization(self):
        self.initial()
        with patch.object(server, 'MAX_SIMULATIONS', 2):
            result = server.warmup(2)
        self.assertFalse(result['success'])
        self.assertEqual(result['ngspice_attempts'], 0)
        self.td3_sim.assert_not_called()
        self.assertIsNone(self.session.agent)
        for n in (0, -1, 501, True, 1.5):
            self.assertFalse(server.train(n)['success'])

    def test_failed_td3_evaluation_requires_a_fresh_reset(self):
        server.warmup(1)
        agent, buffer = self.session.agent, self.session.buffer
        self.td3_sim.return_value = 1
        failed = server.train(1)
        self.assertFalse(failed['success'])
        self.assertEqual(failed['ngspice_attempts'], 1)
        self.assertTrue(self.session.state['done'])
        self.td3_sim.return_value = 0
        resumed = server.train(1)
        self.assertTrue(resumed['success'])
        self.assertIs(self.session.agent, agent)
        self.assertIs(self.session.buffer, buffer)
        self.assertEqual(resumed['ngspice_attempts'], 2)

    def test_llm_only_and_compact_candidate_retrieval(self):
        with patch.object(server, 'td3_session', None):
            result = self.initial()
            self.assertNotIn('replay', result)
            self.assertFalse(server.train(1)['success'])
            self.assertFalse(server.get_problem()['td3']['active'])
        record = server.get_candidates()['candidates'][0]
        self.assertNotIn('parameters', record)
        full = server.get_candidates(design_id=result['design_id'], include_parameters=True)
        self.assertEqual(full['candidates'][0]['parameters'], PARAMETERS)

    def test_td3_response_is_compact_but_audit_retains_all_ids(self):
        self.initial()
        for phase in ('warmup', 'train'):
            # Stub the whole batch: this checks presentation, not learning.
            best = self.archive.best(1)[0]
            detailed = {'success': True, 'steps': 2, 'evaluated_design_ids': ['a', 'b'],
                        'best_design_id': best['design_id'], 'buffer_size': 3,
                        'critic_updates': 0, 'actor_updates': 0}
            with patch.object(self.session, 'run', return_value=detailed):
                result = getattr(server, phase)(2)
            self.assertNotIn('evaluated_design_ids', result)
            self.assertEqual(result['steps'], 2)
            self.assertEqual(result['best_reward'], best['reward'])
            self.assertEqual(result['hard_satisfied'], best['hard_satisfied'])
            for key in ('ngspice_attempts', 'remaining', 'buffer_size',
                        'critic_updates', 'actor_updates', 'best_design_id'):
                self.assertIn(key, result)
            audit = json.loads((server.RUN / 'calls.jsonl').read_text().splitlines()[-1])
            self.assertEqual(audit['result']['evaluated_design_ids'], ['a', 'b'])
            self.assertEqual(detailed['evaluated_design_ids'], ['a', 'b'])
        self.td3_sim.assert_not_called()

    def test_standalone_runner_keeps_random_only_episode_behavior(self):
        env = self.session.env
        env.max_steps_per_episode = 2
        args = self.session.args
        args.w, args.T = 1, 4
        agent = backend.TD3(7, env.action_space, args)
        buffer = backend.ReplayBuffer(7, 20, max_size=32)
        progress = td3_runner.train(args, env, agent, buffer)
        self.assertEqual(progress, {'warmup_steps': 2, 'training_steps': 2})
        self.assertEqual(agent.total_it, 2)
        self.assertEqual(buffer.size, 4)
        self.assertEqual(env.counter, 6)

    def test_launcher_preserves_measurements_and_reports_cli_failures(self):
        import run_experiment as runner
        for outcome in ('SUCCESS', 'ERROR', 'nonzero', 'timeout', 'json', 'llm_only'):
            with self.subTest(outcome=outcome):
                workspace = self.folder / outcome / 'llm'
                workspace.mkdir(parents=True)
                for name in ('experiment.md', 'initial_design.json'):
                    (workspace / name).write_bytes((REPO / 'llm' / name).read_bytes())
                def cli(command, **kwargs):
                    self.assertEqual(kwargs['env']['CAD_HYBRID'], '0' if outcome == 'llm_only' else '1')
                    self.assertNotIn('{{workflow}}', command[-1])
                    archive = CandidateArchive(kwargs['env']['CAD_ARCHIVE_PATH'], self.archive.problem_id)
                    archive.add(PARAMETERS, server.adapter.assess(dict(server.env.dict_targets)),
                        'LLM', kwargs['env']['CAD_RUN_ID'], {'completed': True, 'simulator': 'ngspice', 'simulation_id': 'MOCK'})
                    audit = Path(kwargs['env']['CAD_RUNS_DIR']) / 'session_mock'
                    audit.mkdir()
                    (audit / 'calls.jsonl').write_text(json.dumps({'result': {'simulation_count': 1, 'critic_updates': 0}})+'\n')
                    if outcome == 'timeout':
                        raise subprocess.TimeoutExpired(command, 330)
                    status = 'ERROR' if outcome == 'ERROR' else 'SUCCESS'
                    return backend.SimpleNamespace(returncode=2 if outcome == 'nonzero' else 0,
                        stdout='bad JSON' if outcome == 'json' else json.dumps({'status': status, 'usage': {'input_tokens': 5}}),
                        stderr='CLI failure')
                argv = ['run_experiment.py', '--budget', '3', '--td3-config', str(DEFAULT_CONFIG)]
                if outcome == 'llm_only':
                    argv += ['--llm-only']
                with patch.object(runner, 'HERE', workspace), patch.object(runner, 'setup_id', return_value=self.archive.problem_id), \
                     patch.object(sys, 'argv', argv), patch.object(runner.subprocess, 'run', side_effect=cli), \
                     patch('sys.stdout', io.StringIO()):
                    code = runner.main()
                summary = json.loads(next((workspace / 'runs').glob('*/summary.json')).read_text())
                self.assertEqual(code, 0 if outcome in ('SUCCESS', 'llm_only') else 1)
                self.assertIsNotNone(summary['best'])
                self.assertEqual(summary['ngspice_attempts'], 1)


@unittest.skipUnless(os.environ.get('CAD_PERSISTENT_REAL') == '1', 'Opt-in actual ngspice/MCP smoke')
class TestRealPersistentMCP(unittest.TestCase):
    def test_real_stdio_workflow(self):
        asyncio.run(self.workflow())

    async def workflow(self):
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        root = REPO / 'codex_tests/artifacts/persistent'
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='real_', dir=root))
        config = StdioServerParameters(command=sys.executable, args=['-B', str(REPO / 'llm/mcp_server.py')],
            env={**os.environ, 'CAD_HYBRID': '1', 'CAD_MAX_SIMULATIONS': '12',
                 'CAD_RUNS_DIR': str(folder), 'CAD_ARCHIVE_PATH': str(folder / 'candidates.jsonl'),
                 'CAD_TD3_CONFIG': str(DEFAULT_CONFIG), 'CAD_RUN_ID': folder.name,
                 'MPLBACKEND': 'Agg', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
        results = []
        async with stdio_client(config) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                async def call(name, args):
                    response = (await client.call_tool(name, args)).structured_content
                    self.assertTrue(response['success'], response)
                    results.append({'tool': name, 'result': response})
                    return response
                base = await call('simulate_design', {'parameters': PARAMETERS, 'hypothesis': 'SDK-supplied smoke, no LLM proposal.'})
                await call('probe_parameters', {'base_design_id': base['design_id'], 'changes_list': [{'res': 6100.}]})
                warm = await call('warmup', {'n_steps': 2})
                self.assertEqual(warm['replay']['injected'], 2)
                self.assertEqual(warm['critic_updates'], 0)
                first = await call('train', {'n_steps': 2})
                intervention = await call('evaluate_candidate', {'base_design_id': base['design_id'], 'changes': {'res': 6200.}})
                self.assertEqual(intervention['replay']['injected'], 1)
                second = await call('train', {'n_steps': 2})
                self.assertEqual(first['critic_updates'], 2)
                self.assertEqual(second['critic_updates'], 2)
                self.assertEqual(second['training_steps_total'], 4)
                self.assertEqual(second['simulation_count'], 10)
                self.assertEqual(second['buffer_size'], 9)
                best = (await client.call_tool('get_candidates', {'k': 5})).structured_content
                problem = (await client.call_tool('get_problem', {})).structured_content
                self.assertEqual(problem['td3']['training_steps'], 4)
        records = [json.loads(line) for line in (folder / 'candidates.jsonl').read_text().splitlines()]
        self.assertEqual(sum(r['source'] == 'TD3' for r in records), 6)
        self.assertEqual(sum(r['source'] == 'LLM' for r in records), 3)
        self.assertTrue(all(np.isfinite(list(r['specs'].values())).all() and np.isfinite(r['reward']) for r in records))
        evidence = {'ngspice_attempts': 10, 'llm_evaluations': 3, 'td3_step_evaluations': 6,
                    'td3_reset_evaluations': 1, 'critic_updates': 4, 'actor_updates': 2,
                    'model_calls': 0, 'calls': results, 'best': best['candidates'][0]}
        (folder / 'smoke.json').write_text(json.dumps(evidence, indent=2, allow_nan=False))
        print('PERSISTENT MCP EVIDENCE:', folder / 'smoke.json')


if __name__ == '__main__':
    unittest.main(verbosity=2)
