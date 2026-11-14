"""The Judge: Tactical Threat Assessor, Mode Arbiter, and Value Evaluator (Phi).

Solves the student failure:
- Does NOT blend conflicting probability distributions across teachers.
- Dynamically assigns 100% authority to the appropriate grandmaster expert:
    * High threat / defense / 50-50 / shadow rotation -> Chronos (impenetrable defensive anchor)
    * High opportunity / aerial read / wall read / shot -> Galactus (lethal aerial and offensive specialist)
    * Pinch geometry -> Specialized Pinch Trigger
- Enforces Tactical Hysteresis / Commitment: prevents jittery, alternating teacher switches mid-air.
- Provides potential function Phi(s) for provably safe reward shaping during training.
"""
from __future__ import annotations
import numpy as np

MODE_DEFENSE = "chronos_defense"
MODE_OFFENSE = "galactus_offense"
MODE_PINCH   = "pinch_strike"

GOAL_BACK_Y = 5120.0
SIDE_WALL_X = 4096.0

class TacticalJudge:
    def __init__(self, commitment_steps: int = 4):
        """commitment_steps: number of 8-tick decision steps (each ~66ms) to lock commitment."""
        self.commitment_steps = commitment_steps
        self.current_mode = MODE_DEFENSE
        self.lock_remaining = 0
        self.last_threat = 0.0
        self.last_opportunity = 0.0

    def evaluate_state(self, own_pos, own_vel, opp_pos, opp_vel, ball_pos, ball_vel, own_boost, is_orange: bool):
        """Evaluates tactical threat and opportunity from the perspective of own team."""
        # Normalize so own goal is always at -5120, opponent goal is at +5120
        sign = -1.0 if is_orange else 1.0
        o_pos = own_pos * np.array([sign, sign, 1.0])
        o_vel = own_vel * np.array([sign, sign, 1.0])
        e_pos = opp_pos * np.array([sign, sign, 1.0])
        b_pos = ball_pos * np.array([sign, sign, 1.0])
        b_vel = ball_vel * np.array([sign, sign, 1.0])

        dist_to_own_goal = float(np.linalg.norm(b_pos - np.array([0.0, -GOAL_BACK_Y, 0.0])))
        dist_to_opp_goal = float(np.linalg.norm(b_pos - np.array([0.0, GOAL_BACK_Y, 0.0])))
        car_ball_dist = float(np.linalg.norm(o_pos - b_pos))
        opp_ball_dist = float(np.linalg.norm(e_pos - b_pos))

        # Is car goal-side (between ball and our goal)?
        is_goal_side = (o_pos[1] < b_pos[1])

        # --- 1. Defensive Threat Level T in [0, 1] ---
        threat = 0.0
        # Ball in defensive half
        if b_pos[1] < 0:
            threat += 0.35 * (abs(b_pos[1]) / GOAL_BACK_Y)
        # Ball moving toward our goal
        if b_vel[1] < -200:
            threat += min(0.40, abs(b_vel[1]) / 2500.0)
        # Opponent closer to ball than us in our half
        if opp_ball_dist < car_ball_dist and b_pos[1] < 1000:
            threat += 0.25
        # We are caught ahead of ball (disaster scenario)
        if not is_goal_side and b_pos[1] < 1500:
            threat += 0.30
        threat = float(np.clip(threat, 0.0, 1.0))

        # --- 2. Offensive Opportunity Level O in [0, 1] ---
        opportunity = 0.0
        # Ball in offensive half
        if b_pos[1] > 0:
            opportunity += 0.35 * (b_pos[1] / GOAL_BACK_Y)
        # Ball moving toward opponent goal
        if b_vel[1] > 200:
            opportunity += min(0.30, b_vel[1] / 2500.0)
        # We are closer to ball and have goal-side momentum
        if car_ball_dist < opp_ball_dist and is_goal_side:
            opportunity += 0.25
        # Aerial opportunity (ball floating high in offensive half)
        if b_pos[2] > 400 and b_pos[1] > -1000 and own_boost > 20:
            opportunity += 0.25
        opportunity = float(np.clip(opportunity, 0.0, 1.0))

        # --- 3. Pinch Geometry Detection ---
        near_wall = (abs(b_pos[0]) > (SIDE_WALL_X - 600))
        high_closing_speed = (car_ball_dist < 600 and np.linalg.norm(o_vel) > 1200)
        pinch_opportunity = bool(near_wall and high_closing_speed and b_pos[2] < 1200)

        self.last_threat = threat
        self.last_opportunity = opportunity

        # --- 4. Mode Selection with Hysteresis ---
        if self.lock_remaining > 0:
            self.lock_remaining -= 1
            # If currently in offense or pinch, check if touch/landing occurred to unlock early
            if self.current_mode in (MODE_OFFENSE, MODE_PINCH):
                if car_ball_dist < 180: # Just hit the ball
                    self.lock_remaining = 0
            return self.current_mode

        # Decision rule:
        # Defense takes absolute priority under real threat
        if threat >= 0.50 or (threat > opportunity and threat > 0.30):
            chosen_mode = MODE_DEFENSE
            self.lock_remaining = self.commitment_steps
        elif pinch_opportunity and threat < 0.35:
            chosen_mode = MODE_PINCH
            self.lock_remaining = self.commitment_steps * 2 # Lock pinch run-up
        elif opportunity >= 0.35:
            chosen_mode = MODE_OFFENSE
            self.lock_remaining = self.commitment_steps
        else:
            # Default to Chronos's robust general positioning
            chosen_mode = MODE_DEFENSE

        self.current_mode = chosen_mode
        return self.current_mode

    @staticmethod
    def compute_potential(own_pos, ball_pos, ball_vel, is_orange: bool) -> float:
        """Potential function Phi(s) for telescoping reward shaping:
        Phi(s) = 0.5 * (y_ball / 5120) - 0.2 * (dist_car_ball / 6000) + 0.3 * (v_y_ball / 2300)
        """
        sign = -1.0 if is_orange else 1.0
        b_y = float(ball_pos[1] * sign)
        v_y = float(ball_vel[1] * sign)
        car_dist = float(np.linalg.norm(own_pos - ball_pos))

        phi = (0.5 * (b_y / GOAL_BACK_Y)
               - 0.2 * min(car_dist, 10000.0) / 6000.0
               + 0.3 * np.clip(v_y / 2300.0, -1.0, 1.0))
        return float(phi)
