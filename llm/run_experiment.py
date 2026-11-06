"""Launch one native Antigravity experiment; save its measured best design and status."""
import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import yaml

from candidates import CandidateArchive
from circuit_adapter import setup_id
from efficiency import summarize_efficiency

HERE = Path(__file__).resolve().parent
MODEL = 'gemini-3.8-flash-low'
REPO = Path(__file__).resolve().parent.parent
AGY = HERE.parent.parent / '.tools/antigravity/agy.exe'
CONSTANTS = json.loads((HERE / 'experiment_constants.json').read_text(encoding='utf-8'))
STRATEGIES = CONSTANTS['strategies']
ADAPTIVE_SCHEMA = CONSTANTS['adaptive_schema']
ADAPTIVE_INSTRUCTIONS = CONSTANTS['instructions']['adaptive']
SCHEDULE_INSTRUCTIONS = CONSTANTS['instructions']['schedule']
GUARD_INSTRUCTIONS = CONSTANTS['instructions']['guard']
MEASURE_INITIAL_INSTRUCTIONS = CONSTANTS['instructions']['measure_initial']
PROTECTED_SOURCES = CONSTANTS['protected_sources']
HARNESS_SOURCES = CONSTANTS['harness_sources']
RUNTIME_VARIABLES = CONSTANTS['runtime_variables']


def make_plan(strategy, warmup, training, llm):
    """Fixed step schedule; the LLM-first phase alone has its existing 8/30 trigger."""
    warm = [{'tool': 'warmup', 'steps': warmup}] if warmup else []
    learn = [{'tool': 'train', 'steps': training}] if training else []
    guided = [{'tool': 'llm', 'steps': llm}] if llm else []
    if strategy == 'adaptive':
        return warm + [{'tool': 'adaptive', 'llm_limit': llm, 'train_limit': training,
                        'specialist_limit': 2, 'coordinator_response_limit': 30}]
    if strategy == 'llm_only':
        return guided
    if strategy == 'llm_then_td3':
        return [{'tool': 'llm', 'steps': 30, 'plateau': 8}] + warm + learn
    if strategy == 'td3_then_llm':
        return warm + learn + guided
    if llm and training < 2:
        raise ValueError('Interleaved interventions require at least two training steps')
    if not llm:
        return warm + learn  # Same timestamped archive supports a TD3-only baseline.
    return warm + [{'tool': 'train', 'steps': training // 2}] + guided + [
        {'tool': 'train', 'steps': training - training // 2}]


def check_completion(plan, calls):
    """Check measured tool progress/order, independently of CLI status or reward sign."""
    if any(p['tool'] == 'adaptive' for p in plan):
        return adaptive_progress(plan, calls)
    completed = [0 for _ in plan]
    phase, streak, best = 0, 0, float('-inf')
    errors = []
    for call in calls:
        tool, result = call['tool'], call['result']
        kind = 'llm' if tool in ('simulate_design', 'evaluate_candidate') else tool
        if kind not in ('llm', 'warmup', 'train'):
            continue  # Outer probe calls duplicate their individual evaluation audits.
        if not result.get('success'):
            if not result.get('protocol_rejected') and (call.get('ngspice_attempts', 0) or kind in ('warmup', 'train')):
                errors.append(result.get('error', 'Evaluation failed'))
        count = call.get('ngspice_attempts', 0) if kind == 'llm' else result.get('steps', 0)
        if not count:
            continue
        if phase >= len(plan) or kind != plan[phase]['tool']:
            errors.append('Unexpected evaluation/training phase')
            continue
        completed[phase] += count
        if kind == 'llm' and plan[phase].get('plateau'):
            if result.get('success') and result['reward'] > best:
                best, streak = result['reward'], 0
            else:
                streak += 1
        if completed[phase] > plan[phase]['steps']:
            errors.append('Phase exceeded planned steps')
        if completed[phase] >= plan[phase]['steps'] or (
                plan[phase].get('plateau') and streak >= plan[phase]['plateau']):
            phase += 1
    return {'complete': phase == len(plan) and not errors,
            'next_phase': {**plan[phase], 'remaining_steps': plan[phase]['steps']-completed[phase]} if phase < len(plan) else None,
            'phases': [{**p, 'completed_steps': n, 'complete': index < phase}
                       for index, (p, n) in enumerate(zip(plan, completed))],
            'errors': errors}


def adaptive_progress(plan, calls):
    warmup = next(p['steps'] for p in plan if p['tool'] == 'warmup')
    limits = plan[-1]
    counts = {'warmup': 0, 'llm': 0, 'train': 0}
    errors = []
    for call in calls:
        kind = 'llm' if call['tool'] in ('simulate_design', 'evaluate_candidate') else call['tool']
        if kind not in counts:
            continue
        result = call['result']
        if not result.get('success') and not result.get('protocol_rejected') and (
                call.get('ngspice_attempts', 0) or kind in ('warmup', 'train')):
            errors.append(result.get('error', 'Evaluation failed'))
        count = call.get('ngspice_attempts', 0) if kind == 'llm' else result.get('steps', 0)
        if count and counts['warmup'] < warmup and kind != 'warmup':
            errors.append('Optimization started before mandatory warmup completed')
        counts[kind] += count
    if counts['warmup'] > warmup or counts['llm'] > limits['llm_limit'] or counts['train'] > limits['train_limit']:
        errors.append('Adaptive resource ceiling exceeded')
    next_phase = ({'tool': 'warmup', 'remaining_steps': warmup-counts['warmup']} if counts['warmup'] < warmup else
                  {**limits, 'llm_remaining': limits['llm_limit']-counts['llm'],
                   'train_remaining': limits['train_limit']-counts['train']})
    return {'complete': False, 'next_phase': next_phase, 'counts': counts,
            'phases': [{'tool': 'warmup', 'steps': warmup, 'completed_steps': counts['warmup'],
                        'complete': counts['warmup'] == warmup},
                       {**limits, 'completed_llm': counts['llm'], 'completed_train': counts['train'], 'complete': False}],
            'errors': errors}


def finish_adaptive(protocol, response, attempts, budget, public_path):
    value = response.get('structured_output') or response.get('response')
    try:
        decision = value if isinstance(value, dict) else json.loads(value or '')
    except (ValueError, TypeError):
        decision = {}
    steps = {}
    coordinator_id = None
    if public_path.exists():
        for line in public_path.read_text().splitlines():
            event = json.loads(line)
            if event.get('event') == 'init':
                coordinator_id = event.get('conversation_id')
            step = event.get('step_update', {})
            if step.get('state') == 'DONE':
                steps[(step.get('conversation_id'), step.get('step_index'))] = step
    coordinator_steps = [s for (conversation,_),s in steps.items() if coordinator_id is None or conversation == coordinator_id]
    responses = sum(s.get('step_type') == 'agent_response' for s in coordinator_steps)
    consultations = sum(s.get('tool_name') in ('invoke_subagent','send_message') for s in coordinator_steps)
    limits = protocol['phases'][-1]
    reason = decision.get('stop_reason')
    valid = bool(decision.get('stop_explanation') and decision.get('remaining_methods_assessment'))
    if reason == 'budget_exhausted':
        valid = valid and attempts >= budget
    elif reason == 'resource_limit':
        valid = valid and (protocol['counts']['llm'] >= limits['llm_limit'] or
                          protocol['counts']['train'] >= limits['train_limit'] or
                          responses >= limits['coordinator_response_limit'])
    elif reason != 'no_useful_action':
        valid = False
    if responses > limits['coordinator_response_limit'] or consultations > limits['specialist_limit']:
        protocol['errors'].append('Observed native response/consultation ceiling exceeded (not mechanically enforced by CLI)')
    protocol['complete'] = bool(valid and protocol['phases'][0]['complete'] and not protocol['errors'])
    protocol['phases'][-1]['complete'] = protocol['complete']
    protocol.update(adaptive_final=decision, coordinator_responses=responses, specialist_consultations=consultations,
                    native_limits_enforcement='instructions and post-run audit; CLI timeout enforced')
    return protocol


def cli_result(stdout, run):
    """Keep public native tool events, including schema rejections before Python tools run."""
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        document = None
    if isinstance(document, dict) and 'status' in document:
        return document  # Also accepts existing mocked/older CLI envelopes.
    events = [document] if document is not None else [json.loads(line) for line in stdout.splitlines() if line.strip()]
    public = []
    result = None
    for event in events:
        if event.get('event') == 'step_update':
            step = event['step_update']
            public.append({'event': 'step_update', 'step_update': {key: step[key] for key in
                ('conversation_id', 'step_index', 'state', 'step_type', 'tool_name', 'tool_info', 'usage') if key in step}})
        elif event.get('event') in ('init', 'result'):
            public.append(event)
        if event.get('event') == 'result':
            result = event['result']
    (run / 'public_events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in public), encoding='utf-8')
    if result is None:
        raise ValueError('CLI stream had no final result')
    return result


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--llm-only', action='store_true', help='Disable TD3; retain ordinary LLM evaluation')
    parser.add_argument('--strategy', choices=STRATEGIES, default='interleaved')
    parser.add_argument('--budget', type=int, default=2400)
    parser.add_argument('--td3-config', type=Path, default=HERE.parent / 'output_figs/2026-11-05--18-35-18/params.json')
    parser.add_argument('--archive', type=Path, help='optional shared candidate JSONL')
    parser.add_argument('--measure-initial', action='store_true', help='Measure the unchanged initial design before the hybrid schedule')
    parser.add_argument('--warmup-steps', type=int, help='fixed warmup steps; default saved w')
    parser.add_argument('--train-steps', type=int, help='fixed policy steps; default saved T-w')
    parser.add_argument('--llm-evaluations', type=int, default=6,
                        help='fixed intervention/refinement attempts; 0 permits a TD3-only baseline; LLM-first uses 8/30')
    return parser


def validate_arguments(parser, args):
    if args.budget < 1:
        parser.error('--budget must be positive')
    if not args.llm_only and not args.td3_config.is_file():
        parser.error('Hybrid mode requires an existing --td3-config params.json')
    if args.llm_only and args.strategy != 'interleaved':
        parser.error('--llm-only cannot be combined with a hybrid --strategy')


def resolve_schedule(parser, args):
    """Return the saved TD3 settings, the warmup and training steps and the phase plan."""
    settings = None if args.llm_only else json.loads(args.td3_config.read_text())
    saved_warmup = settings['w'] if settings else 0
    saved_training = settings['T'] - settings['w'] if settings else 0
    warmup = saved_warmup if args.warmup_steps is None else args.warmup_steps
    training = saved_training if args.train_steps is None else args.train_steps
    if min(warmup, training, args.llm_evaluations) < 0:
        parser.error('Schedule counts must be nonnegative')
    if args.llm_only:
        warmup = training = 0
    if args.strategy == 'adaptive' and (warmup != 200 or training > 800 or args.llm_evaluations > 100
                                        or args.measure_initial or args.archive):
        parser.error('Adaptive B requires fresh archive, warmup=200, train ceiling<=800, LLM ceiling<=100 and no pre-warmup measurement')
    try:
        plan = make_plan('llm_only' if args.llm_only else args.strategy, warmup, training, args.llm_evaluations)
        if args.measure_initial:
            plan.insert(0, {'tool': 'llm', 'steps': 1, 'label': 'initial_design'})
    except ValueError as error:
        parser.error(str(error))
    return settings, warmup, training, plan


def read_episode_horizon():
    """Read the literal horizon without creating an environment or simulator."""
    tree = ast.parse((REPO / 'circuit_env.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(node.value) for node in ast.walk(tree)
                if isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute)
                and target.attr == 'max_steps_per_episode' for target in node.targets))


def count_planned_attempts(plan, td3_steps, horizon):
    llm_attempts = sum(p['steps'] for p in plan if p['tool'] == 'llm') + sum(p.get('llm_limit', 0) for p in plan)
    resets = (td3_steps + horizon - 1) // horizon if td3_steps else 0
    return llm_attempts + td3_steps + resets


def build_workflow(args, plan):
    if args.strategy == 'adaptive':
        return STRATEGIES['adaptive'] + ' Resource ceilings and mandatory warmup: ' + json.dumps(plan) + ADAPTIVE_INSTRUCTIONS
    if args.llm_only:
        workflow = 'TD3 is disabled. Refine measured designs using physics-guided evaluations/probes.'
    else:
        workflow = (f'Selected strategy: {args.strategy}. ' + STRATEGIES[args.strategy] +
                    ' Use large train batches up to 500 steps without crossing a planned phase boundary. '
                    'The same process, networks and replay persist; never restart them. '
                    'Read current targets from get_problem: slewRate >=30 V/us and ugbw >=100 MHz; '
                    'do not relax any constraint. Prefix LLM hypotheses with exploration, intervention '
                    'or final_refinement as appropriate so the existing archive preserves phase context. '
                    'Keep final phase counts and candidate IDs concise.')
    workflow += ('\nMandatory predefined schedule (llm counts individual simulation attempts): '
                 + json.dumps(plan) + SCHEDULE_INSTRUCTIONS)
    workflow += GUARD_INSTRUCTIONS
    if args.measure_initial:
        workflow += MEASURE_INITIAL_INSTRUCTIONS
    return workflow


def build_prompt(args, mode, plan, initial_parameters):
    start = ('First simulate these unchanged physical parameters once: '
             + json.dumps(initial_parameters, separators=(',', ':')))
    return ((HERE / 'experiment.md').read_text().replace('{{budget}}', str(args.budget))
            .replace('{{start}}', start).replace('{{mode}}', mode)
            .replace('{{workflow}}', build_workflow(args, plan)))


def git_revision():
    head = (REPO / '.git/HEAD').read_text().strip()
    if not head.startswith('ref: '):
        return head
    reference = REPO / '.git' / head[5:]
    return reference.read_text().strip() if reference.exists() else None


def hash_sources():
    agents = HERE / '.agents'
    sources = [REPO / name for name in PROTECTED_SOURCES]
    sources += list(agents.rglob('*.md')) + list(agents.rglob('*.json'))
    sources += [HERE / name for name in HARNESS_SOURCES]
    sources.append(REPO / 'td3_runner.py')
    sources += list((REPO / 'ngspice_interface/files').rglob('*.cir')) + list((REPO / 'ngspice_interface/files').rglob('*.sp'))
    return {str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path):
            hashlib.sha256(path.read_bytes()).hexdigest() for path in sources if path.is_file()}


def build_manifest(args, settings, initial_parameters, plan, planned_attempts, horizon):
    grids_path = REPO / 'ngspice_interface/files/yaml_files/TwoStage.yaml'
    return {'model': MODEL, 'strategy': 'llm_only' if args.llm_only else args.strategy,
            'source_revision': git_revision(),
            'launch_arguments': sys.argv[1:], 'python_executable': sys.executable,
            'runtime_environment': {name: os.environ.get(name) for name in RUNTIME_VARIABLES},
            'td3_settings': settings, 'initial_design': initial_parameters,
            'targets_and_grids': yaml.load(grids_path.read_text(), Loader=yaml.FullLoader),
            'budget': args.budget, 'plan': plan, 'planned_attempts_max': planned_attempts,
            'episode_horizon': horizon, 'sha256': hash_sources()}


def build_command(args, prompt):
    command = [str(AGY), '--settings', str(HERE / '.agents/settings.json'), '--agent', 'coordinator',
               '--model', MODEL, '--output-format', 'stream-json', '--print-timeout', '15m', '-p', prompt]
    if args.strategy == 'adaptive':
        prompt_flag = command.index('-p')
        command[prompt_flag:prompt_flag] = ['--json-schema', json.dumps(ADAPTIVE_SCHEMA)]
    return command


def build_environment(args, run, archive, started):
    return {**os.environ, 'CAD_MAX_SIMULATIONS': str(args.budget), 'CAD_RUN_ID': run.name,
            'CAD_RUNS_DIR': str(run), 'CAD_ARCHIVE_PATH': str(archive.path), 'PYTHONDONTWRITEBYTECODE': '1',
            'CAD_HYBRID': '0' if args.llm_only else '1', 'CAD_TD3_CONFIG': str(run / 'td3_config.json'),
            'CAD_PROTOCOL_PATH': str(run / 'manifest.json'),
            'CAD_EXPERIMENT_START': str(started)}  # Same monotonic clock in subprocesses.


def write_json(path, document, **options):
    path.write_text(json.dumps(document, indent=2, **options), encoding='utf-8')


def run_cli(command, environment, run):
    """Run the CLI once and return its completed process, exit code and public response."""
    completed = exit_code = None
    try:
        completed = subprocess.run(command, cwd=HERE, env=environment, capture_output=True,
                                   encoding='utf-8', errors='replace', timeout=930)
        exit_code = completed.returncode
        response = cli_result(completed.stdout, run)
    except (subprocess.TimeoutExpired, ValueError, OSError) as error:
        response = {'status': 'ERROR', 'error': str(error)}
    if completed is not None:
        write_json(run / 'cli_output.json', response)
        (run / 'stderr.txt').write_text(completed.stderr, encoding='utf-8')
    return completed, exit_code, response


def read_audit_files(run):
    return [[json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
            for audit in run.glob('session_*/calls.jsonl')]


def count_attempts(audit_files):
    return sum(max((r.get('simulation_index', r.get('result', {}).get('simulation_count', 0)) for r in records),
                   default=0) for records in audit_files)


def stop_reason(args, protocol, response, exit_code, attempts):
    if exit_code != 0 or response.get('status') != 'SUCCESS' or protocol['errors']:
        return 'execution_error'
    if args.strategy == 'adaptive' and protocol['complete']:
        return protocol['adaptive_final']['stop_reason']
    if protocol['complete']:
        return 'protocol_complete'
    return 'budget_exhausted' if attempts >= args.budget else 'early_exit'


def count_phases(new_candidates):
    def phase_of(record):
        return 'llm' if record['source'] == 'LLM' else record['metadata'].get('phase', 'unknown')
    return {phase: sum(1 for record in new_candidates if phase_of(record) == phase)
            for phase in ('llm', 'warmup', 'policy')}


def failure_message(args, response, exit_code, stderr, attempts, best, protocol):
    if exit_code:
        return stderr.strip() or f'CLI exited with code {exit_code}'
    if attempts > args.budget:
        return 'Recorded simulator attempts exceed the budget'
    if response.get('status') != 'SUCCESS':
        return f"CLI returned {response.get('status')}"
    if best is None:
        return 'No measured design is available'
    if not protocol['complete']:
        return 'Incomplete protocol: CLI status does not establish schedule completion'
    return None


def main():
    parser = build_parser()
    args = parser.parse_args()
    problem_id = setup_id(HERE.parent)
    validate_arguments(parser, args)
    settings, warmup, training, plan = resolve_schedule(parser, args)
    horizon = read_episode_horizon()
    planned_attempts = count_planned_attempts(plan, warmup + training, horizon)
    if not plan or planned_attempts > args.budget:
        parser.error(f'Planned schedule needs up to {planned_attempts} attempts including resets; '
                     'increase --budget or specify smaller --warmup-steps/--train-steps/--llm-evaluations')
    mode = 'llm_only' if args.llm_only else 'hybrid'
    (HERE / 'runs').mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=mode + '_', dir=HERE / 'runs'))
    archive = CandidateArchive((args.archive or run / 'candidates.jsonl').resolve(), problem_id)
    previous_ids = {r['design_id'] for r in archive.records()}
    initial_parameters = json.loads((HERE / 'initial_design.json').read_text())
    prompt = build_prompt(args, mode, plan, initial_parameters)
    (run / 'prompt.txt').write_text(prompt, encoding='utf-8')
    manifest = build_manifest(args, settings, initial_parameters, plan, planned_attempts, horizon)
    if settings:
        write_json(run / 'td3_config.json', settings)
    command = build_command(args, prompt)
    print(f'Running {mode}, budget={args.budget}, results={run}', flush=True)
    started = perf_counter()
    environment = build_environment(args, run, archive, started)
    write_json(run / 'manifest.json', {**manifest, 'monotonic_start': started,
                                       'utc_start': datetime.now(timezone.utc).isoformat()})
    completed, exit_code, response = run_cli(command, environment, run)
    audit_files = read_audit_files(run)
    audit_events = [record for records in audit_files for record in records]
    calls = sorted((r for r in audit_events if r.get('event') == 'tool_call'), key=lambda r: r['elapsed_s'])
    attempts = count_attempts(audit_files)
    protocol = check_completion(plan, calls)
    if args.strategy == 'adaptive':
        protocol = finish_adaptive(protocol, response, attempts, args.budget, run / 'public_events.jsonl')
    candidates = archive.records()
    new_candidates = [r for r in candidates if r['design_id'] not in previous_ids]
    best = max(candidates, key=lambda r: r['reward'], default=None)
    success = (exit_code == 0 and response.get('status') == 'SUCCESS' and attempts <= args.budget
               and best is not None and protocol['complete'])
    summary = {'success': success, 'mode': mode, 'model': MODEL, 'archive': str(archive.path),
               'incomplete': not protocol['complete'], 'protocol': protocol,
               'stop_reason': stop_reason(args, protocol, response, exit_code, attempts),
               'strategy': None if args.llm_only else args.strategy,
               'td3_settings': settings, 'td3_config': str(args.td3_config.resolve()) if settings else None,
               'phase_counts': count_phases(new_candidates),
               'simulation_budget': args.budget, 'ngspice_attempts': attempts,
               'critic_updates': sum(r['result'].get('critic_updates', 0) for r in calls),
               'wall_clock_s': round(perf_counter() - started, 3), 'usage': response.get('usage'),
               'cli_status': response.get('status'), 'cli_exit_code': exit_code,
               'error': response.get('error'), 'response': response.get('response'),
               'best': best, 'evaluated_design_ids': [r['design_id'] for r in new_candidates],
               'problem_id': problem_id,
               'efficiency': summarize_efficiency(new_candidates, audit_events, attempts)}
    if not summary['error']:
        stderr = completed.stderr if completed else ''
        summary['error'] = failure_message(args, response, exit_code, stderr, attempts, best, protocol) or summary['error']
    write_json(run / 'summary.json', summary, allow_nan=False)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
