"""
Zenith League Manager: Prioritized Fictitious Self-Play (PFSP)
Maintains past policy checkpoints and dynamically matches the student against
historical snapshots and sparring teachers to prevent cyclical degradation.
"""
from __future__ import annotations

import pathlib
import copy
import numpy as np
import torch
import torch.nn as nn
from .policy import ZenithPolicy


class LeagueManager:
    """
    Manages self-play opponent pool, snapshot retention, and PFSP matchmaking.
    """
    def __init__(
        self,
        snapshot_dir: pathlib.Path | str,
        max_snapshots: int = 20,
        device: torch.device | str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        self.snapshot_dir = pathlib.Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.max_snapshots = max_snapshots
        self.device = torch.device(device)

        # Active opponent model loaded in memory
        self.opponent_policy: ZenithPolicy | None = None
        self.snapshots: list[dict] = []
        self.current_opponent_name = "initial_self"

    def register_snapshot(self, policy: ZenithPolicy, step_count: int, elo: float = 1000.0) -> str:
        """
        Saves a copy of the current policy weights as a league snapshot.
        """
        snap_name = f"zenith_snap_{step_count:08d}.pt"
        snap_path = self.snapshot_dir / snap_name
        torch.save(policy.state_dict(), snap_path)

        info = {
            "name": snap_name,
            "path": snap_path,
            "step": step_count,
            "elo": elo,
            "games_played": 0,
            "win_rate_vs_student": 0.50
        }
        self.snapshots.append(info)

        # Evict oldest snapshots if exceeding max_snapshots (preserving landmark snapshots)
        if len(self.snapshots) > self.max_snapshots:
            # Keep first landmark, highest elo, and most recent
            self.snapshots.sort(key=lambda s: s["step"])
            # Remove from the middle
            evict_idx = 1
            old = self.snapshots.pop(evict_idx)
            if old["path"].exists():
                try:
                    old["path"].unlink()
                except Exception:
                    pass

        # Load as current opponent policy
        self._load_opponent(snap_path)
        return snap_name

    def _load_opponent(self, path: pathlib.Path):
        if self.opponent_policy is None:
            self.opponent_policy = ZenithPolicy().to(self.device)
        state_dict = torch.load(path, map_location=self.device)
        self.opponent_policy.load_state_dict(state_dict)
        self.opponent_policy.eval()

    def sample_opponent(self) -> dict | None:
        """
        Prioritized Fictitious Self-Play (PFSP):
        Samples past opponents with probability inversely proportional to deviation from 50% win rate.
        Focuses on opponents where the student is challenged most (hardest frontier).
        """
        if not self.snapshots:
            return None

        # Compute weights based on challenge factor: f(w) = 1.0 / (0.1 + abs(w - 0.5))
        weights = []
        for s in self.snapshots:
            w = s.get("win_rate_vs_student", 0.5)
            # Higher weight when opponent win rate is close to 50% or higher
            challenge = 1.0 / (0.05 + abs(w - 0.5))
            weights.append(challenge)

        weights = np.array(weights, dtype=np.float32)
        probs = weights / weights.sum()
        chosen_idx = int(np.random.choice(len(self.snapshots), p=probs))
        chosen = self.snapshots[chosen_idx]
        self.current_opponent_name = chosen["name"]
        self._load_opponent(chosen["path"])
        return chosen

    def get_opponent_actions(
        self,
        opp_obs: torch.Tensor,
        opp_masks: torch.Tensor,
        deterministic: bool = False
    ) -> torch.Tensor:
        """
        Computes actions for the opponent players across arenas.
        If no snapshots exist yet, opponent mirror-samples from an un-updated policy.
        """
        if self.opponent_policy is None:
            # Fallback: random valid actions
            logits = torch.randn((opp_obs.shape[0], 90), device=self.device)
            logits = logits.masked_fill(opp_masks == 0, -1e9)
            return torch.argmax(logits, dim=-1)

        with torch.inference_mode():
            actions, _, _ = self.opponent_policy.get_action(
                opp_obs,
                opp_masks,
                temperature=0.3,
                top_p=0.90,
                deterministic=deterministic
            )
            return actions

    def update_opponent_win_rate(self, snap_name: str, opponent_win_rate: float):
        for s in self.snapshots:
            if s["name"] == snap_name:
                s["games_played"] += 1
                s["win_rate_vs_student"] = 0.8 * s["win_rate_vs_student"] + 0.2 * opponent_win_rate
                break
