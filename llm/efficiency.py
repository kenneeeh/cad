"""Offline simulation-efficiency summaries; no model, learner or simulator imports."""
import argparse
import json
from pathlib import Path

DEFAULT_THRESHOLDS = (.1, .3, .5, .6)


def summarize_efficiency(records, events, attempts=None, thresholds=DEFAULT_THRESHOLDS):
    simulations = [e for e in events if e.get('event') == 'simulation_attempt']
    indexed = {e['simulation_index']: e for e in simulations}
    attempts = attempts if attempts is not None else max(indexed, default=0)
    coverage = set(indexed) == set(range(1, attempts + 1)) and len(indexed) == len(simulations)
    timed = coverage and bool(simulations)
    warnings = []
    if not coverage or not simulations:
        warnings.append('Complete per-attempt simulator timing unavailable; do not infer missing costs.')
    measured_s = sum(e['simulator_execution_s'] for e in simulations)
    prefix_s, cost = {}, 0.
    if timed:
        for index in range(1, attempts + 1):
            cost += indexed[index]['simulator_execution_s']
            prefix_s[index] = cost
    curve, milestones, best = [], [], None
    valid = []
    for record in records:
        metadata = record['metadata']
        index, elapsed = metadata.get('cumulative_simulation_count'), metadata.get('elapsed_s')
        if index is None or elapsed is None or metadata.get('fixture'):
            warnings.append('Candidate lacks current-run timing/index or is a fixture: ' + record['design_id'])
            continue
        valid.append(record)
    valid.sort(key=lambda r: r['metadata']['cumulative_simulation_count'])
    for record in valid:
        metadata = record['metadata']
        index = metadata['cumulative_simulation_count']
        point = {'design_id': record['design_id'], 'source': record['source'],
                 'origin': metadata.get('origin', record['source']),
                 'phase': metadata.get('phase'), 'reward': record['reward'],
                 'feasible': record['hard_satisfied'], 'simulation_index': index,
                 'elapsed_s': metadata['elapsed_s']}
        if record['hard_satisfied'] and (best is None or record['reward'] > best):
            best = record['reward']
            milestone = dict(point)
            prefix_timed = timed and 1 <= index <= attempts
            simulator_s = prefix_s[index] if prefix_timed else None
            milestone['simulator_execution_s'] = simulator_s
            overhead = point['elapsed_s'] - simulator_s if simulator_s is not None else None
            milestone['non_simulator_elapsed_s'] = overhead if overhead is not None and overhead >= 0 else None
            milestones.append(milestone)
        curve.append({**point, 'best_feasible_reward': best})
    counts = {}
    for event in simulations:
        phase = event['initiator']
        counts[phase] = counts.get(phase, 0) + 1
    batches = [e for e in events if e.get('event') == 'tool_call' and e.get('tool') in ('warmup', 'train')]
    batch_overhead = (sum(e['tool_runtime_s'] - e['simulator_execution_s'] for e in batches)
                      if batches and all('tool_runtime_s' in e and 'simulator_execution_s' in e for e in batches) else None)
    return {'actual_ngspice_attempts': attempts, 'attempt_log_complete': coverage and bool(simulations),
            'attempts_by_initiating_phase': counts, 'curve': curve, 'new_best_feasible': milestones,
            'thresholds': [{'fom': t, 'first_hit': next((m for m in milestones if m['reward'] >= t), None)}
                           for t in thresholds],
            'timing': {'measured_simulator_execution_s': measured_s if simulations else None,
                       'total_simulator_execution_s': measured_s if timed else None,
                       'td3_non_simulator_batch_s': batch_overhead,
                       'pure_llm_inference_s': None, 'pure_td3_compute_s': None},
            'warnings': warnings}


def compare_efficiency(baseline, hybrid, compatible=True):
    """Hypothetical equal-cost simulator model at the SAME attained feasible FoM."""
    result = []
    for target in hybrid['thresholds']:
        threshold, h = target['fom'], target['first_hit']
        b = next((t['first_hit'] for t in baseline['thresholds'] if t['fom'] == threshold), None)
        row = {'fom': threshold, 'baseline': b, 'hybrid': h, 'simulations_saved': None,
               'break_even_simulator_s': None}
        if b is None or h is None:
            row['limitation'] = 'Common feasible threshold not observed in both runs; unreached is not zero cost.'
        else:
            saved = b['simulation_index'] - h['simulation_index']
            row['simulations_saved'] = saved
            if not compatible:
                row['limitation'] = 'Settings/setup/baseline provenance do not establish a compatible comparison.'
            elif saved <= 0:
                row['limitation'] = 'No simulation saving at this threshold; no slow-simulator break-even claimed.'
            elif b.get('non_simulator_elapsed_s') is None or h.get('non_simulator_elapsed_s') is None:
                row['limitation'] = 'Complete simulator timing unavailable; overhead cannot be separated.'
            else:
                overhead = h['non_simulator_elapsed_s'] - b['non_simulator_elapsed_s']
                row.update(extra_non_simulator_s=overhead,
                           break_even_simulator_s=max(0., overhead / saved),
                           hypothetical=True,
                           assumption='T = measured non-simulator overhead + N*c; same fixed c for all designs/methods, unchanged overhead.')
        result.append(row)
    return result


def load_run(folder, thresholds):
    folder = Path(folder)
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    archive = folder / 'candidates.jsonl'
    if not archive.exists():
        archive = Path(summary['archive'])
    all_records = [json.loads(line) for line in archive.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = set(summary.get('evaluated_design_ids', []))
    records = [r for r in all_records if r['design_id'] in ids]
    events = [json.loads(line) for path in folder.glob('session_*/calls.jsonl')
              for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    report = summarize_efficiency(records, events, summary.get('ngspice_attempts'), thresholds)
    report['run'] = str(folder)
    report['incomplete'] = summary.get('incomplete')
    report['td3_only'] = bool(manifest.get('plan')) and all(p['tool'] != 'llm' for p in manifest['plan']) and not any(r['source'] == 'LLM' for r in all_records)
    report['problem_id'] = summary.get('problem_id')
    report['td3_settings'] = manifest.get('td3_settings')
    report['external_candidate_ids'] = [r['design_id'] for r in all_records if r['design_id'] not in ids]
    if report['external_candidate_ids']:
        report['warnings'].append('External measured designs exist; their preparation cost is outside this run.')
    report['setup_identifiers'] = {key: value for key, value in manifest.get('sha256', {}).items()
                                 if key.startswith('ngspice_interface/') or key in
                                 ('circuit_env.py', 'td3/agent.py', 'td3/buffer.py', 'td3_runner.py')}
    if 'evaluated_design_ids' not in summary:
        report['warnings'].append('Historical summary has no new-candidate ID list; candidates were not attributed by guesswork.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs='+')
    parser.add_argument('--baseline', type=Path, help='TD3-only launcher run with fresh archive')
    parser.add_argument('--thresholds', nargs='+', type=float, default=DEFAULT_THRESHOLDS)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [load_run(path, args.thresholds) for path in args.runs]
    baseline = load_run(args.baseline, args.thresholds) if args.baseline else None
    comparisons = []
    if baseline:
        for report in reports:
            compatible = (baseline['td3_only'] and baseline['problem_id'] is not None and
                          baseline['problem_id'] == report['problem_id'] and
                          baseline['td3_settings'] is not None and baseline['td3_settings'] == report['td3_settings'] and
                          bool(baseline['setup_identifiers']) and baseline['setup_identifiers'] == report['setup_identifiers'] and
                          not baseline['external_candidate_ids'] and not report['external_candidate_ids'])
            comparisons.append({'run': report['run'], 'threshold_comparison': compare_efficiency(baseline, report, compatible)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'baseline': baseline, 'runs': reports, 'comparisons': comparisons}, indent=2, allow_nan=False), encoding='utf-8')
    print(f'Saved offline efficiency analysis: {args.output}')


if __name__ == '__main__':
    main()
