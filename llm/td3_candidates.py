"""Save completed TD3 evaluations directly to the shared candidate archive."""
import math
from pathlib import Path
import re
import json
import os
from time import perf_counter
from .circuit_adapter import CircuitAdapter
from .candidates import CandidateArchive, EXPERIMENT_START

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def record_reset_evaluation(env):
    """Audit measured resets without adding replay entries or archive selection candidates."""
    path = getattr(env.simulation_engine, 'audit_path', None)
    if not path:
        return
    try:
        assessment = CircuitAdapter(env, REPO).assess(env.real_specs)
        simulation_id = env.simulation_engine.random_name
        record = {'event': 'reset_measurement', 'design_id': 'reset_' + simulation_id,
                  'simulation_id': simulation_id, 'source': 'TD3', 'origin': 'TD3_reset',
                  'phase': getattr(env.simulation_engine, 'audit_phase', 'unknown'),
                  'parameters': dict(env.param_values), **assessment,
                  'simulation_index': env.counter + getattr(env, '_llm_simulation_attempts', 0),
                  'elapsed_s': perf_counter()-float(os.environ.get('CAD_EXPERIMENT_START', EXPERIMENT_START))}
        with Path(path).open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, allow_nan=False)+'\n')
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'Reset measurement audit failed: {error}')


def export_td3_candidate(env, reward, info, path=None, phase='policy'):
    """Call after a successful env.step. No action selection, training or simulation here."""
    adapter = CircuitAdapter(env, REPO)
    simulation_id = getattr(env.simulation_engine, 'random_name', None)
    if env.counter < 1 or not simulation_id or env.param_values != env.simulation_engine.circuit_params:
        raise ValueError('No matching completed physical evaluation to export')
    adapter.validate_parameters(env.param_values)
    assessment = adapter.assess(env.real_specs)
    if not math.isclose(reward, assessment['reward'], rel_tol=1e-9, abs_tol=1e-10) or info['hard_satisfied'] != assessment['hard_satisfied']:
        raise ValueError('Step reward/feasibility does not match its measurements')
    assessment['reward'] = float(reward)
    run_name = re.sub(r'[^A-Za-z0-9_.-]', '_', str(env.run_id))
    output = Path(path) if path is not None else HERE / 'runs' / ('td3_' + run_name) / 'candidates.jsonl'
    CandidateArchive(output, adapter.context()['problem_id']).add(env.param_values, assessment, 'TD3', env.run_id,
        {'completed': True, 'simulator': 'ngspice', 'simulation_id': simulation_id,
         'simulation_count': env.counter, 'phase': phase,
         'cumulative_simulation_count': env.counter + getattr(env, '_llm_simulation_attempts', 0)})
    return output

