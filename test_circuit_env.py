import csv
import os
import sys
import unittest

import numpy as np

# CircuitEnv uses the current directory as the project root, so always run from CAD/
CAD_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(CAD_DIR)
sys.path.insert(0, CAD_DIR)

from circuit_env import CircuitEnv

REFERENCES_CSV = os.path.join(CAD_DIR, "references.csv")
EXACT_TOL = 1e-6      # for the pure computations (no simulation)
SPEC_REL_TOL = 0.05   # simulated specs must be within 5% of the reference
NORM_ABS_TOL = 0.05   # normalized specs / reward after simulation


def load_references():
    """Return {design name: {attribute: value}} from references.csv."""
    with open(REFERENCES_CSV) as f:
        rows = list(csv.reader(f))
    designs = rows[0][2:]
    refs = {d: {} for d in designs}
    for row in rows[1:]:
        for d, value in zip(designs, row[2:]):
            refs[d][row[0]] = float(value)
    return refs


def pick(ref, prefix):
    """{name: value} for all attributes starting with prefix (prefix stripped)."""
    return {k[len(prefix):]: v for k, v in ref.items() if k.startswith(prefix)}


class TestCircuitEnv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = CircuitEnv(circuit_name="TwoStage_test", run_id="unit_test")  # frozen yaml copy for tests
        cls.refs = load_references()

    def action_vector(self, ref):
        # action order follows the parameter order in the YAML file
        actions = pick(ref, "action_")
        return np.array([actions[name] for name in self.env.param_ranges])

    def test_action_refine(self):
        for design, ref in self.refs.items():
            with self.subTest(design=design):
                params = self.env.action_refine(self.action_vector(ref))
                for name, expected in pick(ref, "param_").items():
                    self.assertAlmostEqual(params[name], expected, delta=EXACT_TOL * abs(expected),
                                           msg=f"{design} {name}")

    def test_normalize_specs(self):
        for design, ref in self.refs.items():
            with self.subTest(design=design):
                norm = self.env.normalize_specs(pick(ref, "spec_"))
                for name, expected in pick(ref, "norm_").items():
                    self.assertAlmostEqual(norm[name], expected, delta=EXACT_TOL, msg=f"{design} {name}")

    def test_reward_computation(self):
        for design, ref in self.refs.items():
            with self.subTest(design=design):
                reward, _ = self.env.reward_computation(pick(ref, "norm_"))
                self.assertAlmostEqual(reward, ref["reward"], delta=EXACT_TOL, msg=design)

    def test_evaluate(self):
        """Full pipeline: action -> params -> simulation -> specs -> normalized specs -> reward."""
        for design, ref in self.refs.items():
            with self.subTest(design=design):
                self.env.evaluate(self.action_vector(ref))
                print(design, self.env.real_specs)

                for name, expected in pick(ref, "spec_").items():
                    self.assertAlmostEqual(self.env.real_specs[name], expected,
                                           delta=SPEC_REL_TOL * abs(expected), msg=f"{design} {name}")

                for name, expected in pick(ref, "norm_").items():
                    self.assertAlmostEqual(self.env.cur_norm_specs[name], expected,
                                           delta=NORM_ABS_TOL, msg=f"{design} {name}")

                reward, _ = self.env.reward_computation(self.env.cur_norm_specs)
                self.assertAlmostEqual(reward, ref["reward"], delta=NORM_ABS_TOL, msg=design)


if __name__ == "__main__":
    unittest.main()
