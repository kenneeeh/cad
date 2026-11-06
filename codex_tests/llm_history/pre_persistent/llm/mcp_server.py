"""Four MCP tools for the current TwoStage opamp."""
from contextlib import redirect_stdout
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
from candidates import CandidateArchive, apply_changes, compact

os.chdir(REPO)  # CircuitEnv/netlist include paths use the repository directory.
with redirect_stdout(sys.stderr):  # stdout is reserved for MCP messages.
    env = CircuitEnv()
env.simulation_engine.output_netlists_folder = str(RUN / 'netlists')
env.simulation_engine.output_files_folder = str(RUN / 'outputs')
adapter = CircuitAdapter(env, REPO)
context = adapter.context()
archive = CandidateArchive(os.environ.get('CAD_ARCHIVE_PATH', str(RUNS / 'candidates.jsonl')), context['problem_id'])
initial_reference = json.loads((HERE / 'initial_design.json').read_text())
MAX_SIMULATIONS = int(os.environ.get('CAD_MAX_SIMULATIONS', '5'))
if MAX_SIMULATIONS < 0:
    raise ValueError('CAD_MAX_SIMULATIONS must be nonnegative')
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
lock = RLock()  # ID lookup and simulation share the same lock and counter.
mcp = MCPServer('cad-simulator', instructions='Use get_problem/get_candidates; test absolute changes with evaluate_candidate. Only the coordinator may simulate.')


def _evaluate(parameters, hypothesis, parent_id=None):
    with lock:
        try:
            if not isinstance(hypothesis, str) or len(hypothesis) > 300:
                raise ValueError('hypothesis must be a string of at most 300 characters')
            adapter.validate_parameters(parameters)
        except (ValueError, TypeError) as error:
            return {'success': False, 'error': str(error), 'simulation_count': env.counter}
        if env.counter >= MAX_SIMULATIONS:
            return {'success': False, 'error': 'Simulation budget exhausted', 'simulation_count': env.counter, 'remaining': 0}
        started = perf_counter()
        try:
            with redirect_stdout(sys.stderr):
                assessment = adapter.assess(env.simulate(parameters))
            source = 'initial reference' if parent_id is None and parameters == initial_reference else 'LLM'
            candidate = archive.add(parameters, assessment, source, os.environ.get('CAD_RUN_ID', RUN.name),
                {'completed': True, 'simulator': 'ngspice', 'simulation_id': env.simulation_engine.random_name,
                 'simulation_count': env.counter}, parent_id, hypothesis)
            result = {'success': True, 'design_id': candidate['design_id'],
                      **{key: assessment[key] for key in ('specs', 'reward', 'hard_satisfied', 'violated_constraints')}}
        except (OSError, RuntimeError, ValueError, TypeError, KeyError, IndexError) as error:
            result = {'success': False, 'hard_satisfied': False, 'error': str(error)}
        result.update(simulation_count=env.counter, remaining=MAX_SIMULATIONS-env.counter,
                      simulation_id=getattr(env.simulation_engine, 'random_name', None),
                      runtime_s=round(perf_counter()-started, 4))
        # Successful data lives once in candidates.jsonl; this small log also records failed attempts.
        audit = {'result': {key: result[key] for key in
                 ('success', 'design_id', 'simulation_count', 'simulation_id', 'runtime_s', 'error') if key in result}}
        if not result['success']:
            audit.update(parameters=parameters, hypothesis=hypothesis)
        with (RUN / 'calls.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps(audit, allow_nan=False) + '\n')
        return result


@mcp.tool(structured_output=True)
def get_problem() -> dict[str, Any]:
    """Read physical grids/units, targets, reward convention and remaining budget. No simulation."""
    return {**adapter.problem(context), 'simulation_count': env.counter, 'remaining': MAX_SIMULATIONS-env.counter}


@mcp.tool(structured_output=True)
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
def simulate_design(parameters: dict[str, Number],
                    hypothesis: Annotated[str, Field(max_length=300)] = '') -> dict[str, Any]:
    """Evaluate all physical parameters once. Use get_problem for names, units and grids."""
    return _evaluate(parameters, hypothesis)


@mcp.tool(structured_output=True)
def evaluate_candidate(base_design_id: str, changes: dict[str, Number],
                       hypothesis: Annotated[str, Field(max_length=300)] = '') -> dict[str, Any]:
    """Copy a measured base and evaluate absolute changed values using the same budget."""
    with lock:
        try:
            parameters, actual = apply_changes(archive.get(base_design_id)['parameters'], changes)
        except ValueError as error:
            return {'success': False, 'error': str(error), 'simulation_count': env.counter}
        result = _evaluate(parameters, hypothesis, base_design_id)
        result.update(parent_id=base_design_id, changes=actual)
        return result


if __name__ == '__main__':
    mcp.run(transport='stdio')
