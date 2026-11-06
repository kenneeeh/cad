"""TwoStage-specific metadata/validation around the existing CircuitEnv; no new simulator."""
import hashlib
import math
from pathlib import Path


def setup_id(repo):
    """Current rising-edge TwoStage setup; only YAML changes are detected automatically."""
    yaml = Path(repo) / 'ngspice_interface/files/yaml_files/TwoStage.yaml'
    return 'TwoStage-rising-' + hashlib.sha256(yaml.read_bytes()).hexdigest()[:12]


class CircuitAdapter:
    def __init__(self, env, repo):
        self.env = env
        self.repo = Path(repo)
        self.units = {'area': 'm^2', 'current': 'A', 'gain': 'V/V', 'noise': 'V RMS',
                      'phm': 'deg', 'slewRate': 'V/us', 'ugbw': 'Hz'}
        self.parameter_units = {name: ('m' if name.startswith(('w', 'l')) else
                                      'F' if name == 'cap' else 'ohm' if name == 'res' else '1')
                                for name in env.dict_params}
        self.directions = {name: '<=' if name == 'noise' else '>=' for name in env.hard_constraints}

    def validate_parameters(self, parameters):
        expected = set(self.env.dict_params)
        if set(parameters) != expected:
            raise ValueError(f'Parameter names: missing={sorted(expected-set(parameters))}, extra={sorted(set(parameters)-expected)}')
        for name, (minimum, maximum, step) in self.env.dict_params.items():
            value = parameters[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{name} must be a finite number')
            if not minimum <= value <= maximum:
                raise ValueError(f'{name} must be within [{minimum:g}, {maximum:g}]')
            position = (value - minimum) / step
            if not math.isclose(position, round(position), rel_tol=0, abs_tol=1e-7):
                raise ValueError(f'{name} must equal {minimum:g} + k*{step:g} for integer k')

    def assess(self, specs):
        if set(specs) != set(self.env.dict_targets):
            raise ValueError('Expected exactly seven measured specifications')
        for name, value in specs.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Invalid measurement: {name}')
        try:
            normalized = self.env.normalize_specs(specs)
        except (ZeroDivisionError, FloatingPointError):
            raise ValueError('Undefined normalized specification') from None
        if not all(math.isfinite(value) for value in normalized.values()):
            raise ValueError('Non-finite normalized specification')
        reward, feasible = self.env.reward_computation(normalized)
        if not math.isfinite(reward):
            raise ValueError('Non-finite reward')
        violated = [name for name, direction in self.directions.items()
                    if (specs[name] > self.env.dict_targets[name] if direction == '<='
                        else specs[name] < self.env.dict_targets[name])]
        if bool(feasible) != (not violated):
            raise ValueError('Reward feasibility disagrees with physical hard constraints')
        return {'specs': {name: float(value) for name, value in specs.items()},
                'units': self.units, 'reward': float(reward), 'hard_satisfied': bool(feasible),
                'violated_constraints': violated}

    def context(self):
        return {'problem_id': setup_id(self.repo), 'circuit': 'TwoStage'}

    def problem(self, context):
        return {**context,
                'parameters': {name: [*bounds, self.parameter_units[name]] for name, bounds in self.env.dict_params.items()},
                'parameter_format': '[minimum, maximum, step, unit]; absolute physical values',
                'hard_targets': {name: [direction, self.env.dict_targets[name], self.units[name]]
                                 for name, direction in self.directions.items()},
                'optimization_targets': {name: ['minimize', self.env.dict_targets[name], self.units[name]]
                                         for name in self.env.optimization_targets},
                'reward': {'implementation': 'CircuitEnv.normalize_specs/reward_computation',
                           'spec_weights': self.env.spec_weights, 'success_threshold': self.env.success_threshold,
                           'convention': 'Maximize returned reward. Feasibility separately requires all hard targets; a positive reward alone does not imply feasibility.'},
                'operations': ['simulate_design: full parameters', 'evaluate_candidate: base ID plus absolute changes']}
