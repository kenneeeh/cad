"""Insert measured LLM designs into the existing TD3 buffer; never run a simulator."""
import math
from pathlib import Path
import numpy as np
from .candidates import CandidateArchive
from .circuit_adapter import CircuitAdapter

REPO = Path(__file__).resolve().parent.parent


def physical_to_action(parameters, environment):
    """Convert physical values to absolute actions and check float32/grid reconstruction."""
    CircuitAdapter(environment, REPO).validate_parameters(parameters)
    action = np.array([2*(parameters[name]-low)/(high-low)-1
                       for name, (low, high, _) in environment.dict_params.items()], dtype=np.float32)
    reconstructed = environment.action_refine(action)
    for name, (_, _, step) in environment.dict_params.items():
        if not math.isclose(parameters[name], reconstructed[name], rel_tol=0, abs_tol=step*1e-7):
            raise ValueError(f'Action does not reconstruct {name}')
    return action


def inject_llm_candidates(archive_path, replay_buffer, environment, already_imported_ids, *, limit=None):
    """Call after a successful reset/step. All candidates branch from the current state.

    This is valid for the current static absolute-sizing CircuitEnv: next specs
    and reward depend on the full action, not preceding sizes. No episode is advanced.
    """
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError('limit must be a nonnegative integer or None')
    if not isinstance(already_imported_ids, set):
        raise ValueError('Keep already_imported_ids as one set for this training run')
    if environment.counter < 1 or not 0 <= environment.episode_steps < environment.max_steps_per_episode:
        raise ValueError('Call after a successful reset/step in a nonterminal episode')
    adapter = CircuitAdapter(environment, REPO)
    adapter.assess(environment.real_specs)
    normalized = environment.normalize_specs(environment.real_specs)
    state = np.array([normalized[n] for n in environment.dict_targets], dtype=np.float32)
    if (list(environment.cur_norm_specs) != list(environment.dict_targets)
            or not np.array_equal(state, np.array(list(environment.cur_norm_specs.values()), dtype=np.float32))
            or environment.param_values != environment.simulation_engine.circuit_params):
        raise ValueError('Active observation does not match the measured circuit')
    if replay_buffer.state.shape[1] != len(state) or replay_buffer.action.shape[1] != len(environment.dict_params):
        raise ValueError('Replay dimensions do not match the circuit')
    done = environment.episode_steps + 1 >= environment.max_steps_per_episode
    archive = CandidateArchive(archive_path, adapter.context()['problem_id'])
    inserted, errors, duplicates = [], [], 0
    for record in archive.records(include_incompatible=True):
        if limit is not None and len(inserted) >= limit:
            break
        try:
            if record['source'] != 'LLM':
                continue
            design_id = record['design_id']
            if design_id in already_imported_ids:
                duplicates += 1
                continue
            metadata = record['metadata']
            if record['problem_id'] != archive.problem_id or record['units'] != adapter.units:
                raise ValueError('Different/old simulation setup or specification units')
            if (metadata.get('completed') is not True or metadata.get('simulator') != 'ngspice'
                    or not metadata.get('simulation_id') or metadata.get('fixture', False)):
                raise ValueError('Requires an actual completed evaluation, not a proposal/fixture')
            assessment = adapter.assess(record['specs'])
            if (isinstance(record['reward'], bool) or not math.isfinite(record['reward'])
                    or not math.isclose(record['reward'], assessment['reward'], rel_tol=1e-9, abs_tol=1e-10)
                    or type(record['hard_satisfied']) is not bool
                    or record['hard_satisfied'] != assessment['hard_satisfied']):
                raise ValueError('Stored reward/feasibility disagrees with measurements')
            action = physical_to_action(record['parameters'], environment)
            normalized = environment.normalize_specs(record['specs'])
            next_state = np.array([normalized[n] for n in environment.dict_targets], dtype=np.float32)
            if not np.isfinite(next_state).all():
                raise ValueError('Non-finite next state')
            replay_buffer.push(state.copy(), action, assessment['reward'], next_state, done)
            already_imported_ids.add(design_id)
            inserted.append(design_id)
        except (ValueError, KeyError, TypeError) as error:
            errors.append({'design_id': record.get('design_id'), 'error': str(error)})
    return {'injected': len(inserted), 'candidate_ids': inserted, 'skipped_duplicates': duplicates,
            'rejected': errors, 'buffer_size': replay_buffer.size}
