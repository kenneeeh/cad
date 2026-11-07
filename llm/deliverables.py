"""Deliverable plots and Solutions folder for one run, using the existing plotting functions."""
import argparse
import csv
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from candidates import CandidateArchive
from circuit_adapter import setup_id
from efficiency import summarize_efficiency

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # utils.plotting lives at the repository root.


def summarize_measurements(records, events, attempts=None):
    """Separate archive selection, actual process cost and observed TD3 updates."""
    records = [r for r in records if not r['metadata'].get('fixture')]
    records = sorted(records, key=lambda r: r['metadata'].get('cumulative_simulation_count') or 0)
    best = max(records, key=lambda r: r['reward'], default=None)
    feasible = [r for r in records if r['hard_satisfied']]
    best_feasible = max(feasible, key=lambda r: r['reward'], default=None)
    first = feasible[0] if feasible else None
    training = [e for e in events if e.get('event') == 'tool_call' and e.get('tool') == 'train']
    updates = sum(e['result'].get('critic_updates', 0) for e in training)
    efficiency = summarize_efficiency(records, events, attempts)
    return {'best_measured_reward': best['reward'] if best else None,
            'best_measured_candidate_id': best['design_id'] if best else None,
            'best_feasible_fom': best_feasible['reward'] if best_feasible else None,
            'best_feasible_candidate_id': best_feasible['design_id'] if best_feasible else None,
            'best_feasible_source': best_feasible['source'] if best_feasible else None,
            'best_feasible_origin': best_feasible['metadata'].get('origin', best_feasible['source']) if best_feasible else None,
            'best_feasible_phase': best_feasible['metadata'].get('phase') if best_feasible else None,
            'best_feasible_simulation': best_feasible['metadata'].get('cumulative_simulation_count') if best_feasible else None,
            'best_hard_feasible': best_feasible,
            'first_feasible_simulation': first['metadata'].get('cumulative_simulation_count') if first else None,
            'first_feasible_candidate_id': first['design_id'] if first else None,
            'successful_td3_training_updates': updates, 'td3_training_used': updates > 0,
            'hybrid_training_executed': updates > 0 and any(r['source'] == 'LLM' for r in records),
            'actual_ngspice_attempts': efficiency['actual_ngspice_attempts'],
            'candidate_counts_by_source': dict(Counter(r['source'] for r in records)),
            'candidate_counts_by_phase': dict(Counter('LLM' if r['source'] == 'LLM' else
                                                       r['metadata'].get('phase', 'unknown') for r in records)),
            'td3_training_batches': len(training),
            'td3_training_steps': sum(e['result'].get('steps', 0) for e in training),
            'td3_actor_updates': sum(e['result'].get('actor_updates', 0) for e in training),
            'efficiency': efficiency}


def read_events(run_dir):
    paths = [Path(run_dir) / 'calls.jsonl']
    if not paths[0].is_file():
        paths = sorted(Path(run_dir).glob('session_*/calls.jsonl'))
    return [json.loads(line) for path in paths for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip()]


def verify_saved_run(run_dir, records, events, analysis):
    """Compare independent log reconstruction with a saved summary, without rewriting it."""
    from run_experiment import check_completion, finish_llm_led
    run_dir = Path(run_dir)
    saved = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    best = analysis['best_hard_feasible']
    parent = next((r for r in records if best and r['design_id'] == best['parent_id']), None)
    calls = sorted((e for e in events if e.get('event') == 'tool_call'), key=lambda e: e['elapsed_s'])
    progress = check_completion(manifest['plan'], calls)
    if manifest['strategy'] == 'llm_led':
        progress = finish_llm_led(progress, {'status': saved['cli_status']},
                                  analysis['actual_ngspice_attempts'], manifest['budget'],
                                  records, events, saved.get('cli_exit_code', 0))
    original_first = next((p['simulation_index'] for p in saved.get('efficiency', {}).get('curve', [])
                           if p['feasible']), None)
    agreement = {'attempts': analysis['actual_ngspice_attempts'] == saved['ngspice_attempts'],
                 'critic_updates': analysis['successful_td3_training_updates'] == saved['critic_updates'],
                 'best_id': bool(best) and best['design_id'] == saved['best']['design_id'],
                 'best_fom': bool(best) and best['reward'] == saved['best']['reward'],
                 'first_feasible': analysis['first_feasible_simulation'] == original_first,
                 'phase_counts': all(analysis['candidate_counts_by_phase'].get(k, 0) == v for k, v in
                                    [('LLM', saved['phase_counts']['llm']),
                                     ('warmup', saved['phase_counts']['warmup']),
                                     ('policy', saved['phase_counts']['policy'])])}
    reset_count = sum(e.get('event') == 'reset_measurement' for e in events)
    return {'published_numerical_agreement': agreement, 'protocol_review': progress,
            'recorded_td3_reset_measurements': reset_count,
            'best_parent': parent,
            'best_changes_from_parent': {k: {'from': parent['parameters'][k], 'to': v}
                                         for k, v in best['parameters'].items()
                                         if parent and parent['parameters'][k] != v} if best else {},
            'training_batches': [{'arguments': c.get('arguments'), 'ngspice_attempts': c['ngspice_attempts'],
                                  'result': c['result']} for c in calls if c['tool'] in ('warmup', 'train')],
            'original_stop_reason': saved['stop_reason'],
            'note': 'Numerical provenance is preserved; the reviewed adaptive stopping classification is separate.'}


def write_deliverables(archive_path, run_dir, run_id, exclude_ids=frozenset(), *, events=None,
                       output_dir=None):
    """Generate plots/exports from measurements only, retaining historical setup IDs."""
    run_dir = Path(run_dir).resolve()
    output_dir = Path(output_dir).resolve() if output_dir else run_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    records = CandidateArchive(Path(archive_path).resolve(), setup_id(REPO)).records(include_incompatible=True)
    summary_path = run_dir / 'summary.json'
    saved_summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    problem_id = saved_summary.get('problem_id') or (saved_summary.get('best') or {}).get('problem_id')
    if problem_id:
        records = [r for r in records if r['problem_id'] == problem_id]
    selected = saved_summary.get('evaluated_design_ids')
    if selected is not None:
        selected = set(selected)
        records = [r for r in records if r['design_id'] in selected]
    records = [r for r in records if r['design_id'] not in exclude_ids]
    records.sort(key=lambda r: r['metadata'].get('cumulative_simulation_count') or 0)
    events = read_events(run_dir) if events is None else events
    analysis = summarize_measurements(records, events)
    (output_dir / 'measurement_summary.json').write_text(json.dumps(analysis, indent=2), encoding='utf-8')
    if not records:
        return analysis
    plot_rewards(records, analysis['efficiency'], output_dir)
    from utils.plotting import plot_pareto_front
    pareto = pareto_solutions([r for r in records if r['hard_satisfied']])
    if pareto:
        solutions_dir = output_dir / 'Solutions'
        write_solutions(pareto, solutions_dir)
        copy_netlists(pareto, run_dir, solutions_dir)
        plot_pareto_front([r['specs'] for r in pareto], str(output_dir / 'pareto.png'))
    return analysis


def plot_rewards(records, efficiency, output_dir):
    import matplotlib.pyplot as plt
    indexed = [r for r in records if r['metadata'].get('cumulative_simulation_count') is not None]
    if not indexed:
        return  # Do not fabricate process indices for old archives without them.
    indices = [r['metadata']['cumulative_simulation_count'] for r in indexed]
    fig, ax = plt.subplots(figsize=(9, 5))
    end = max(indices[-1], efficiency['actual_ngspice_attempts'])
    rewards = np.maximum.accumulate([r['reward'] for r in indexed])
    ax.step(indices + [end], list(rewards) + [rewards[-1]], where='post')
    ax.set(xlabel='Cumulative actual ngspice attempts', ylabel='Best measured unconstrained reward',
           title='Running maximum reward (includes infeasible designs)')
    ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(output_dir / 'max_reward.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    curve = [p for p in efficiency['curve'] if p['best_feasible_reward'] is not None]
    if curve:
        end = max(indices[-1], efficiency['actual_ngspice_attempts'])
        ax.step([p['simulation_index'] for p in curve] + [end],
                [p['best_feasible_reward'] for p in curve] + [curve[-1]['best_feasible_reward']], where='post')
        for source, phase in sorted({(p['source'], p['phase'] or '') for p in efficiency['new_best_feasible']}):
            points = [p for p in efficiency['new_best_feasible'] if p['source'] == source and (p['phase'] or '') == phase]
            label = 'LLM' if source == 'LLM' else 'TD3 ' + phase
            ax.scatter([p['simulation_index'] for p in points], [p['reward'] for p in points], label=label)
        ax.legend()
    else:
        ax.text(.5, .5, 'No hard-feasible candidate measured', transform=ax.transAxes, ha='center')
    ax.set(xlabel='Cumulative actual ngspice attempts (including resets/failures)',
           ylabel='Best measured hard-feasible FoM', title='Undefined before first feasible candidate')
    ax.set_xlim(left=0)
    ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(output_dir / 'best_feasible_fom.png', dpi=160)
    plt.close(fig)


def pareto_solutions(feasible):
    from utils.plotting import is_pareto_efficient
    if not feasible:
        return []
    costs = np.array([[r['specs']['area'], r['specs']['current']] for r in feasible])
    return [r for r, efficient in zip(feasible, is_pareto_efficient(costs)) if efficient]


def write_solutions(pareto, solutions_dir):
    """One netlist per Pareto design plus solutions.csv (parameters, specs, FoM)."""
    solutions_dir.mkdir(parents=True, exist_ok=True)
    csv_path = solutions_dir / 'solutions.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['Design', 'Source', 'Parameters', 'Specs', 'Reward'])
        for record in pareto:
            writer.writerow([record['design_id'], record['source'], record['parameters'],
                             record['specs'], record['reward']])
    return csv_path


def copy_netlists(pareto, run_dir, solutions_dir):
    simulation_ids = {r['metadata']['simulation_id']: r['design_id'] for r in pareto}
    for netlist in Path(run_dir).glob('session_*/**/netlists/*.cir'):
        if netlist.stem in simulation_ids:
            shutil.copy(netlist, solutions_dir / f'{simulation_ids[netlist.stem]}.cir')
    for record in pareto:
        saved = Path(run_dir) / 'Solutions' / f"{record['design_id']}.cir"
        target = solutions_dir / saved.name
        if saved.is_file() and saved.resolve() != target.resolve():
            shutil.copy(saved, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path, help='run folder containing candidates.jsonl')
    parser.add_argument('--output-dir', type=Path, help='separate directory for regenerated outputs')
    args = parser.parse_args()
    output = args.output_dir or REPO / 'llm/reports' / args.run_dir.name
    if output.resolve() == args.run_dir.resolve():
        parser.error('Offline regeneration needs a separate output directory; preserve the saved run')
    analysis = write_deliverables(args.run_dir / 'candidates.jsonl', args.run_dir, args.run_dir.name,
                                 output_dir=output)
    if (args.run_dir / 'manifest.json').is_file() and (args.run_dir / 'summary.json').is_file():
        records = [json.loads(line) for line in (args.run_dir / 'candidates.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        verification = verify_saved_run(args.run_dir, records, read_events(args.run_dir), analysis)
        (output / 'verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in analysis.items()
                      if key not in ('best_hard_feasible', 'efficiency')}, indent=2))


if __name__ == '__main__':
    main()
