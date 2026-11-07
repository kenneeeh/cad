"""Launch one native Antigravity experiment; save its measured best design and status."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime, timezone
from time import perf_counter
import yaml
from candidates import CandidateArchive
from circuit_adapter import setup_id
from deliverables import write_deliverables, summarize_measurements
from efficiency import summarize_efficiency

HERE = Path(__file__).resolve().parent
MODEL = 'gemini-3.8-flash-low'
AGY = os.environ.get('CAD_AGY') or shutil.which('agy') or str(HERE.parent.parent / '.tools/antigravity/agy.exe')
STRATEGIES = {
    'llm_led': (
        'The LLM leads and TD3 is a scarce tool. Start from the best measured design (or the supplied '
        'initial design if none exists) and refine it with specialist-guided probes. Call TD3 only when '
        'LLM refinement is stuck (about four consecutive non-improving evaluations or a conflicting '
        'constraint you cannot resolve): at most one short warmup(n_steps<=30) the first time, then '
        'train(n_steps=20..40, reason=...) batches. After each batch, return to LLM refinement of the best '
        'measured design from either source. Warmup/training are optional ceilings, not mandatory phases. '
        'Stop after a feasible best exists and at least eight subsequent candidate evaluations do not '
        'improve the best feasible FoM, or at a simulation/resource ceiling or execution error. '
        'Infeasible rewards cannot improve that feasible best; reset measurements are charged but do '
        'not advance the candidate-stagnation streak. Finish a started probe batch. '
        'Report the actual stopping reason; feasibility alone is not a stopping condition.'),
    'adaptive': (
        'Experiment B: first complete exactly 200 random warmup transitions, with no learning. '
        'Then independently choose LLM probes or optional TD3 training from measured history. '
        'Prefer physics-guided exploration first. Eight non-improving LLM evaluations or repeated '
        'constraint bottlenecks suggest reconsidering the method, never force a switch or stop. '
        'Use train(n_steps=N, reason="measurement-based reason with candidate IDs") when useful, '
        'prefer 100-400 step batches, and freely return to LLM refinement of promising measured TD3 bases. '
        'No fixed training quota; assess both methods before concluding that no useful action remains.'),
    'interleaved': (
        'Start with TD3 warmup, then large train batches. At occasional batch boundaries, '
        'consult the specialist and refine promising measured TD3 designs with a few LLM '
        'evaluations. Continue training on the SAME learner and shared replay; reserve '
        'budget for continued training after interventions. Do not intervene after every small batch.'),
    'td3_then_llm': (
        'Complete TD3 warmup and training FIRST, reserving a small part of the total budget '
        'for final LLM refinement. Track the best measured TD3 policy candidate across all '
        'training batches using their returned best IDs/rewards (not just the last batch). '
        'Then retrieve its full parameters, consult the specialist and perform controlled '
        'local refinements. After the first LLM evaluation, NEVER call warmup or train again. '
        'If no policy candidate was measured, report that failure rather than substituting an LLM base.'),
    'llm_then_td3': (
        'Begin with specialist-guided LLM exploration ONLY: no warmup/train yet. Count every '
        'actual LLM simulation attempt in THIS run, including the initial measurement and '
        'failed attempts; exclude imported historical candidates and invalid calls that did not simulate. '
        'Track best reward among successful LLM evaluations in this run and consecutive '
        'non-improving attempts in evaluation order. A strictly greater reward resets the streak '
        'to zero; a tie, lower reward or failed simulation increments it. The first successful '
        'evaluation establishes the best and resets the streak. Switch to TD3 immediately after '
        'EITHER eight consecutive non-improving evaluations OR 30 total LLM evaluations. '
        'Limit each probe batch to min(5, 8-streak, 30-total) so it cannot cross the switch point. '
        'Only then call warmup and large train batches, reusing existing replay injection of '
        'the measured LLM designs; make no further LLM evaluations after switching. '
        'If the total simulation budget ends before the trigger, report the TD3 phase as not reached; '
        'never activate TD3 early just to fit it in. Report the switch counts and triggering candidate ID.'),
}


def make_plan(strategy, warmup, training, llm):
    """Fixed step schedule; the LLM-first phase alone has its existing 8/30 trigger."""
    warm = [{'tool': 'warmup', 'steps': warmup}] if warmup else []
    learn = [{'tool': 'train', 'steps': training}] if training else []
    guided = [{'tool': 'llm', 'steps': llm}] if llm else []
    if strategy == 'llm_led':
        return warm + [{'tool': 'llm_led', 'llm_limit': llm, 'train_limit': training}]
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
    if any(p['tool'] == 'llm_led' for p in plan):
        return llm_led_progress(plan, calls)
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


def llm_led_progress(plan, calls):
    """Resource ceilings only: the LLM decides when to call TD3 and when to stop."""
    warmup = next((p['steps'] for p in plan if p['tool'] == 'warmup'), 0)
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
        counts[kind] += call.get('ngspice_attempts', 0) if kind == 'llm' else result.get('steps', 0)
    if counts['warmup'] > warmup or counts['llm'] > limits['llm_limit'] or counts['train'] > limits['train_limit']:
        errors.append('Resource ceiling exceeded')
    if sum(c['tool'] == 'warmup' and c.get('ngspice_attempts', 0) > 0 for c in calls) > 1:
        errors.append('LLM-led permits at most one warmup call')
    if any(c['tool'] == 'train' and c.get('result', {}).get('steps', 0) > 40 for c in calls):
        errors.append('LLM-led training batch exceeded 40 steps')
    return {'complete': False, 'status': 'in_progress', 'within_resource_ceilings': not errors,
            'next_phase': {**limits, 'warmup_remaining': warmup-counts['warmup'],
                           'llm_remaining': limits['llm_limit']-counts['llm'],
                           'train_remaining': limits['train_limit']-counts['train']},
            'counts': counts, 'phases': [{**limits, 'completed_llm': counts['llm'],
                                          'completed_train': counts['train'], 'complete': False}],
            'errors': errors}


def finish_llm_led(progress, response, attempts, budget, records, events=(), exit_code=0):
    """Audit a finished native run; this never schedules or requests evaluations."""
    best, streak = None, 0
    outcomes = [(r['metadata'].get('cumulative_simulation_count'), r) for r in records
                if not r['metadata'].get('fixture')]
    outcomes += [(e['simulation_index'], None) for e in events
                 if e.get('event') == 'simulation_attempt' and e.get('returncode') not in (0, None)]
    indices = [index for index, _ in outcomes]
    ordered_evidence = (all(type(index) is int and 1 <= index <= attempts for index in indices)
                        and len(indices) == len(set(indices)))
    for _, record in sorted(outcomes, key=lambda item: item[0] if item[0] is not None else -1):
        if record and record['hard_satisfied'] and (best is None or record['reward'] > best):
            best, streak = record['reward'], 0
        elif best is not None:
            streak += 1
    failed = (exit_code != 0 or response.get('status') != 'SUCCESS' or progress['errors']
              or attempts > budget)
    exhausted = all(progress['next_phase'][key] <= 0 for key in
                    ('warmup_remaining', 'llm_remaining', 'train_remaining'))
    if failed:
        status, reason, complete = 'execution_failure', 'execution_error', False
    elif ordered_evidence and best is not None and streak >= 8:
        status, reason, complete = 'completed_optimization', 'feasible_stagnation', True
    elif attempts >= budget or exhausted:
        status, reason, complete = 'resource_exhaustion', (
            'simulation_budget_exhausted' if attempts >= budget else 'resource_ceiling_exhausted'), True
    else:
        status, reason, complete = 'voluntary_early_stop', 'unvalidated_early_stop', False
    return {**progress, 'status': status, 'stop_reason': reason, 'complete': complete,
            'phases': [{**phase, 'complete': complete} for phase in progress['phases']],
            'remaining_resources': {key: progress['next_phase'][key + '_remaining']
                                    for key in ('warmup', 'llm', 'train')},
            'best_feasible_reward': best, 'non_improving_candidate_streak': streak,
            'stagnation_order_verified': ordered_evidence,
            'stopping_condition_validated': complete,
            'td3_training_used': any(c.get('event') == 'tool_call' and c.get('tool') == 'train'
                                     and c['result'].get('critic_updates', 0) > 0 for c in events)}


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


ADAPTIVE_SCHEMA = {
    'type': 'object', 'properties': {
        'stop_reason': {'type': 'string', 'enum': ['budget_exhausted','no_useful_action','resource_limit','execution_error']},
        'stop_explanation': {'type': 'string', 'minLength': 1},
        'remaining_methods_assessment': {'type': 'string', 'minLength': 1},
        'best_design_id': {'type': 'string'},
        'decisions': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'candidate_id': {'type': 'string'}, 'decision': {'type': 'string'},
            'reason': {'type': 'string'}, 'next_action': {'type': 'string'}},
            'required': ['candidate_id','decision','reason','next_action'], 'additionalProperties': False}},
        'method_switches': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'method': {'type': 'string'}, 'reason': {'type': 'string'},
            'evidence_candidate_ids': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['method','reason','evidence_candidate_ids'], 'additionalProperties': False}}},
    'required': ['stop_reason','stop_explanation','remaining_methods_assessment','best_design_id','decisions','method_switches'],
    'additionalProperties': False}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=MODEL, help='Exact inherited Antigravity model identifier')
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
    parser.add_argument('--no-plots', action='store_true', help='skip FoM/Pareto plots and Solutions folder')
    args = parser.parse_args()
    problem_id = setup_id(HERE.parent)
    if args.budget < 1:
        parser.error('--budget must be positive')
    if not args.llm_only and not args.td3_config.is_file():
        parser.error('Hybrid mode requires an existing --td3-config params.json')
    if args.llm_only and args.strategy != 'interleaved':
        parser.error('--llm-only cannot be combined with a hybrid --strategy')
    settings = json.loads(args.td3_config.read_text()) if not args.llm_only else None
    warmup = args.warmup_steps if args.warmup_steps is not None else settings['w'] if settings else 0
    training = args.train_steps if args.train_steps is not None else settings['T'] - settings['w'] if settings else 0
    if min(warmup, training, args.llm_evaluations) < 0:
        parser.error('Schedule counts must be nonnegative')
    if args.llm_only:
        warmup = training = 0
    if args.strategy == 'adaptive' and (warmup != 200 or training > 800 or args.llm_evaluations > 100 or args.measure_initial or args.archive):
        parser.error('Adaptive B requires fresh archive, warmup=200, train ceiling<=800, LLM ceiling<=100 and no pre-warmup measurement')
    if args.strategy == 'llm_led' and warmup > 30:
        parser.error('LLM-led warmup ceiling must be at most 30 steps')
    try:
        plan = make_plan('llm_only' if args.llm_only else args.strategy, warmup, training, args.llm_evaluations)
        if args.measure_initial:
            plan.insert(0, {'tool': 'llm', 'steps': 1, 'label': 'initial_design'})
    except ValueError as error:
        parser.error(str(error))
    # Read the existing literal horizon, without creating an environment or simulator.
    repo = Path(__file__).resolve().parent.parent
    tree = ast.parse((repo / 'circuit_env.py').read_text(encoding='utf-8'))
    horizon = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Attribute)
                   and t.attr == 'max_steps_per_episode' for t in node.targets))
    td3_steps = warmup + training
    planned_attempts = sum(p['steps'] for p in plan if p['tool'] == 'llm') + sum(p.get('llm_limit',0) for p in plan) + td3_steps + (
        (td3_steps + horizon - 1) // horizon if td3_steps else 0)
    if not plan or (planned_attempts > args.budget and args.strategy != 'llm_led'):
        parser.error(f'Planned schedule needs up to {planned_attempts} attempts including resets; '
                     'increase --budget or specify smaller --warmup-steps/--train-steps/--llm-evaluations')
    if args.strategy == 'llm_led':
        planned_attempts = min(planned_attempts, args.budget)  # Ceilings need not all fit or be used.
    mode = 'llm_only' if args.llm_only else 'hybrid'
    (HERE / 'runs').mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=mode + '_', dir=HERE / 'runs'))
    archive = CandidateArchive((args.archive or run / 'candidates.jsonl').resolve(), problem_id)
    previous_ids = {r['design_id'] for r in archive.records()}
    parameters = json.loads((HERE / 'initial_design.json').read_text())
    start = 'First simulate these unchanged physical parameters once: ' + json.dumps(parameters, separators=(',', ':'))
    workflow = ('TD3 is disabled. Refine measured designs using physics-guided evaluations/probes.' if args.llm_only else
        f'Selected strategy: {args.strategy}. ' + STRATEGIES[args.strategy] +
        ' Use large train batches up to 500 steps without crossing a planned phase boundary. '
        'The same process, networks and replay persist; never restart them. '
        'Read current targets from get_problem: slewRate >=30 V/us and ugbw >=100 MHz; '
        'do not relax any constraint. Prefix LLM hypotheses with exploration, intervention '
        'or final_refinement as appropriate so the existing archive preserves phase context. '
        'Keep final phase counts and candidate IDs concise.')
    workflow += ('\nMandatory predefined schedule (llm counts individual simulation attempts): ' +
                 json.dumps(plan) + '. Complete it even after finding feasible or positive rewards. '
                 'Do not shrink it or stop for a reward threshold, lack of improvement (except '
                 'the LLM-first phase switch), or a good design. Stop only on protocol completion, '
                 'budget exhaustion or execution error; identify unfinished phases. '
                 'Tie short keep/reject/follow-up decisions to measured candidate IDs in the next '
                 'hypothesis or final response; do not invent retrospective physical explanations.')
    workflow += (' Backend phase/count guards enforce this schedule. Use returned protocol progress; '
                 'do not poll. For each intervention record a short base-ID/hypothesis/trade-off, '
                 'then an actual keep/reject/follow-up decision tied to returned candidate IDs. '
                 'Consult the specialist before choosing intervention values; retain its short advice '
                 'and ID in the final response. No repository reads or reward-based early finish.')
    if args.measure_initial:
        workflow += (' For this protocol, FIRST simulate the unchanged supplied initial design once, '
                     'before TD3 warmup. This initial measurement precedes the strategy sequence.')
    if args.strategy == 'adaptive':
        workflow = STRATEGIES['adaptive'] + ' Resource ceilings and mandatory warmup: '+json.dumps(plan)+(
            '. Select the best measured feasible warmup base with full sizes/specs and margins. '
            'The warmup/train response supplies guidance_base; use it directly without redundant archive reads. '
            'If none is feasible, explicitly say so and use the best measured infeasible base; never invent feasibility. '
            'No initial LLM evaluation before warmup. Keep the same nominal initial_design.json as Experiment A. '
            'At most TWO specialist consultations total: one initial invocation and at most one optional follow-up. '
            'Use at most 30 coordinator responses; reserve the last response for the structured final result. '
            'The CLI has no reliable response-count flag: this limit is advisory and audited, with a 15-minute timeout. '
            'No repository reads, status polling or full-history dumps. Batch independent probes up to five. '
            'Never stop merely because a feasible/positive/sufficient reward was found. Stagnation prompts a method decision. '
            'Continue constructive actions until budget/resource exhaustion, genuine execution error, or a measurement-grounded '
            'explanation of why neither remaining LLM probes nor TD3 is useful. Training is optional, not a required quota. '
            'For each train call, reason must cite actual candidate IDs and recent measurements; 8 non-improving evaluations '
            'are a suggestion, not a forced switch. Record actual method switches and candidate decisions in the structured '
            'final response. Explain remaining methods for every stop, including unused TD3 capacity. '
            'Current constraints remain gain>=200, noise<=0.03 V RMS, PM>=60 deg, rising slew>=30 V/us, UGBW>=100 MHz.')
    if args.strategy == 'llm_led':
        workflow = (STRATEGIES['llm_led'] + ' Resource ceilings: ' + json.dumps(plan) +
            '. warmup/train steps and LLM evaluations beyond these ceilings are rejected. '
            'Without feasibility, continue while a method and sufficient simulation budget remain. '
            'Consult the specialist before the first refinement batch and after each TD3 batch. '
            'For each train call, reason must cite actual candidate IDs and recent measurements. '
            'Prefix hypotheses with exploration, intervention or final_refinement. '
            'Constraints stay gain>=200, noise<=0.03 V RMS, PM>=60 deg, rising slew>=30 V/us, UGBW>=100 MHz. '
            'Finish with the best measured ID, simulations used per method, each TD3 call and why it was made.')
    prompt = ((HERE / 'experiment.md').read_text().replace('{{budget}}', str(args.budget))
              .replace('{{start}}', start).replace('{{mode}}', mode).replace('{{workflow}}', workflow))
    (run / 'prompt.txt').write_text(prompt, encoding='utf-8')
    protected = [repo / p for p in ('circuit_env.py', 'td3/agent.py', 'td3/buffer.py',
                 'ngspice_interface/dut_testbench.py', 'ngspice_interface/ngspice_wrapper.py',
                 'ngspice_interface/files/yaml_files/TwoStage.yaml', 'requirements-lock.txt')]
    identified = protected + list((HERE / '.agents').rglob('*.md')) + list((HERE / '.agents').rglob('*.json'))
    identified += [HERE / name for name in ('GEMINI.md', 'experiment.md', 'initial_design.json',
                   'run_experiment.py', 'mcp_server.py', 'td3_session.py', 'td3_candidates.py',
                   'candidates.py', 'circuit_adapter.py', 'replay_injection.py', 'efficiency.py', 'deliverables.py')]
    identified += [repo / 'td3_runner.py']
    identified += list((repo / 'ngspice_interface/files').rglob('*.cir')) + list((repo / 'ngspice_interface/files').rglob('*.sp'))
    git_head = (repo / '.git/HEAD').read_text().strip()
    revision_file = repo / '.git' / git_head[5:] if git_head.startswith('ref: ') else None
    revision = revision_file.read_text().strip() if revision_file and revision_file.exists() else git_head if not revision_file else None
    manifest = {'model': args.model, 'strategy': args.strategy if not args.llm_only else 'llm_only',
                'source_revision': revision,
                'launch_arguments': sys.argv[1:], 'python_executable': sys.executable,
                'runtime_environment': {name: os.environ.get(name) for name in
                    ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'MPLBACKEND', 'NGSPICE_EXECUTABLE')},
                'td3_settings': settings, 'initial_design': parameters,
                'targets_and_grids': yaml.load((repo / 'ngspice_interface/files/yaml_files/TwoStage.yaml').read_text(), Loader=yaml.FullLoader),
                'budget': args.budget, 'plan': plan, 'planned_attempts_max': planned_attempts,
                'episode_horizon': horizon,
                'sha256': {str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p):
                           hashlib.sha256(p.read_bytes()).hexdigest() for p in identified if p.is_file()}}
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if settings:
        (run / 'td3_config.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
    command = [str(AGY), '--settings', str(HERE / '.agents/settings.json'), '--agent', 'coordinator',
               '--model', args.model, '--output-format', 'stream-json', '--print-timeout', '15m', '-p', prompt]
    if args.strategy == 'adaptive':
        command[command.index('-p'):command.index('-p')] = ['--json-schema', json.dumps(ADAPTIVE_SCHEMA)]
    environment = {**os.environ, 'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'],
                   'CAD_MAX_SIMULATIONS': str(args.budget), 'CAD_RUN_ID': run.name,
                   'CAD_RUNS_DIR': str(run), 'CAD_ARCHIVE_PATH': str(archive.path), 'PYTHONDONTWRITEBYTECODE': '1',
                   'CAD_HYBRID': '0' if args.llm_only else '1', 'CAD_TD3_CONFIG': str(run / 'td3_config.json')}
    environment['CAD_PROTOCOL_PATH'] = str(run / 'manifest.json')
    print(f'Running {mode}, budget={args.budget}, results={run}', flush=True)
    started = perf_counter()
    environment['CAD_EXPERIMENT_START'] = str(started)  # Same monotonic clock in subprocesses.
    (run / 'manifest.json').write_text(json.dumps({**manifest, 'monotonic_start': started,
        'utc_start': datetime.now(timezone.utc).isoformat()}, indent=2), encoding='utf-8')
    exit_code = None
    completed = None
    try:
        completed = subprocess.run(command, cwd=HERE, env=environment, capture_output=True,
                                   encoding='utf-8', errors='replace', timeout=930)
        exit_code = completed.returncode
        response = cli_result(completed.stdout, run)
    except (subprocess.TimeoutExpired, ValueError, OSError) as error:
        response = {'status': 'ERROR', 'error': str(error)}
    if completed is not None:
        (run / 'cli_output.json').write_text(json.dumps(response, indent=2), encoding='utf-8')
        (run / 'stderr.txt').write_text(completed.stderr, encoding='utf-8')
    attempts = 0
    updates = 0
    calls = []
    for audit in run.glob('session_*/calls.jsonl'):
        records = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
        attempts += max((r.get('simulation_index', r.get('result', {}).get('simulation_count', 0)) for r in records), default=0)
        calls.extend(r for r in records if r.get('event') == 'tool_call')
        updates += sum(r['result'].get('critic_updates', 0) for r in records if r.get('event') == 'tool_call')
    calls.sort(key=lambda r: r['elapsed_s'])
    protocol = check_completion(plan, calls)
    if args.strategy == 'adaptive':
        protocol = finish_adaptive(protocol, response, attempts, args.budget, run/'public_events.jsonl')
    candidates = archive.records()
    current_candidates = [r for r in candidates if r['design_id'] not in previous_ids]
    audit_events = [json.loads(line) for audit in run.glob('session_*/calls.jsonl')
                    for line in audit.read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.strategy == 'llm_led':
        protocol = finish_llm_led(protocol, response, attempts, args.budget, current_candidates,
                                  audit_events, exit_code)
    best = max(candidates, key=lambda r: r['reward'], default=None)
    success = (exit_code == 0 and response.get('status') == 'SUCCESS' and attempts <= args.budget
               and best is not None and protocol['complete'])
    summary = {'success': success, 'mode': mode, 'model': args.model, 'archive': str(archive.path),
               'incomplete': not protocol['complete'], 'protocol': protocol,
               'stop_reason': protocol['stop_reason'] if args.strategy == 'llm_led' else
                              'execution_error' if exit_code != 0 or response.get('status') != 'SUCCESS' or protocol['errors'] else
                              protocol['adaptive_final']['stop_reason'] if args.strategy == 'adaptive' and protocol['complete'] else
                              'protocol_complete' if protocol['complete'] else
                              'budget_exhausted' if attempts >= args.budget else 'early_exit',
               'strategy': args.strategy if not args.llm_only else None,
               'td3_settings': settings, 'td3_config': str(args.td3_config.resolve()) if settings else None,
               'phase_counts': {phase: sum(1 for r in candidates if r['design_id'] not in previous_ids
                   and ('llm' if r['source'] == 'LLM' else r['metadata'].get('phase', 'unknown')) == phase)
                   for phase in ('llm', 'warmup', 'policy')},
               'simulation_budget': args.budget, 'ngspice_attempts': attempts,
               'critic_updates': updates,
               'wall_clock_s': round(perf_counter()-started, 3), 'usage': response.get('usage'),
               'cli_status': response.get('status'), 'cli_exit_code': exit_code,
               'error': response.get('error'), 'response': response.get('response'),
               'best': best, 'evaluated_design_ids': [r['design_id'] for r in candidates if r['design_id'] not in previous_ids]}
    summary['problem_id'] = problem_id
    summary.update(summarize_measurements(current_candidates, audit_events, attempts))
    summary['optimization_status'] = protocol.get('status', summary['stop_reason'])
    summary['efficiency'] = summarize_efficiency(
        [r for r in candidates if r['design_id'] not in previous_ids], audit_events, attempts)
    if not summary['error']:
        if exit_code:
            summary['error'] = completed.stderr.strip() or f'CLI exited with code {exit_code}'
        elif attempts > args.budget:
            summary['error'] = 'Recorded simulator attempts exceed the budget'
        elif response.get('status') != 'SUCCESS':
            summary['error'] = f"CLI returned {response.get('status')}"
        elif best is None:
            summary['error'] = 'No measured design is available'
        elif not protocol['complete']:
            summary['error'] = 'Incomplete protocol: CLI status does not establish schedule completion'
    (run / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
    if not args.no_plots:
        write_deliverables(archive.path, run, run.name, previous_ids, events=audit_events)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
