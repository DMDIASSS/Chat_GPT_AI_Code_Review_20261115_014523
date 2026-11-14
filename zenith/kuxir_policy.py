"""Kuxir Policy & Value Network based on Nexto Student (92-obs -> 90-actions).

Initialized with pre-trained weights from Nexto student, retaining expert driving,
turning, and aerial fundamentals while adapting to high-speed wall pinches.
"""
from __future__ import annotations

import math
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical

NEXTO_STUDENT_PATH = Path(r"E:\Downloads\Chat_GPT_AI\data\nexto_student_v2.pt")


class KuxirActorCritic(nn.Module):
    def __init__(self, obs_dim: int = 92, act_dim: int = 90, hidden_dim: int = 512):
        super().__init__()
        self.obs_dim = obs_dim
        self.act_dim = act_dim

        # Actor trunk: 92 -> 512 -> 512 -> 90
        self.actor = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, act_dim)
        )

        # Critic trunk: 92 -> 512 -> 512 -> 1
        self.critic = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )

    def load_base_weights(self, path: Path | str = NEXTO_STUDENT_PATH):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Base Nexto student weights not found at: {path}")

        ckpt = torch.load(str(path), map_location="cpu")
        state_dict = {}
        for k, v in ckpt.items():
            clean_k = k.replace("model.", "")
            state_dict[clean_k] = v

        # Load into actor
        self.actor.load_state_dict(state_dict, strict=True)
        print(f"[Kuxir Policy] Successfully loaded base Nexto Student weights from {path.name}!")

        # Initialize critic weights from actor hidden layers for fast warm-start
        with torch.no_grad():
            self.critic[0].weight.copy_(self.actor[0].weight)
            self.critic[0].bias.copy_(self.actor[0].bias)
            self.critic[2].weight.copy_(self.actor[2].weight)
            self.critic[2].bias.copy_(self.actor[2].bias)
            nn.init.orthogonal_(self.critic[4].weight, gain=1.0)
            nn.init.constant_(self.critic[4].bias, 0.0)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if obs.dtype != torch.float32:
            obs = obs.to(torch.float32)
        logits = self.actor(obs)
        value = self.critic(obs).squeeze(-1)
        return logits, value

    def get_action(self, obs: torch.Tensor, mask: torch.Tensor | None = None, deterministic: bool = False):
        logits, value = self.forward(obs)
        if mask is not None:
            logits = logits.masked_fill(~mask, -1e8)

        dist = Categorical(logits=logits)
        if deterministic:
            action = logits.argmax(dim=-1)
        else:
            action = dist.sample()

        log_prob = dist.log_prob(action)
        return action, log_prob, dist.entropy(), value

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor, mask: torch.Tensor | None = None):
        logits, values = self.forward(obs)
        if mask is not None:
            logits = logits.masked_fill(~mask, -1e8)

        dist = Categorical(logits=logits)
        log_probs = dist.log_prob(actions)
        entropy = dist.entropy()
        return log_probs, entropy, values, logits


def build_anchor_policy(device: torch.device) -> nn.Module:
    """Creates a frozen copy of the base Nexto student for KL divergence anchoring."""
    anchor = nn.Sequential(
        nn.Linear(92, 512),
        nn.ReLU(),
        nn.Linear(512, 512),
        nn.ReLU(),
        nn.Linear(512, 90)
    ).to(device)

    ckpt = torch.load(str(NEXTO_STUDENT_PATH), map_location=device)
    state_dict = {k.replace("model.", ""): v for k, v in ckpt.items()}
    anchor.load_state_dict(state_dict)
    anchor.eval()
    for p in anchor.parameters():
        p.requires_grad = False
    return anchor
