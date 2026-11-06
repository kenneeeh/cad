"""One in-process TD3 learner; reuse the runner loops and tested replay insertion."""
from copy import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from circuit_env import CircuitEnv
from td3 import TD3, ReplayBuffer
import td3_runner
from llm.replay_injection import inject_llm_candidates

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / 'output_figs/2026-11-05--18-35-18/params.json'


class TD3Session:
    def __init__(self, archive, folder, config=DEFAULT_CONFIG):
        self.archive = archive
        self.config = Path(config)
        self.args = SimpleNamespace(**json.loads(self.config.read_text(encoding='utf-8')))
        # Only output routing changes; learning settings come from the existing saved run.
        self.env = CircuitEnv(run_id=os.path.relpath(Path(folder) / 'td3', REPO / 'output_figs'))
        self.env.simulation_engine.output_netlists_folder = str(Path(folder) / 'td3/netlists')
        self.env.simulation_engine.output_files_folder = str(Path(folder) / 'td3/outputs')
        self.agent = self.buffer = None
        self.state = {'obs': None, 'done': True}
        self.seen = set()
        self.random_steps = self.training_steps = 0

    def flush(self):
        """Defer until measured and nonterminal; insertion itself never simulates."""
        if self.agent is None or self.state['done']:
            pending = sum(r['source'] == 'LLM' and r['design_id'] not in self.seen
                          for r in self.archive.records())
            return {'injected': 0, 'deferred': pending}
        return inject_llm_candidates(self.archive.path, self.buffer, self.env, self.seen)

    def required_evaluations(self, n_steps):
        horizon = self.env.max_steps_per_episode
        resets = (1 + (n_steps - 1) // horizon if self.state['done'] else
                  (self.env.episode_steps + n_steps - 1) // horizon)
        return n_steps + resets

    def run(self, phase, n_steps):
        """Called after the server checks the full batch fits its remaining budget."""
        if type(n_steps) is not int or not 1 <= n_steps <= 500:
            raise ValueError('n_steps must be an integer from 1 to 500')
        if self.agent is None:
            torch.manual_seed(self.args.seed)
            np.random.seed(self.args.seed)
            self.env.action_space.seed(self.args.seed)
            self.agent = TD3(self.env.obs_dim, self.env.action_space, self.args)
            self.buffer = ReplayBuffer(self.env.obs_dim, self.env.n_actions, max_size=self.args.replay_size)
        before, updates = self.env.counter, self.agent.total_it
        start_steps = self.env.env_steps
        old_ids = {r['design_id'] for r in self.archive.records()}
        try:
            if self.state['done']:
                self.state.update(obs=self.env.reset(), done=False)
            replay = self.flush()
            batch = copy(self.args)
            batch.w = batch.T = n_steps  # Batch lengths, not learning hyperparameters.
            if phase == 'warmup':
                td3_runner.warmup_exploration(batch, self.env, self.buffer, self.agent,
                    continuation=self.state, archive_path=self.archive.path)
            else:
                td3_runner.train(batch, self.env, self.agent, self.buffer,
                    continuation=self.state, archive_path=self.archive.path)
        except Exception:
            # A failed evaluation must not leave a stale observation reusable next time.
            self.state['done'] = True
            raise
        finally:
            steps = self.env.env_steps - start_steps
            if phase == 'warmup':
                self.random_steps += steps
            else:
                self.training_steps += steps
        records = [r for r in self.archive.records() if r['design_id'] not in old_ids]
        return {'success': True, 'steps': steps, 'ngspice_attempts': self.env.counter - before,
                'critic_updates': self.agent.total_it - updates,
                'actor_updates': self.agent.total_it // self.agent.policy_freq - updates // self.agent.policy_freq,
                'replay': replay, 'buffer_size': self.buffer.size,
                'training_steps_total': self.training_steps,
                'evaluated_design_ids': [r['design_id'] for r in records],
                'best_design_id': max(records, key=lambda r: r['reward'])['design_id'] if records else None}
