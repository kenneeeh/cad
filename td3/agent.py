import copy
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


class Actor(nn.Module):
    def __init__(self, state_dim, action_dim, max_action):
        super(Actor, self).__init__()

        self.l1 = nn.Linear(state_dim, 256)
        self.l2 = nn.Linear(256, 256)
        self.l3 = nn.Linear(256, action_dim)

        self.max_action = max_action


    def forward(self, state):
        a = F.relu(self.l1(state))
        a = F.relu(self.l2(a))
        return self.max_action * torch.tanh(self.l3(a))


class Critic(nn.Module):
    def __init__(self, state_dim, action_dim):
        super(Critic, self).__init__()

        # Q1 architecture
        self.l1 = nn.Linear(state_dim + action_dim, 256)
        self.l2 = nn.Linear(256, 256)
        self.l3 = nn.Linear(256, 1)

        # Q2 architecture
        self.l4 = nn.Linear(state_dim + action_dim, 256)
        self.l5 = nn.Linear(256, 256)
        self.l6 = nn.Linear(256, 1)


    def forward(self, state, action):
        sa = torch.cat([state, action], 1)

        q1 = F.relu(self.l1(sa))
        q1 = F.relu(self.l2(q1))
        q1 = self.l3(q1)

        q2 = F.relu(self.l4(sa))
        q2 = F.relu(self.l5(q2))
        q2 = self.l6(q2)
        return q1, q2


    def Q1(self, state, action):
        sa = torch.cat([state, action], 1)

        q1 = F.relu(self.l1(sa))
        q1 = F.relu(self.l2(q1))
        q1 = self.l3(q1)
        return q1


class TD3(object):
    def __init__(self, state_dim, action_space, args):
        self.max_action = float(action_space.high[0])
        self.discount = args.gamma
        self.tau = args.tau
        self.policy_noise = 0.2
        self.noise_clip = 0.5
        self.expl_noise = args.noise_sigma
        self.policy_freq = args.actor_update_interval

        self.action_dim = action_space.shape[0]
        self.actor = Actor(state_dim, self.action_dim, self.max_action).to(device)
        self.actor_target = copy.deepcopy(self.actor)
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=args.pi_lr)

        self.critic = Critic(state_dim, self.action_dim).to(device)
        self.critic_target = copy.deepcopy(self.critic)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=args.q_lr)

        self.total_it = 0


    def select_action(self, state):
        """
        TODO: Implement the action selection mechanism for the TD3 agent

        Steps to implement:
        1. Convert the state to a tensor if it's a numpy array or CPU tensor
        2. Get the deterministic action from the actor network (mu)
        3. Add "exploration noise" using np.random.normal with:
           - mean = 0
           - std = self.max_action * self.expl_noise
           - size = self.action_dim
        4. Clip the final action to be between -self.max_action and self.max_action
        5. Return the action as a numpy array

        Args:
            state: The current state observation (numpy array or tensor)

        Returns:
            action: The selected action as a numpy array
        """
        with torch.no_grad():
            action = self.actor(torch.FloatTensor(state).to(device)).cpu().numpy()
            noise = np.random.normal(0, self.max_action * self.expl_noise, size=self.action_dim)
            return np.clip(action + noise, -self.max_action, self.max_action)




    def update_parameters(self, memory_batch, update):
        self.total_it += 1
        (state, action, next_state, reward, not_done) = memory_batch

        with torch.no_grad():
            action_noise = (torch.randn_like(action) * self.policy_noise).clamp(-self.noise_clip, self.noise_clip)
            target_action = (self.actor_target.forward(next_state) + action_noise).clamp(-self.max_action, self.max_action)
            target_q1, target_q2 = self.critic_target.forward(next_state, target_action)
            td_target = reward + self.discount * not_done * torch.min(target_q1, target_q2)

        q1, q2 = self.critic.forward(state, action)
        loss = F.mse_loss(q1, td_target) + F.mse_loss(q2, td_target)

        self.critic_optimizer.zero_grad()
        loss.backward()
        self.critic_optimizer.step()

        #delayed policy update
        if self.total_it % self.policy_freq == 0:
            actor_loss = -self.critic.Q1(state, self.actor(state)).mean()
            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            self.actor_optimizer.step()

            #Polyyak averaging
            with torch.no_grad():
                for p, p_targ in zip(self.critic.parameters(), self.critic_target.parameters()):
                    p_targ.mul_(1 - self.tau).add_(self.tau * p)
                for p, p_targ in zip(self.actor.parameters(), self.actor_target.parameters()):
                    p_targ.mul_(1 - self.tau).add_(self.tau * p)

        """
        TODO: Implement the TD3 learning algorithm

        Steps to implement:
        1. Increment total_it counter
        2. Unpack the memory_batch tuple into state, action, next_state, reward, not_done

        3. Compute target actions (with torch.no_grad()):
           - Add clipped "policy noise" to target policy
           - Get next actions from target actor network
           - Clip target actions to valid range

        4. Compute target Q-values (with torch.no_grad()):
           - Get Q-values from both target critics
           - Take the minimum of both Q-values
           - Compute TD target using reward + discount * min Q-value * not_done

        5. Compute current Q-values and critic loss:
           - Get current Q-values from both critics
           - Compute MSE loss between current and target Q-values for both critics

        6. Update critics:
           - Zero gradients
           - Backpropagate critic loss
           - Optimize critic

        7. Delayed policy update (if total_it % policy_freq == 0):
           - Compute actor loss using first critic's Q-values
           - Update actor
           - Update target networks using soft update (τ)

        Args:
            memory_batch: Tuple of (state, action, next_state, reward, not_done) tensors
            update: Update step (not used in this implementation)
        """


    def save(self, filename):
        torch.save(self.critic.state_dict(), filename + "_critic")
        torch.save(self.critic_optimizer.state_dict(), filename + "_critic_optimizer")

        torch.save(self.actor.state_dict(), filename + "_actor")
        torch.save(self.actor_optimizer.state_dict(), filename + "_actor_optimizer")


    def load(self, filename):
        self.critic.load_state_dict(torch.load(filename + "_critic"))
        self.critic_optimizer.load_state_dict(torch.load(filename + "_critic_optimizer"))
        self.critic_target = copy.deepcopy(self.critic)

        self.actor.load_state_dict(torch.load(filename + "_actor"))
        self.actor_optimizer.load_state_dict(torch.load(filename + "_actor_optimizer"))
        self.actor_target = copy.deepcopy(self.actor)

