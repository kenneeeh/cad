"""Optional archive injection around the existing TD3 runner; no model calls."""
import argparse
import json
from pathlib import Path
import re
import sys
from time import perf_counter

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import td3_runner
from llm.candidates import CandidateArchive
from llm.replay_injection import inject_llm_candidates


class HybridReplay:
    """One warmup import and one optional checkpoint, sharing a run-local ID set."""
    def __init__(self, archive, warmup=0, after=None, count=1):
        self.archive = Path(archive)
        self.warmup_limit, self.after, self.count = warmup, after, count
        self.seen = set()
        self.events = []
        self.warmup_done = self.checkpoint_done = False

    def _inject(self, phase, steps, env, buffer, limit):
        result = inject_llm_candidates(self.archive, buffer, env, self.seen, limit=limit)
        self.events.append({'phase': phase, 'training_steps': steps, **result})
        print(f'LLM replay {phase}: {result}')
        return result['injected']

    def warmup(self, env, buffer):
        if self.warmup_done or self.warmup_limit == 0:
            return 0
        self.warmup_done = True
        return self._inject('warmup', 0, env, buffer, self.warmup_limit)

    def checkpoint(self, steps, env, buffer):
        # Called before a policy action, so terminal episodes have already reset.
        if self.checkpoint_done or self.after is None or steps < self.after:
            return
        self.checkpoint_done = True
        self._inject('checkpoint', steps, env, buffer, self.count)


def run_training(args, hybrid=None, summary_path=None):
    """Use the teammate's runner unchanged by default, then save basic run counts."""
    run_name = re.sub(r'[^A-Za-z0-9_.-]', '_', str(args.run_id))
    folder = REPO / 'llm/runs' / ('td3_' + run_name)
    archive = CandidateArchive(folder / 'candidates.jsonl', '')
    old_ids = {r['design_id'] for r in archive.records(include_incompatible=True)}
    started = perf_counter()
    env, agent, buffer, progress = td3_runner.main(args, hybrid=hybrid)
    records = [r for r in archive.records(include_incompatible=True) if r['design_id'] not in old_ids]
    policy = [r for r in records if r['metadata']['phase'] == 'policy']
    events = hybrid.events if hybrid else []
    warmup_imports = sum(e['injected'] for e in events if e['phase'] == 'warmup')
    total_imports = sum(e['injected'] for e in events)
    def quality(record):
        return {k: record[k] for k in ('design_id', 'reward', 'hard_satisfied')} if record else None
    result = {'run_id': args.run_id, 'runtime_s': perf_counter() - started,
              'warmup_slots': progress['warmup_steps'],
              'random_warmup_steps': progress['warmup_steps'] - warmup_imports,
              'training_steps': progress['training_steps'], 'td3_step_evaluations': env.env_steps,
              'td3_reset_evaluations': env.counter - env.env_steps,
              'td3_total_evaluations': env.counter, 'critic_updates': agent.total_it,
              'injected_llm_experiences': total_imports, 'injection_events': events,
              'checkpoint_reached': hybrid.checkpoint_done if hybrid and hybrid.after is not None else None,
              'replay_size': buffer.size, 'model_calls': 0,
              'original_llm_runtime_s': None, 'original_llm_tokens': None,
              'td3_rewards_in_step_order': env.reward_history,
              'best_policy_sample': quality(max(policy, key=lambda r: r['reward']) if policy else None),
              'final_policy_sample': quality(policy[-1] if policy else None),
              'policy_sample_note': 'Exploration noise is included; these are not deterministic actor-only evaluations.',
              'td3_candidate_archive': str(archive.path)}
    output = Path(summary_path) if summary_path else folder / 'training_summary.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(f'TD3 summary: {output}')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
        epilog='All other options are passed to td3_runner.py. Run from the repository root.')
    parser.add_argument('--llm-archive', type=Path)
    parser.add_argument('--llm-warmup', type=int, default=0, help='Replace up to N random warmup slots')
    parser.add_argument('--llm-after', type=int, help='Import once before the next action after N policy steps')
    parser.add_argument('--llm-count', type=int, default=1, help='Maximum imports at that checkpoint')
    options, remaining = parser.parse_known_args(argv)
    args = td3_runner.readParser(remaining)
    if options.llm_warmup < 0 or options.llm_count < 1 or (options.llm_after is not None and options.llm_after < 0):
        parser.error('LLM counts must be nonnegative, and --llm-count must be positive')
    if options.llm_warmup > args.w:
        parser.error('--llm-warmup cannot exceed --w')
    enabled = options.llm_warmup > 0 or options.llm_after is not None
    if enabled and (options.llm_archive is None or not options.llm_archive.is_file()):
        parser.error('Injection requires an existing --llm-archive file')
    hybrid = HybridReplay(options.llm_archive, options.llm_warmup, options.llm_after, options.llm_count) if enabled else None
    # Preserve the chosen integration settings in the runner's existing params.json.
    vars(args).update(vars(options))
    args.llm_archive = str(options.llm_archive) if options.llm_archive else None
    return run_training(args, hybrid)


if __name__ == '__main__':
    main()
