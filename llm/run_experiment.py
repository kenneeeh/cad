"""Launch one native Antigravity experiment; save its measured best design and status."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
from candidates import CandidateArchive
from circuit_adapter import setup_id

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get('CAD_MODEL', 'gemini-3.8-flash-low')
AGY = HERE.parent.parent / '.tools/antigravity/agy.exe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--llm-only', action='store_true', help='Disable TD3; retain ordinary LLM evaluation')
    parser.add_argument('--budget', type=int, default=20)
    parser.add_argument('--td3-config', type=Path, default=HERE.parent / 'output_figs/2026-11-05--18-35-18/params.json')
    parser.add_argument('--archive', type=Path, help='optional shared candidate JSONL')
    args = parser.parse_args()
    problem_id = setup_id(HERE.parent)
    if args.budget < 1:
        parser.error('--budget must be positive')
    if not args.llm_only and not args.td3_config.is_file():
        parser.error('Hybrid mode requires an existing --td3-config params.json')
    mode = 'llm_only' if args.llm_only else 'hybrid'
    (HERE / 'runs').mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=mode + '_', dir=HERE / 'runs'))
    archive = CandidateArchive((args.archive or run / 'candidates.jsonl').resolve(), problem_id)
    previous_ids = {r['design_id'] for r in archive.records()}
    parameters = json.loads((HERE / 'initial_design.json').read_text())
    start = 'First simulate these unchanged physical parameters once: ' + json.dumps(parameters, separators=(',', ':'))
    workflow = ('TD3 is disabled. Refine measured designs using physics-guided evaluations/probes.' if args.llm_only else
        'Call warmup(n_steps={w}) once right away (skip other exploration), then call train with LARGE batches '
        'of about {b} steps. TD3 steps cost no tokens; each model turn does, so use few, large calls. '
        'After each train batch you may use at most one targeted evaluate_candidate/probe_parameters on the best '
        'measured design (max 3 interventions in total). Do not consult the specialist and skip the initial get_problem/get_candidates reads (this overrides earlier instructions). Stop when budget is nearly used.'
        ).format(w=max(1, args.budget // 5), b=max(1, args.budget // 5))
    prompt = ((HERE / 'experiment.md').read_text().replace('{{budget}}', str(args.budget))
              .replace('{{start}}', start).replace('{{mode}}', mode).replace('{{workflow}}', workflow))
    command = [str(AGY), '--settings', str(HERE / '.agents/settings.json'), '--agent', 'coordinator',
               '--model', MODEL, '--output-format', 'json', '--print-timeout', '15m', '-p', prompt]
    environment = {**os.environ, 'CAD_MAX_SIMULATIONS': str(args.budget), 'CAD_RUN_ID': run.name,
                   'CAD_RUNS_DIR': str(run), 'CAD_ARCHIVE_PATH': str(archive.path), 'PYTHONDONTWRITEBYTECODE': '1',
                   'CAD_HYBRID': '0' if args.llm_only else '1', 'CAD_TD3_CONFIG': str(args.td3_config.resolve())}
    print(f'Running {mode}, budget={args.budget}, results={run}', flush=True)
    started = perf_counter()
    exit_code = None
    try:
        completed = subprocess.run(command, cwd=HERE, env=environment, capture_output=True,
                                   encoding='utf-8', errors='replace', timeout=930)
        exit_code = completed.returncode
        response = json.loads(completed.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as error:
        response = {'status': 'ERROR', 'error': str(error)}
    attempts = 0
    updates = 0
    for audit in run.glob('session_*/calls.jsonl'):
        records = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
        attempts += max((r['result']['simulation_count'] for r in records), default=0)
        updates += sum(r['result'].get('critic_updates', 0) for r in records)
    candidates = archive.records()
    best = max(candidates, key=lambda r: r['reward'], default=None)
    success = exit_code == 0 and response.get('status') == 'SUCCESS' and attempts <= args.budget and best is not None
    summary = {'success': success, 'mode': mode, 'model': MODEL, 'archive': str(archive.path),
               'simulation_budget': args.budget, 'ngspice_attempts': attempts,
               'critic_updates': updates,
               'wall_clock_s': round(perf_counter()-started, 3), 'usage': response.get('usage'),
               'cli_status': response.get('status'), 'cli_exit_code': exit_code,
               'error': response.get('error'), 'response': response.get('response'),
               'best': best, 'evaluated_design_ids': [r['design_id'] for r in candidates if r['design_id'] not in previous_ids]}
    if not summary['error']:
        if exit_code:
            summary['error'] = completed.stderr.strip() or f'CLI exited with code {exit_code}'
        elif attempts > args.budget:
            summary['error'] = 'Recorded simulator attempts exceed the budget'
        elif response.get('status') != 'SUCCESS':
            summary['error'] = f"CLI returned {response.get('status')}"
        elif best is None:
            summary['error'] = 'No measured design is available'
    (run / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
