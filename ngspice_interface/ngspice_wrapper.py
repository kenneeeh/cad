import os
import re
import yaml
import random
import string
import time 
import shutil
import subprocess
import json
import sys
from pathlib import Path

class NgspiceWrapper(object):
    
    def __init__(self, yaml_path):
        with open(yaml_path, 'r') as f:
            yaml_data = yaml.load(f, Loader=yaml.Loader)
        self.circuit_name = yaml_data['circuit_name']
        self.circuit_multipliers = yaml_data['circuit_multipliers']
        self.technology = yaml_data['technology']
        project_path = os.getcwd()
        self.netlist_path = os.path.join(project_path, 'ngspice_interface', 'files', 'input_netlists', f"{self.circuit_name}.cir")
        self.solutions_folder = os.path.join(project_path, 'no_backup', 'solutions')
        self.output_netlists_folder = os.path.join(project_path, 'no_backup', 'output_netlists')
        self.output_files_folder = os.path.join(project_path, 'no_backup', 'output_files')
        self.param_names = yaml_data['params'].keys()
        self.parameters = {}
        self.read_netlist()
        
    def read_netlist(self):
        with open(self.netlist_path, 'r') as f:
            for line in f:
                if line.startswith(".param"):  # Find parameter lines
                    match = re.search(r"(\w+)=([\w\.]+(?:e[+-]\d+)?)", line)
                    if match:
                        param_name = match.group(1)
                        param_value = match.group(2)
                        units = {'f':1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'meg': 1e6, 'g': 1e9}
                        if param_name in ["trf", "period", "VDD"]:
                            value = None
                            for unit, multiplier in units.items():
                                if unit in param_value:
                                    value = float(param_value.rstrip(unit)) * multiplier
                                    break
                            if value is None:  # If no unit was found, just convert the value to float
                                value = float(param_value)
                            setattr(self, param_name, value)
                        elif param_name in self.param_names:
                            value = None
                            for unit, multiplier in units.items():
                                if unit in param_value:
                                    value = float(param_value.rstrip(unit)) * multiplier
                                    break
                            if value is None:  # If no unit was found, just convert the value to float
                                value = float(param_value)
                            self.parameters[param_name] = value

    def generate_random_name(self, length=10):
        letters = string.ascii_lowercase
        random_string = ''.join(random.choice(letters) for _ in range(length))
        timestamp = str(int(time.time()))
        unique_name = timestamp + "_" + random_string
        return unique_name

    def create_new_netlist(self, parameters=None, process='TT', temp_pvt=None, vdd=None, vcm=None, vhigh=None):
        # Define the new netlist path randomly
        self.random_name = self.circuit_name + f"_{self.generate_random_name()}"
        new_netlist_path = os.path.join(self.output_netlists_folder, self.random_name + ".cir")
        self.circuit_params = parameters
        
        # Open the input netlist and read lines
        with open(self.netlist_path, 'r') as input_file:
            lines = input_file.readlines()
        
        # Modify the lines
        for i, line in enumerate(lines):
            if line.startswith(".param"):  # Find parameter lines
                # Split the line into individual parameter assignments
                param_assignments = re.findall(r"(\w+)=([\w\.]+(?:e[+-]\d+)?)", line)
                new_assignments = []
                for param_name, old_value in param_assignments:
                    if parameters is not None and param_name in parameters:
                        new_value = str(parameters[param_name])
                    elif param_name == "temp_pvt" and temp_pvt is not None:
                        new_value = str(temp_pvt)
                    elif param_name in ["VREF", "ICMV"] and vcm is not None:
                        new_value = str(vcm)
                    elif param_name == "VHIGH" and vhigh is not None:
                        new_value = str(vhigh)
                    elif param_name == "VDD" and vdd is not None:
                        new_value = str(vdd)
                        self.VDD = new_value
                    else:
                        new_value = old_value
                    new_assignments.append(f"{param_name}={new_value}")
                
                # Reconstruct the line with updated values
                lines[i] = ".param " + " ".join(new_assignments) + "\n"
            
            elif line.startswith(".include"):  # Find include lines
                match = re.search(r"(\w+_\w+\.sp)", line)
                if match:
                    old_model_path = match.group(1)
                    new_model_path = re.sub(r"_\w+\.sp", f"_{process}.sp", old_model_path)
                    lines[i] = line.replace(old_model_path, new_model_path)  # Replace the model path
            
            elif line.startswith("wrdata"):  # Find wrdata lines
                match = re.search(r"wrdata (\w+)\.csv", line)
                if match:
                    old_file_name = match.group(1)
                    new_file_name = os.path.join(self.output_files_folder, old_file_name.split('_')[0] + "_" + self.random_name)
                    lines[i] = line.replace(old_file_name, new_file_name)
        
        # Open the new netlist and write lines
        os.makedirs(os.path.dirname(new_netlist_path), exist_ok=True)
        with open(new_netlist_path, 'w') as output_file:
            output_file.writelines(lines)
        
        return new_netlist_path

    def simulate(self, netlist_path):
        # An explicit override also permits a different local ngspice installation.
        executable = os.environ.get('NGSPICE_EXECUTABLE')
        if not executable:
            server_executable = '/users/micas/mahmadza/public/bin/ngspice'
            local_executable = (Path(__file__).resolve().parents[2] / '.tools' /
                                'ngspice' / 'Spice64' / 'bin' / 'ngspice_con.exe')
            if Path(server_executable).is_file():
                executable = server_executable
            else:
                executable = (shutil.which('ngspice_con') or shutil.which('ngspice')
                              or str(local_executable))
        # Argument lists handle spaces in paths without shell quoting or Unix redirection.
        started = time.perf_counter()
        result = None
        self.simulator_attempts = getattr(self, 'simulator_attempts', 0) + 1
        try:
            result = subprocess.run(
                [executable, '-b', os.fspath(netlist_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        finally:
            duration = time.perf_counter() - started
            self.simulator_execution_s = getattr(self, 'simulator_execution_s', 0.) + duration
            if getattr(self, 'audit_path', None):
                event = {'event': 'simulation_attempt', 'simulation_id': Path(netlist_path).stem,
                         'simulation_index': self.simulator_attempts + getattr(self, 'audit_offset', 0),
                         'initiator': getattr(self, 'audit_phase', 'unknown'),
                         'simulator_execution_s': duration,
                         'elapsed_s': time.perf_counter() - float(os.environ.get('CAD_EXPERIMENT_START', getattr(self, 'audit_start', started))),
                         'returncode': result.returncode if result is not None else None}
                try:
                    Path(self.audit_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(self.audit_path, 'a', encoding='utf-8') as output:
                        output.write(json.dumps(event, allow_nan=False) + '\n')
                except OSError as error:
                    print(f'Simulator audit failed: {error}', file=sys.stderr)
        return 0 if result.returncode == 0 else 1
    

    def measure_metrics(self):
        result = None
        return result



if __name__ == "__main__":
    project_path = os.getcwd()
    yaml_path = os.path.join(project_path, 'ngspice_interface', 'files', 'yaml_files', 'TwoStage.yaml')
    parameters = {
        'mp1': 10,
        'wp1': 5.0e-07,
        'lp1': 100.0e-09,
        'mn1': 10,
        'wn1': 5.0e-07,
        'ln1': 100.0e-09,
        'mp3': 10,
        'wp3': 5.0e-07,
        'lp3': 100.0e-09,
        'mn3': 10,
        'wn3': 5.0e-07,
        'ln3': 100.0e-09,
        'mn4': 10,
        'wn4': 5.0e-07,
        'ln4': 100.0e-09,
        'mn5': 10,
        'wn5': 5.0e-07,
        'ln5': 100.0e-09,
        'cap': 5.0e-12,
        'res': 5.0e+3
    }
    process = "TT"
    temp_pvt = 27
    vdd = 1.2
    ngspice_wrapper = NgspiceWrapper(yaml_path)
    
    new_netlist_path = ngspice_wrapper.create_new_netlist(parameters, process, temp_pvt, vdd)
    info = ngspice_wrapper.simulate(new_netlist_path)
    print(f"New netlist created at: {new_netlist_path}")
    print("info:", info)
    print("trf:", ngspice_wrapper.trf)
    print("period:", ngspice_wrapper.period)
    print("VDD:", ngspice_wrapper.VDD)
