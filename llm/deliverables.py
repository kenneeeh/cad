"""Deliverable plots and Solutions folder for one run, using the existing plotting functions."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import numpy as np
import yaml
from candidates import CandidateArchive
from circuit_adapter import setup_id

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # utils.plotting lives at the repository root.
YAML = REPO / 'ngspice_interface/files/yaml_files/TwoStage.yaml'


def write_deliverables(archive_path, run_dir, run_id, exclude_ids=frozenset()):
    """Write max_reward.png and pareto.png under output_figs/run_id and run_dir/Solutions.

    The x axis of the FoM plot counts every archived simulation in execution order,
    whether it came from the LLM or from TD3.
    """
    run_dir = Path(run_dir).resolve()
    records = CandidateArchive(Path(archive_path).resolve(), setup_id(REPO)).records()
    records = [r for r in records if r['design_id'] not in exclude_ids]
    records.sort(key=lambda r: r['metadata'].get('cumulative_simulation_count', 0))
    if not records:
        return
    previous_directory = os.getcwd()
    os.chdir(REPO)  # utils.plotting writes to ./output_figs relative to the repository.
    try:
        from utils.plotting import plot_running_maximum, solutions2pareto
        (REPO / 'output_figs' / run_id).mkdir(parents=True, exist_ok=True)
        best = max(records, key=lambda r: r['reward'])
        targets = yaml.load(YAML.read_text(), Loader=yaml.FullLoader)['targets']
        plot_running_maximum([r['reward'] for r in records], run_id, best_specs=best['specs'], targets=targets)
        pareto = pareto_solutions([r for r in records if r['hard_satisfied']])
        if pareto:
            solutions_dir = run_dir / 'Solutions'
            csv_path = write_solutions(pareto, solutions_dir)
            copy_netlists(pareto, run_dir, solutions_dir)
            solutions2pareto(csv_path, run_id)
    finally:
        os.chdir(previous_directory)


def pareto_solutions(feasible):
    from utils.plotting import is_pareto_efficient
    if not feasible:
        return []
    costs = np.array([[r['specs']['area'], r['specs']['current']] for r in feasible])
    return [r for r, efficient in zip(feasible, is_pareto_efficient(costs)) if efficient]


def write_solutions(pareto, solutions_dir):
    """One netlist per Pareto design plus solutions.csv (parameters, specs, FoM)."""
    solutions_dir.mkdir(parents=True, exist_ok=True)
    csv_path = solutions_dir / 'solutions.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['Design', 'Source', 'Parameters', 'Specs', 'Reward'])
        for record in pareto:
            writer.writerow([record['design_id'], record['source'], record['parameters'],
                             record['specs'], record['reward']])
    return csv_path


def copy_netlists(pareto, run_dir, solutions_dir):
    simulation_ids = {r['metadata']['simulation_id']: r['design_id'] for r in pareto}
    for netlist in Path(run_dir).glob('session_*/**/netlists/*.cir'):
        if netlist.stem in simulation_ids:
            shutil.copy(netlist, solutions_dir / f'{simulation_ids[netlist.stem]}.cir')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path, help='run folder containing candidates.jsonl')
    args = parser.parse_args()
    write_deliverables(args.run_dir / 'candidates.jsonl', args.run_dir, args.run_dir.name)


if __name__ == '__main__':
    main()
