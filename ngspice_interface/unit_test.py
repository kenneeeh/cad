import csv
import os
import shutil
import sys
import unittest

# NgspiceWrapper uses the current directory as the project root, so always run from CAD/
CAD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(CAD_DIR)
sys.path.insert(0, CAD_DIR)

from ngspice_interface import DUT

YAML_PATH = os.path.join("ngspice_interface", "files", "yaml_files", "TwoStage_test.yaml")  # frozen copy for tests
NGSPICE = shutil.which("ngspice") or "/users/micas/mahmadza/public/bin/ngspice"

# default sizes from TwoStage.cir (a design must contain all 20 parameters)
DEFAULT_PARAMS = {
    "wp1": 0.5e-6, "lp1": 90e-9, "mp1": 10,
    "wn1": 0.5e-6, "ln1": 90e-9, "mn1": 38,
    "wn3": 0.5e-6, "ln3": 90e-9, "mn3": 9,
    "wp3": 0.5e-6, "lp3": 90e-9, "mp3": 4,
    "wn4": 0.5e-6, "ln4": 90e-9, "mn4": 20,
    "wn5": 0.5e-6, "ln5": 90e-9, "mn5": 60,
    "cap": 3e-12, "res": 1e3,
}

REFERENCES_CSV = os.path.join(CAD_DIR, "references.csv")
SPEC_REL_TOL = 0.05  # simulated specs must be within 5% of the reference


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


class TestDUT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dut = DUT(YAML_PATH)

    def simulate(self, params=DEFAULT_PARAMS, temp_pvt=None):
        """Simulate one design and return its spec dict."""
        netlist = self.dut.create_new_netlist(params, temp_pvt=temp_pvt)
        exit_code = os.system(f"{NGSPICE} -b {netlist} > /dev/null 2>&1")
        self.assertEqual(exit_code, 0, f"ngspice failed on {netlist}")
        return self.dut.measure_metrics()

    def test_default_design(self):
        specs = self.simulate()
        print(specs)
        # TODO: compare against reference_designs.csv, e.g.
        # self.assertAlmostEqual(specs["gain"], ref["gain"], delta=0.01 * ref["gain"])

        # TODO: super slow slew rate waar ge niet tot max vout haalt
        # TODO: als dc gain altijd laag, dan ugbw moet nul zijn
        # TODO: phase margin als dc laag
        # TODO: ugbw, wat als multiple crossings (brakka grafiek)
        # TODO: phase margin, wat als multiple crossings (brakka grafiek)

    def test_reference_designs(self):
        for design, ref in load_references().items():
            with self.subTest(design=design):
                params = {k[len("param_"):]: v for k, v in ref.items() if k.startswith("param_")}
                specs = self.simulate(params, temp_pvt=27)  # references use the env corner: TT, 27C, 1.2V
                print(design, specs)
                for name, value in specs.items():
                    expected = ref["spec_" + name]
                    self.assertAlmostEqual(value, expected, delta=SPEC_REL_TOL * abs(expected),
                                           msg=f"{design} {name}")



if __name__ == "__main__":
    unittest.main()


