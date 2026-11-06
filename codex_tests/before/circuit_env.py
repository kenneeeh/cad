import gymnasium as gym
from gymnasium.spaces import Box
import numpy as np
import os
import yaml
import math
from ngspice_interface import DUT as DUT_NGSpice
from utils.plotting import plotLearning, plot_running_maximum

class CircuitEnv(gym.Env):
    PER_LOW, PER_HIGH = -np.inf, +np.inf
    
    def __init__(self, config=None, circuit_name='TwoStage', run_id='rllib_baseline',
                 success_threshold=0.0, simulator='ngspice'):
        self.run_id = run_id
        self.max_steps_per_episode = 10
        self.env_steps = 0
        self.episode_steps = 0
        self.success_threshold = success_threshold
        self.circuit_name = circuit_name

        project_path = os.getcwd()
        yaml_directory = os.path.join(project_path, f"{simulator}_interface", 'files', 'yaml_files')
        circuit_yaml_path = os.path.join(yaml_directory, f'{circuit_name}.yaml')
        with open(circuit_yaml_path, 'r') as f:
            yaml_data = yaml.load(f, Loader=yaml.Loader)
        
        self.dict_params = yaml_data['params']
        self.dict_targets = yaml_data['targets']

        self.hard_constraints = yaml_data['hard_constraints']
        self.optimization_targets = yaml_data['optimization_targets']

        # number of input action components
        self.n_actions = len(self.dict_params)

        # number of output observation components
        self.obs_dim = len(self.dict_targets)

        self.param_ranges = {}
        for name, value in self.dict_params.items():
           self.param_ranges[name] = {'min': value[0], 'max': value[1], 'step': value[2]}
        
        self.simulation_engine = DUT_NGSpice(circuit_yaml_path)

        print(f"\n Initialized {circuit_name} with simulator {simulator} \n")

        # Action space & Observation space
        act_high = np.array([1 for _ in range(self.n_actions)])
        act_low = np.array([-1 for _ in range(self.n_actions)])
        self.action_space = Box(low=act_low, high=act_high)
        obs_high = np.array([CircuitEnv.PER_HIGH]*self.obs_dim, dtype=np.float32)
        obs_low = np.array([CircuitEnv.PER_LOW]*self.obs_dim, dtype=np.float32)
        self.observation_space = Box(low=obs_low, high=obs_high)

        # spec reward weights
        self.spec_weights = yaml_data['spec_weights']

        self.reward_history = []
        self.score_history = []

        self.counter = 0
        self.pvt_corner = {'process': 'TT', 'voltage': 1.2, 'temp': 27}
    
    
    def action_refine(self, action):
        params = {}

        for i, (name, bounds) in enumerate(self.param_ranges.items()):
            minimum = bounds["min"]
            maximum = bounds["max"]
            step = bounds["step"]

            a = np.clip(action[i], -1, 1)

            value = minimum + (a + 1) / 2 * (maximum - minimum)

            value = minimum + round((value - minimum) / step) * step

            params[name] = float(np.clip(value, minimum, maximum))

        return params

    
    def simulate(self, params):
        """
        Create/Simulate netlist with the given parameters and return the measured metrics.

        Args:
            params (dict): A dictionary containing the parameters for the simulation.

        Returns:
            dict: A dictionary containing the measured metrics from the simulation.
        """
        netlist_path = self.simulation_engine.create_new_netlist(
            parameters=params,
            process=self.pvt_corner["process"],
            temp_pvt=self.pvt_corner["temp"],
            vdd=self.pvt_corner["voltage"]
        )

        info = self.simulation_engine.simulate(netlist_path)

        if info != 0:
            raise RuntimeError("ngspice simulation failed")

        specs = self.simulation_engine.measure_metrics()

        return specs

    
    
    def normalize_specs(self, spec_dict):
        normalized = {}

        for name, value in spec_dict.items():
            target = self.dict_targets[name]
            normalized[name] = (value - target) / (value + target)

        return normalized

    
    def evaluate(self, action):
        self.param_values = self.action_refine(action)
        self.real_specs = self.simulate(self.param_values)
        self.cur_norm_specs = self.normalize_specs(self.real_specs)
    
    def reset(self, *, seed=None, options=None):
        """
         Reset the environment to an initial state and return the initial observation.

        Parameters:
            No mandatory input parameters (leave the input signature as is).
            seed (int, optional): A seed for the random number generator to ensure reproducibility.
            options (dict, optional): Additional options for the reset process.

        Returns:
            np.ndarray: The initial observation of the environment, which is the normalized current specifications.

        This method performs the following steps:
        1. Initializes the episode steps counter to zero.
        2. Generates a random action within the range [-1, 1] for each action parameter.
        3. Evaluates the environment with the generated random action.
        4. Resets the episode score to zero.
        5. Constructs the initial observation by returning the normalized current specifications.

        Note:
        - The observation is returned as a NumPy array of type float32.
        """
        super().reset(seed=seed)

        self.episode_steps = 0

        action = self.action_space.sample()

        self.evaluate(action)
            
        self.score = 0.0

        ob = np.array(
            list(self.cur_norm_specs.values()),
            dtype=np.float32
        )

        return ob

    
    def step(self, action):
        """
         Perform a single step in the environment using the given action.

        This function should:
        1. Evaluate the given action.
        2. Compute the reward and check if the hard constraints are satisfied.
        3. Update the current observation.
        4. Append the reward to the reward history and update the score.
        5. Create output directories if they do not exist.
        6. If the goal state is reached, plot the running maximum reward.
        7. Increment the environment and episode step counters.
        8. Check if the maximum steps per episode have been reached, setting the done flag if true.
        9. Every 10 steps, update the score history, also plot the learning curve, and reset the score.
        10. Return the current observation, reward, done flag, and additional information.

        Args:
            action: The action to be taken in the environment. An array of values between -1 and 1.

        Returns:
            tuple: A tuple containing:
            - ob (np.ndarray): The current observation of the environment.
            - reward (float): The reward obtained from taking the action.
            - done (bool): A flag indicating whether the episode has ended.
            - info (dict): Additional information, including whether the goal state was reached.
        """
        self.evaluate(action)

        reward, hard_satisfied = self.reward_computation(
            self.cur_norm_specs
        )

        ob = np.array(
            list(self.cur_norm_specs.values()),
            dtype=np.float32
        )

        self.reward_history.append(reward)
        self.score += reward

        output_dir = f"./output_figs/{self.run_id}"
        os.makedirs(output_dir, exist_ok=True)

        if hard_satisfied:
            plot_running_maximum(
                self.reward_history, self.run_id
            )

        self.env_steps += 1
        self.episode_steps += 1

        done = self.episode_steps >= self.max_steps_per_episode

        if self.episode_steps % 10 == 0:
            self.score_history.append(self.score)
            plotLearning(self.score_history, self.run_id)
            self.score = 0.0

        info = {"hard_satisfied": hard_satisfied}

        return ob, reward, done, info

    
    def reward_computation(self, norm_specs):
        """
        Compute the reward based on normalized specifications and hard constraints.

        Args:
            norm_specs (dict): A dictionary containing normalized specifications.

        Returns:
            tuple: A tuple containing:
            - reward (float): The computed reward value.
            - hard_satisfied (bool): A boolean indicating whether the hard constraints are satisfied.

        The function performs the following steps:
        1. Initialize the reward to 0.0 and hard_satisfied to False.
        2. Iterate over the hard constraints and adjust the reward based on the specifications.
        3. Check if all hard constraints are satisfied or the total reward passes the success threshold of 0.
            - If so, set hard_satisfied to True, add a bonus reward (+0.3), and adjust the reward based on optimization targets.
            - If not, add weighted reward components of the optimization targets.
        4. Return the computed reward and the hard_satisfied flag.
        """
        
        #hard constraints reward
        reward = 0.0

        for spec in self.hard_constraints:
            value = norm_specs[spec]

            if spec == "noise":
                penalty = -max(value, 0) #kleiner is beter
            else:
                penalty = min(value, 0)

            reward += self.spec_weights[spec] * penalty #allemaal 1.0

        hard_satisfied = reward >= self.success_threshold

        # Optimization reward
        r_targets = 0.0

        for spec in self.optimization_targets:
            r_targets -= self.spec_weights[spec] * norm_specs[spec]

        if hard_satisfied:
            reward += 0.3 + r_targets
        else:
            reward += 0.05 * r_targets #in slide 46

        return float(reward), bool(hard_satisfied)



if __name__ == '__main__':
    env = CircuitEnv(
        circuit_name='TwoStage', 
        run_id=0, 
        simulator='ngspice', 
        success_threshold=0.0
        )
    print(env.action_space)
    print(env.observation_space)

    ob = env.reset()
    print("Initial observation: ", ob)
    print("Initial parameters: ", env.param_values)
    print("Initial specs: ", env.real_specs)

    action = np.random.uniform(-1, 1, [env.n_actions])
    ob, reward, done, info = env.step(action)
    print("Next parameters: ", env.param_values)
    print("Next observation: ", ob)
    print("Next specs: ", env.real_specs)
    print("Reward: ", reward)
    print("Done: ", done)
