"""Seven tools sharing measured designs and one persistent TD3 session."""
from contextlib import redirect_stdout
from functools import wraps
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import RLock
from time import perf_counter
from typing import Annotated, Any
from pydantic import Field
from mcp.server.mcpserver import MCPServer

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RUNS = Path(os.environ.get('CAD_RUNS_DIR', str(HERE / 'runs'))).resolve()
RUNS.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix='session_', dir=RUNS))
os.environ.setdefault('MPLCONFIGDIR', str(RUN / 'matplotlib'))
os.environ.setdefault('MPLBACKEND', 'Agg')
sys.path.insert(0, str(REPO))
from circuit_env import CircuitEnv
from circuit_adapter import CircuitAdapter
from candidates import CandidateArchive, apply_changes, compact, EXPERIMENT_START
from llm.td3_session import TD3Session, DEFAULT_CONFIG

os.chdir(REPO)  # CircuitEnv/netlist include paths use the repository directory.
with redirect_stdout(sys.stderr):  # stdout is reserved for MCP messages.
    env = CircuitEnv()
env.simulation_engine.output_netlists_folder = str(RUN / 'netlists')
env.simulation_engine.output_files_folder = str(RUN / 'outputs')
adapter = CircuitAdapter(env, REPO)
context = adapter.context()
archive = CandidateArchive(os.environ.get('CAD_ARCHIVE_PATH', str(RUNS / 'candidates.jsonl')), context['problem_id'])
with redirect_stdout(sys.stderr):
    td3_session = (TD3Session(archive, RUN, os.environ.get('CAD_TD3_CONFIG', DEFAULT_CONFIG))
                   if os.environ.get('CAD_HYBRID', '1') == '1' else None)
MAX_SIMULATIONS = int(os.environ.get('CAD_MAX_SIMULATIONS', '5'))
if MAX_SIMULATIONS < 0:
    raise ValueError('CAD_MAX_SIMULATIONS must be nonnegative')
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
lock = RLock()  # ID lookup and simulation share the same lock and counter.
PROTOCOL = json.loads(Path(os.environ['CAD_PROTOCOL_PATH']).read_text()) if os.environ.get('CAD_PROTOCOL_PATH') else None
mcp = MCPServer('cad-simulator', instructions='Only the coordinator may evaluate, probe, warm up or train. All calls share one budget, candidate archive and persistent TD3 memory.')


def total_attempts():
    return env.counter + (td3_session.env.counter if td3_session else 0)


env.simulation_engine.audit_path = RUN / 'calls.jsonl'
env.simulation_engine.audit_start = EXPERIMENT_START
if td3_session:
    td3_session.env.simulation_engine.audit_path = RUN / 'calls.jsonl'
    td3_session.env.simulation_engine.audit_start = EXPERIMENT_START


def simulator_time():
    return (getattr(env.simulation_engine, 'simulator_execution_s', 0.) +
            (getattr(td3_session.env.simulation_engine, 'simulator_execution_s', 0.) if td3_session else 0.))


def protocol_state(extra_call=None):
    if PROTOCOL is None:
        return None
    from run_experiment import check_completion
    path = RUN / 'calls.jsonl'
    calls = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    if extra_call:
        calls.append(extra_call)
    return check_completion(PROTOCOL['plan'], [c for c in calls if c.get('event') == 'tool_call'])


def protocol_guard(kind, count, parameters=None, reason=''):
    state = protocol_state()
    if state is None:
        return None
    phase = state['next_phase']
    error = None
    if state['errors']:
        error = 'Protocol has an execution error; stop and report partial completion'
    elif phase is None:
        error = 'Protocol complete; stop without further evaluations'
    elif phase['tool'] == 'adaptive':
        remaining = phase['llm_remaining'] if kind == 'llm' else phase['train_remaining'] if kind == 'train' else 0
        if count > remaining or kind not in ('llm','train'):
            error = 'Adaptive resource ceiling or completed warmup; select a remaining method'
        elif kind == 'train' and (not reason.strip() or not any(r['design_id'] in reason for r in archive.records())):
            error = 'Adaptive train requires a measurement-based reason citing actual candidate IDs'
    elif phase['tool'] != kind or count > phase['remaining_steps']:
        error = 'Wrong phase or count; follow returned protocol progress'
    elif phase.get('label') == 'initial_design' and parameters != PROTOCOL['initial_design']:
        error = 'First evaluate the unchanged initial_design.json parameters'
    if error:
        return {'success': False, 'protocol_rejected': True, 'error': error, 'protocol': state,
                'simulation_count': total_attempts(), 'ngspice_attempts': 0}
    return None


def audited(function):
    """Keep actual tool inputs/results locally; do not expand model responses."""
    @wraps(function)
    def call(*args, **kwargs):
        from inspect import signature
        arguments = dict(signature(function).bind(*args, **kwargs).arguments)
        before = total_attempts()
        started, before_simulator = perf_counter(), simulator_time()
        result = function(*args, **kwargs)
        try:
            json.dumps(arguments, allow_nan=False)
        except ValueError:
            # Direct Python callers can supply NaN; retain the rejected input without invalid JSON.
            arguments = {'invalid_arguments_repr': repr(arguments)}
        record = {'event': 'tool_call', 'tool': function.__name__, 'arguments': arguments,
                  'ngspice_attempts': total_attempts() - before,
                  'tool_runtime_s': perf_counter() - started,
                  'simulator_execution_s': simulator_time() - before_simulator,
                  'elapsed_s': perf_counter() - float(os.environ.get('CAD_EXPERIMENT_START', EXPERIMENT_START)),
                  'result': result}
        if PROTOCOL and any(p['tool']=='adaptive' for p in PROTOCOL['plan']):
            result['adaptive_resources'] = protocol_state(record)['next_phase']
        with (RUN / 'calls.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, allow_nan=False) + '\n')
        return result
    return call


def _evaluate(parameters, hypothesis, parent_id=None):
    with lock:
        rejected = protocol_guard('llm', 1, parameters)
        if rejected:
            return rejected
        try:
            if not isinstance(hypothesis, str) or len(hypothesis) > 300:
                raise ValueError('hypothesis must be a string of at most 300 characters')
            adapter.validate_parameters(parameters)
        except (ValueError, TypeError) as error:
            return {'success': False, 'error': str(error), 'simulation_count': total_attempts()}
        if total_attempts() >= MAX_SIMULATIONS:
            return {'success': False, 'error': 'Simulation budget exhausted', 'simulation_count': total_attempts(), 'remaining': 0}
        started = perf_counter()
        env.simulation_engine.audit_phase = 'LLM'
        env.simulation_engine.audit_offset = td3_session.env.counter if td3_session else 0
        try:
            with redirect_stdout(sys.stderr):
                assessment = adapter.assess(env.simulate(parameters))
            candidate = archive.add(parameters, assessment, 'LLM', os.environ.get('CAD_RUN_ID', RUN.name),
                {'completed': True, 'simulator': 'ngspice', 'simulation_id': env.simulation_engine.random_name,
                 'simulation_count': total_attempts()}, parent_id, hypothesis)
            result = {'success': True, 'design_id': candidate['design_id'],
                      **{key: assessment[key] for key in ('specs', 'reward', 'hard_satisfied', 'violated_constraints')}}
            if td3_session:
                result['replay'] = td3_session.flush()
        except (OSError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
            result = {'success': False, 'hard_satisfied': False, 'error': str(error)}
        result.update(simulation_count=total_attempts(), remaining=MAX_SIMULATIONS-total_attempts(),
                      simulation_id=getattr(env.simulation_engine, 'random_name', None),
                      runtime_s=round(perf_counter()-started, 4))
        return result


@mcp.tool(structured_output=True)
@audited
def get_problem() -> dict[str, Any]:
    """Read physical grids/units, targets, reward convention and remaining budget. No simulation."""
    return {**adapter.problem(context), 'simulation_count': total_attempts(),
            'protocol': protocol_state(),
            'remaining': MAX_SIMULATIONS-total_attempts(),
            'td3': {'active': td3_session is not None,
                    'initialized': td3_session is not None and td3_session.agent is not None,
                    'buffer_size': td3_session.buffer.size if td3_session and td3_session.buffer is not None else 0,
                    'training_steps': td3_session.training_steps if td3_session else 0,
                    'settings': vars(td3_session.args) if td3_session else None}}


@mcp.tool(structured_output=True)
@audited
def get_candidates(k: Annotated[int, Field(strict=True, ge=1, le=20)] = 5,
                   design_id: str | None = None, include_parameters: bool = False) -> dict[str, Any]:
    """Read best distinct measured designs, or one ID. Full record only on request."""
    with lock:
        try:
            if type(k) is not int or not 1 <= k <= 20:
                raise ValueError('k must be an integer from 1 to 20')
            records = [archive.get(design_id)] if design_id else archive.best(k)
            return {'success': True, 'candidates': [compact(r, include_parameters) for r in records]}
        except ValueError as error:
            return {'success': False, 'error': str(error)}


@mcp.tool(structured_output=True)
@audited
def simulate_design(parameters: dict[str, Number],
                    hypothesis: Annotated[str, Field(max_length=300)] = '') -> dict[str, Any]:
    """Evaluate all physical parameters once. Use get_problem for names, units and grids."""
    return _evaluate(parameters, hypothesis)


@mcp.tool(structured_output=True)
@audited
def evaluate_candidate(base_design_id: str, changes: dict[str, Number],
                       hypothesis: Annotated[str, Field(max_length=300)] = '') -> dict[str, Any]:
    """Copy a measured base and evaluate absolute changed values using the same budget."""
    with lock:
        try:
            parameters, actual = apply_changes(archive.get(base_design_id)['parameters'], changes)
        except ValueError as error:
            return {'success': False, 'error': str(error), 'simulation_count': total_attempts()}
        result = _evaluate(parameters, hypothesis, base_design_id)
        result.update(parent_id=base_design_id, changes=actual)
        return result


@mcp.tool(structured_output=True)
@audited
def probe_parameters(base_design_id: str,
                     changes_list: Annotated[list[dict[str, Number]], Field(min_length=1, max_length=5)],
                     hypothesis: Annotated[str, Field(max_length=300)] = '') -> dict[str, Any]:
    """Test 1–5 independent absolute modifications of the SAME measured base."""
    with lock:
        if not 1 <= len(changes_list) <= 5:
            return {'success': False, 'error': 'Use one to five probes'}
        rejected = protocol_guard('llm', len(changes_list))
        if rejected:
            return rejected
        results = [evaluate_candidate(base_design_id, changes, hypothesis) for changes in changes_list]
        return {'success': all(r['success'] for r in results), 'probes': results,
                'simulation_count': total_attempts(), 'remaining': MAX_SIMULATIONS-total_attempts()}


def _td3_batch(phase, n_steps, reason=''):
    with lock:
        rejected = protocol_guard(phase, n_steps, reason=reason)
        if rejected:
            return rejected
        started = perf_counter()
        before = total_attempts()
        before_updates = td3_session.agent.total_it if td3_session and td3_session.agent else 0
        before_steps = td3_session.env.env_steps if td3_session else 0
        try:
            if td3_session is None:
                raise ValueError('TD3 is disabled in this LLM-only session')
            if type(n_steps) is not int or not 1 <= n_steps <= 500:
                raise ValueError('n_steps must be an integer from 1 to 500')
            needed = td3_session.required_evaluations(n_steps)
            if needed > MAX_SIMULATIONS-total_attempts():
                raise ValueError(f'Batch needs {needed} evaluations including resets; reduce n_steps to fit the budget')
            td3_session.env._llm_simulation_attempts = env.counter  # Export accounting only.
            td3_session.env.simulation_engine.audit_offset = env.counter
            td3_session.env.simulation_engine.audit_phase = phase
            with redirect_stdout(sys.stderr):
                result = td3_session.run(phase, n_steps)
        except (OSError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
            result = {'success': False, 'error': str(error)}
        result.update(simulation_count=total_attempts(), remaining=MAX_SIMULATIONS-total_attempts(),
                      ngspice_attempts=total_attempts()-before, runtime_s=round(perf_counter()-started, 4))
        after_updates = td3_session.agent.total_it if td3_session and td3_session.agent else 0
        result['critic_updates'] = after_updates-before_updates
        result.setdefault('steps', td3_session.env.env_steps-before_steps if td3_session else 0)
        with (RUN / 'calls.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps({'event': 'td3_batch', 'tool': phase, 'result': result}, allow_nan=False) + '\n')
        # Keep full batch IDs in the audit above, not in repeated model context.
        summary = {key: value for key, value in result.items() if key != 'evaluated_design_ids'}
        if result.get('best_design_id'):
            best = archive.get(result['best_design_id'])
            summary.update(best_reward=best['reward'], hard_satisfied=best['hard_satisfied'])
        if PROTOCOL and any(p['tool']=='adaptive' for p in PROTOCOL['plan']) and result.get('success'):
            ids = set(result.get('evaluated_design_ids', []))
            records = [r for r in archive.records() if r['design_id'] in ids]
            feasible = [r for r in records if r['hard_satisfied']]
            base = max(feasible or records, key=lambda r:r['reward'], default=None)
            if base:
                summary['guidance_base'] = {key:base[key] for key in
                    ('design_id','source','parameters','specs','reward','hard_satisfied','violated_constraints')}
                summary['guidance_base']['constraint_margins'] = {name:(env.dict_targets[name]-base['specs'][name]
                    if name=='noise' else base['specs'][name]-env.dict_targets[name]) for name in env.hard_constraints}
        return summary


@mcp.tool(structured_output=True)
@audited
def warmup(n_steps: Annotated[int, Field(strict=True, ge=1, le=500)]) -> dict[str, Any]:
    """Add random experiences to the persistent memory; no network updates or clearing."""
    return _td3_batch('warmup', n_steps)


@mcp.tool(structured_output=True)
@audited
def train(n_steps: Annotated[int, Field(strict=True, ge=1, le=500)],
          reason: Annotated[str, Field(max_length=600)] = '') -> dict[str, Any]:
    """Continue existing TD3 exploration/learning for exactly n_steps; never reinitialize."""
    return _td3_batch('train', n_steps, reason)


if __name__ == '__main__':
    mcp.run(transport='stdio')
