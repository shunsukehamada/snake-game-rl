import math
import random
from typing import Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from QNet import Dueling_Network
from replay_buffer import ReplayMemory, Transition


class DQNAgent:
    GAMMA = 0.99
    EPS_START = 0.9
    EPS_END = 0.05
    EPS_DECAY = 200
    N_ACTIONS = 3
    SIZE_REPLAY_MEMORY = 1000
    BATCH_SIZE = 32
    TAU = 0.005
    LR = 1e-4

    def __init__(self, n_frame: int, device: torch.device):
        self.policy_net = Dueling_Network(n_frame=n_frame, n_actions=self.N_ACTIONS).to(device)
        self.target_net = Dueling_Network(n_frame=n_frame, n_actions=self.N_ACTIONS).to(device)
        self.device = device
        self.memory = ReplayMemory(self.SIZE_REPLAY_MEMORY)
        self.optimizer = optim.AdamW(self.policy_net.parameters(), lr=self.LR, amsgrad=True)

    def e_greedy_select_action(self, state: torch.Tensor, steps_done) -> Tuple[torch.Tensor, float]:
        eps_threshold = self.EPS_END + (self.EPS_START - self.EPS_END) * math.exp(-1.0 * steps_done / self.EPS_DECAY)
        steps_done += 1

        if random.random() > eps_threshold:
            with torch.no_grad():
                return self.policy_net(state.to(self.device)).argmax().view(1, 1).cpu(), eps_threshold
        return torch.tensor([[random.randint(0, self.N_ACTIONS - 1)]]), eps_threshold

    def update(self) -> None:
        if len(self.memory) < self.BATCH_SIZE:
            return
        transitions = self.memory.sample(self.BATCH_SIZE)
        batch = Transition(*zip(*transitions))
        non_final_mask = torch.tensor(
            tuple(map(lambda s: s is not None, batch.next_state)), device=self.device, dtype=torch.bool
        )
        non_final_next_states = torch.cat([s for s in batch.next_state if s is not None])

        state_batch = torch.cat(batch.state).to(self.device)
        action_batch = torch.cat(batch.action).to(self.device)
        reward_batch = torch.cat(batch.reward).to(self.device)

        state_action_values = self.policy_net(state_batch).gather(1, action_batch)
        next_state_values = torch.zeros(self.BATCH_SIZE, device=self.device)

        with torch.no_grad():
            next_state_values[non_final_mask] = self.target_net(non_final_next_states.to(self.device)).max(1)[0]

        expected_state_action_values = (next_state_values * self.GAMMA) + reward_batch

        criterion = nn.SmoothL1Loss()
        loss = criterion(state_action_values, expected_state_action_values.unsqueeze(1))
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_value_(self.policy_net.parameters(), 1000)
        self.optimizer.step()

    def push_memory(self, *args) -> None:
        self.memory.push(*args)

    def sync_target(self) -> None:
        target_net_state_dict = self.target_net.state_dict()
        policy_net_state_dict = self.policy_net.state_dict()
        for key in policy_net_state_dict:
            target_net_state_dict[key] = policy_net_state_dict[key] * self.TAU + target_net_state_dict[key] * (
                1 - self.TAU
            )
        self.target_net.load_state_dict(target_net_state_dict)

    def save(self, fname: str) -> None:
        torch.save(self.target_net.state_dict(), f"model_weights/{fname}_target.pth")
        torch.save(self.policy_net.state_dict(), f"model_weights/{fname}_policy.pth")
