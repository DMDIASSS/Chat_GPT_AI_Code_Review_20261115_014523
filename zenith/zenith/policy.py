"""
Zenith Policy & Value Actor-Critic Architecture
Featuring Top-p (nucleus) sampling, discrete action masking, and LayerNorm GELU trunks.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions.categorical import Categorical


def top_p_logits(logits: torch.Tensor, top_p: float = 0.90, filter_value: float = -1e9) -> torch.Tensor:
    """
    Nucleus (Top-p) filtering on logits.
    Keeps only the smallest set of most probable actions whose cumulative probability >= top_p.
    """
    if top_p >= 1.0:
        return logits

    sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
    sorted_probs = F.softmax(sorted_logits, dim=-1)
    cumulative_probs = torch.cumsum(sorted_probs, dim=-1)

    # Remove tokens with cumulative probability above the threshold
    sorted_indices_to_remove = cumulative_probs > top_p
    # Shift indices to the right to keep the first token above threshold
    sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
    sorted_indices_to_remove[..., 0] = False

    # Scatter back to original indexing
    indices_to_remove = sorted_indices_to_remove.scatter(dim=-1, index=sorted_indices, src=sorted_indices_to_remove)
    filtered_logits = logits.masked_fill(indices_to_remove, filter_value)
    return filtered_logits


class ZenithPolicy(nn.Module):
    """
    Compact high-throughput Actor-Critic architecture for Zenith.
    Default hidden_dim=256 (~228k total parameters) for maximum SPS,
    sub-millisecond GPU inference, and zero memory-bandwidth bottlenecks.
    """
    def __init__(self, obs_dim: int = 145, num_actions: int = 90, hidden_dim: int = 256):
        super().__init__()
        self.obs_dim = obs_dim
        self.num_actions = num_actions
        self.hidden_dim = hidden_dim

        # Compact Actor Network (145 -> 256 -> 256 -> 90) ~125k params
        self.actor = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_actions)
        )

        # Compact Critic Network (145 -> 256 -> 256 -> 1) ~103k params
        self.critic = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1)
        )

        self._init_weights()

    def _init_weights(self):
        # Orthogonal initialization for RL stability
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=1.414)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
        # Smaller gain on final policy layer for unskewed initial exploration
        nn.init.orthogonal_(self.actor[-1].weight, gain=0.01)
        nn.init.orthogonal_(self.critic[-1].weight, gain=1.0)

    def forward(self, obs: torch.Tensor, mask: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor]:
        logits = self.actor(obs)
        if mask is not None:
            invalid = (mask == 0)
            logits = logits.masked_fill(invalid, -1e9)
        values = self.critic(obs).squeeze(-1)
        return logits, values

    def get_action(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor | None = None,
        temperature: float = 0.25,
        top_p: float = 0.90,
        deterministic: bool = False
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Selects actions for a batch of observations.
        Returns: (actions, log_probs, values)
        """
        logits, values = self.forward(obs, mask)

        if deterministic:
            actions = torch.argmax(logits, dim=-1)
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)
            log_probs = dist.log_prob(actions)
            return actions, log_probs, values

        # Stochastic selection with temperature and Top-p nucleus filtering
        temp = max(1e-4, temperature)
        scaled_logits = logits / temp
        filtered_logits = top_p_logits(scaled_logits, top_p=top_p)
        probs = F.softmax(filtered_logits, dim=-1)

        # Numerical safety check
        if torch.isnan(probs).any() or (probs.sum(dim=-1) <= 0).any():
            probs = F.softmax(logits, dim=-1)

        dist = Categorical(probs)
        actions = dist.sample()
        log_probs = dist.log_prob(actions)
        return actions, log_probs, values

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
        mask: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Evaluates batch of actions for PPO updates.
        Returns: (log_probs, values, entropy)
        """
        logits, values = self.forward(obs, mask)
        probs = F.softmax(logits, dim=-1)
        dist = Categorical(probs)

        log_probs = dist.log_prob(actions)
        entropy = dist.entropy()
        return log_probs, values, entropy

    def get_value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.critic(obs).squeeze(-1)
