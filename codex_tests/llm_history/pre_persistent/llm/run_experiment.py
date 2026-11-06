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
MODEL = 'gemini-3.8-flash-low'
AGY = HERE.parent.parent / '.tools/antigravity/agy.exe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='multi_agent', choices=['multi_agent', 'td3_refine'])
    parser.add_argument('--budget', type=int, default=5, choices=range(1, 6))
    parser.add_argument('--archive', type=Path, help='optional shared candidate JSONL')
    args = parser.parse_args()
    problem_id = setup_id(HERE.parent)
    base = None
    if args.mode == 'td3_refine':
        args.archive = args.archive or HERE / 'runs/candidates.jsonl'
        candidates = CandidateArchive(args.archive, problem_id).records()
        base = max((r for r in candidates if r['source'] == 'TD3' and not r['metadata'].get('fixture', False)),
                   key=lambda r: r['reward'], default=None)
        if base is None:
            parser.error('No current, non-fixture TD3 evaluation. Import measured TD3 candidates first.')
    (HERE / 'runs').mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=args.mode + '_', dir=HERE / 'runs'))
    archive = CandidateArchive((args.archive or run / 'candidates.jsonl').resolve(), problem_id)
    if base:
        start = f'Start from evaluated TD3 ID {base["design_id"]}; retrieve it without re-simulating.'
    else:
        parameters = json.loads((HERE / 'initial_design.json').read_text())
        start = 'First simulate these unchanged physical parameters once: ' + json.dumps(parameters, separators=(',', ':'))
    prompt = (HERE / 'experiment.md').read_text().replace('{{budget}}', str(args.budget)).replace('{{start}}', start)
    command = [str(AGY), '--settings', str(HERE / '.agents/settings.json'), '--agent', 'coordinator',
               '--model', MODEL, '--output-format', 'json', '--print-timeout', '5m', '-p', prompt]
    environment = {**os.environ, 'CAD_MAX_SIMULATIONS': str(args.budget), 'CAD_RUN_ID': run.name,
                   'CAD_RUNS_DIR': str(run), 'CAD_ARCHIVE_PATH': str(archive.path), 'PYTHONDONTWRITEBYTECODE': '1'}
    print(f'Running {args.mode}, budget={args.budget}, results={run}', flush=True)
    started = perf_counter()
    exit_code = None
    try:
        completed = subprocess.run(command, cwd=HERE, env=environment, capture_output=True,
                                   encoding='utf-8', errors='replace', timeout=330)
        exit_code = completed.returncode
        response = json.loads(completed.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as error:
        response = {'status': 'ERROR', 'error': str(error)}
    attempts = 0
    for audit in run.glob('session_*/calls.jsonl'):
        records = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
        attempts += max((r['result']['simulation_count'] for r in records), default=0)
    candidates = archive.records()
    best = max(candidates, key=lambda r: r['reward'], default=None)
    success = exit_code == 0 and response.get('status') == 'SUCCESS' and attempts <= args.budget and best is not None
    summary = {'success': success, 'mode': args.mode, 'model': MODEL, 'archive': str(archive.path),
               'simulation_budget': args.budget, 'ngspice_attempts': attempts,
               'wall_clock_s': round(perf_counter()-started, 3), 'usage': response.get('usage'),
               'cli_status': response.get('status'), 'cli_exit_code': exit_code,
               'error': response.get('error'), 'response': response.get('response'),
               'best': best, 'evaluated_design_ids': [r['design_id'] for r in candidates if r['run_id'] == run.name]}
    if not summary['error']:
        if exit_code:
            summary['error'] = completed.stderr.strip() or f'CLI exited with code {exit_code}'
        elif attempts > args.budget:
            summary['error'] = 'Recorded simulator attempts exceed the budget'
        elif best is None:
            summary['error'] = 'No measured design is available'
    (run / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
