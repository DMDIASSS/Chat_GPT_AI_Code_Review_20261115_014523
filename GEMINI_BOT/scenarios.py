"""Scenario definitions for scenario-based training & fine-tuning in RocketSim / RLGym.

Includes:
- Kuxir / Sidewall Pinch Scenarios: teaches high-velocity pinches into the wall/ground
- Shadow Defense Scenarios: teaches goal-line saves and back-post rotation under high pressure
- Fast Kickoff Scenarios: speedflips and kickoff challenges
"""
from __future__ import annotations
import numpy as np

class PinchScenario:
    """Sets up high-speed pinch opportunities against sidewall."""
    def __init__(self, rng=None):
        self.rng = rng or np.random.default_rng()

    def generate(self) -> dict:
        side = 1.0 if self.rng.random() > 0.5 else -1.0
        wall_x = 3850.0 * side
        y = self.rng.uniform(-1500.0, 1500.0)
        z = self.rng.uniform(100.0, 250.0)

        ball_pos = np.array([wall_x, y, z], dtype=np.float32)
        ball_vel = np.array([side * 300.0, self.rng.uniform(-200.0, 400.0), 0.0], dtype=np.float32)

        # Place car 350 units inward from ball, angled toward wall
        car_pos = np.array([wall_x - side * 350.0, y - 300.0, 17.0], dtype=np.float32)
        car_vel = np.array([side * 1400.0, 1200.0, 0.0], dtype=np.float32)

        return {
            "name": "sidewall_pinch",
            "ball_pos": ball_pos,
            "ball_vel": ball_vel,
            "car_pos": car_pos,
            "car_vel": car_vel,
            "car_boost": 100.0
        }

class ShadowDefenseScenario:
    """Sets up defensive emergency where bot must shadow, turn, and save."""
    def __init__(self, rng=None):
        self.rng = rng or np.random.default_rng()

    def generate(self) -> dict:
        # Ball coming toward our goal (y = -5120) with high pace
        ball_y = self.rng.uniform(-2000.0, 500.0)
        ball_x = self.rng.uniform(-1500.0, 1500.0)
        ball_pos = np.array([ball_x, ball_y, self.rng.uniform(100.0, 800.0)], dtype=np.float32)
        ball_vel = np.array([self.rng.uniform(-300.0, 300.0), -self.rng.uniform(1200.0, 2000.0), self.rng.uniform(100.0, 500.0)], dtype=np.float32)

        # Car heading toward our net in front of the ball
        car_pos = np.array([ball_x + self.rng.uniform(-300.0, 300.0), ball_y - 1200.0, 17.0], dtype=np.float32)
        car_vel = np.array([0.0, -1400.0, 0.0], dtype=np.float32)

        return {
            "name": "shadow_defense",
            "ball_pos": ball_pos,
            "ball_vel": ball_vel,
            "car_pos": car_pos,
            "car_vel": car_vel,
            "car_boost": 60.0
        }

class KickoffScenario:
    """Standard 5 kickoff spawn positions."""
    SPAWNS = [
        # Diagonal spawns
        (np.array([-2048.0, -2560.0, 17.0]), np.array([2048.0, 2560.0, 17.0])),
        (np.array([2048.0, -2560.0, 17.0]), np.array([-2048.0, 2560.0, 17.0])),
        # Off-center spawns
        (np.array([-256.0, -3840.0, 17.0]), np.array([256.0, 3840.0, 17.0])),
        (np.array([256.0, -3840.0, 17.0]), np.array([-256.0, 3840.0, 17.0])),
        # Straight-back spawn
        (np.array([0.0, -4608.0, 17.0]), np.array([0.0, 4608.0, 17.0]))
    ]

    def __init__(self, rng=None):
        self.rng = rng or np.random.default_rng()

    def generate(self) -> dict:
        idx = int(self.rng.integers(len(self.SPAWNS)))
        own_spawn, opp_spawn = self.SPAWNS[idx]
        return {
            "name": "kickoff",
            "ball_pos": np.array([0.0, 0.0, 93.0], dtype=np.float32),
            "ball_vel": np.zeros(3, dtype=np.float32),
            "car_pos": own_spawn.copy(),
            "car_vel": np.zeros(3, dtype=np.float32),
            "opp_pos": opp_spawn.copy(),
            "opp_vel": np.zeros(3, dtype=np.float32),
            "car_boost": 33.0
        }
