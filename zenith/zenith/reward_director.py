"""
Zenith Reward Director
Manages the 12 decomposed reward components and schedules dynamic annealing.
"""
from __future__ import annotations

import numpy as np


class RewardDirector:
    """
    Manages decomposed reward weights and provides curriculum scheduling.
    Component indices:
      0: goal (+10 / -10)
      1: ball_net_vel (ball velocity toward opponent net)
      2: car_ball_vel (closing speed to ball)
      3: car_ball_dist (exponential proximity to ball)
      4: touch (any touch on ball)
      5: aerial_touch (touch above 300 uu)
      6: flip_reset (3-wheel contact reset acquired)
      7: musty_flick (Musty flick mechanic executed)
      8: save (defensive goal-line save)
      9: prejump (early takeoff on high boomer shot)
     10: fake_penalty (punish unprompted high jumping on fake)
     11: boost (boost gain)
    """

    COMPONENT_NAMES = [
        "goal",
        "ball_net_vel",
        "car_ball_vel",
        "car_ball_dist",
        "touch",
        "aerial_touch",
        "flip_reset",
        "musty_flick",
        "save",
        "prejump",
        "fake_penalty",
        "boost"
    ]

    def __init__(self, stage: str = "balanced"):
        self.stage = stage
        self.step_count = 0

        # Base default weights
        self.weights = np.zeros(12, dtype=np.float32)
        self.set_stage(stage)

    def set_stage(self, stage: str):
        self.stage = stage
        if stage == "mechanics_discovery":
            # Higher rewards for aerial, reset, musty, and defensive reads
            self.weights = np.array([
                5.0,   # goal
                1.5,   # ball_net_vel
                0.3,   # car_ball_vel
                0.2,   # car_ball_dist
                1.0,   # touch
                2.5,   # aerial_touch
                4.0,   # flip_reset
                4.0,   # musty_flick
                3.5,   # save
                3.0,   # prejump
                2.0,   # fake_penalty (positive multiplier on negative component)
                0.2    # boost
            ], dtype=np.float32)
        elif stage == "goal_dominance":
            # Highly competitive win-rate dominance, minimal shaping
            self.weights = np.array([
                10.0,  # goal
                2.0,   # ball_net_vel
                0.1,   # car_ball_vel
                0.05,  # car_ball_dist
                0.5,   # touch
                1.5,   # aerial_touch
                2.0,   # flip_reset
                2.0,   # musty_flick
                2.5,   # save
                2.0,   # prejump
                2.0,   # fake_penalty
                0.1    # boost
            ], dtype=np.float32)
        else:  # "balanced"
            self.weights = np.array([
                8.0,   # goal
                1.8,   # ball_net_vel
                0.2,   # car_ball_vel
                0.1,   # car_ball_dist
                0.8,   # touch
                2.0,   # aerial_touch
                3.0,   # flip_reset
                3.0,   # musty_flick
                3.0,   # save
                2.5,   # prejump
                2.0,   # fake_penalty
                0.15   # boost
            ], dtype=np.float32)

    def get_weights(self) -> np.ndarray:
        return self.weights.copy()

    def update_schedule(self, current_total_steps: int):
        self.step_count = current_total_steps
        # Anneal car_ball_dist and car_ball_vel over time
        if current_total_steps > 1_000_000 and self.stage == "mechanics_discovery":
            self.set_stage("balanced")
        elif current_total_steps > 3_000_000 and self.stage == "balanced":
            self.set_stage("goal_dominance")

    def decompose_metrics(self, reward_components_batch: np.ndarray) -> dict[str, float]:
        """
        Computes mean metric values across the batch for telemetry.
        """
        means = np.mean(reward_components_batch, axis=0)
        return {name: float(means[i]) for i, name in enumerate(self.COMPONENT_NAMES)}
