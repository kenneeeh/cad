import matplotlib.pyplot as plt
import numpy as np
from typing import List, Dict
import pandas as pd

def plotLearning(scores, run_id):
    filename = f'./output_figs/{run_id}/average_score.png'
    N = len(scores)
    # Calculate the running average of scores
    running_avg = np.zeros(N)
    for t in range(N):
        running_avg[t] = np.mean(scores[max(0, t-N):(t+1)])

    # change the font size
    plt.rcParams.update({'font.size': 18})
    plt.ylabel('Episode Scores')       
    plt.xlabel('# Episode')                     
    plt.plot(range(N), running_avg, label='Running Avg')
    plt.plot(range(N), scores, alpha=0.5, label='Scores')  # Optionally overlay the raw scores
    plt.legend()
    plt.grid('on')
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

# display name, scale factor and unit for each spec (used in the FoM plot legend)
SPEC_FORMAT = {
    'area':     ('Area',         1e12, 'µm²'),
    'current':  ('Current',      1e6,  'µA'),
    'gain':     ('Gain',         1,    'V/V'),
    'noise':    ('Noise',        1e3,  'mV RMS'),
    'phm':      ('Phase margin', 1,    '°'),
    'slewRate': ('Slew rate',    1,    'V/µs'),
    'ugbw':     ('UGBW',         1e-6, 'MHz'),
}


def plot_running_maximum(data, run_id, best_specs=None, targets=None):
    file_name = f'./output_figs/{run_id}/max_reward.png'
    running_max = float('-inf')  # Initialize running maximum to negative infinity
    running_max_values = []

    for value in data:
        if value > running_max:
            running_max = value
        running_max_values.append(running_max)

    # change the font size
    plt.rcParams.update({'font.size': 18})
    plt.plot(running_max_values)
    plt.xlabel('# Simulation')
    plt.ylabel('Maximum FoM Reached')
    plt.grid(True)

    # legend box (right of the plot) with the specs of the best design so far
    if best_specs is not None:
        lines = [f'Best FoM = {running_max:.3f}', '']
        for name, value in best_specs.items():
            label, scale, unit = SPEC_FORMAT.get(name, (name, 1, ''))
            line = f'{label:<13}{value * scale:>9.4g} {unit:<7}'
            if targets is not None and name in targets:
                line += f' (target {targets[name] * scale:.4g})'
            lines.append(line)
        plt.gca().text(1.03, 1.0, '\n'.join(lines), transform=plt.gca().transAxes,
                       va='top', family='monospace', fontsize=12,
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))

    plt.savefig(file_name, bbox_inches='tight')
    plt.close()
    

def is_pareto_efficient(costs: np.ndarray) -> np.ndarray:
    is_efficient = np.ones(costs.shape[0], dtype=bool)
    for i, c in enumerate(costs):
        if is_efficient[i]:
            is_efficient[is_efficient] = np.any(costs[is_efficient] < c, axis=1)
            is_efficient[i] = True
    return is_efficient

def plot_pareto_front(solutions: List[Dict[str, float]], fname, show_all=False) -> None:
    current_scaled = [sol['current']*1e+6 for sol in solutions] # --> convert to μA
    area_scaled = [sol['area']*1e12 for sol in solutions] # --> convert to μm²

    combined_objectives = np.vstack((area_scaled, current_scaled)).T
    pareto_optimal_indices = is_pareto_efficient(combined_objectives)
    
    pareto_optimal_points = combined_objectives[pareto_optimal_indices]
    pareto_area = pareto_optimal_points[:, 0]
    pareto_current = pareto_optimal_points[:, 1]

    # change the font size
    plt.rcParams.update({'font.size': 18})

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(pareto_area, pareto_current, c='blue', s=100, label='Pareto Front')
    if show_all:
        ax.scatter(area_scaled, current_scaled, c='gray', alpha=0.6, s=100, label='Non-Pareto Solutions')
    
    sorted_indices = np.argsort(pareto_area)
    ax.plot(pareto_area[sorted_indices], pareto_current[sorted_indices], 'b--', linewidth=2)
    
    ax.set_xlabel('Active Area (μm²)', fontsize=18)
    ax.set_ylabel('Total Current (μA)', fontsize=18)

    # show grids for both x and y axis
    ax.grid(True, linestyle='--', alpha=0.7, which='both')

    
    plt.tight_layout()
    plt.savefig(fname, dpi=300, bbox_inches='tight')
    plt.close()


def solutions2pareto(csv_fname, run_id, show_all=False):
    plot_fname = f'./output_figs/{run_id}/pareto.png'
    df = pd.read_csv(csv_fname)
    solutions = df['Specs'].apply(eval).tolist()
    plot_pareto_front(solutions, plot_fname, show_all)