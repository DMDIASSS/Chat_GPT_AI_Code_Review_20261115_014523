"""Kuxir Pinch & Wall-Roll Environment & Mutator for RocketSim.

Specialized curriculum for:
1) Full Sequence (50%):
   - Ball on ground rolled towards side wall at 0 to 30 degrees into the wall
     (0 deg = perpendicular into wall, 30 deg = angled downfield towards enemy side).
   - Car on the ground driving behind the ball with boost, guiding it into the bevel.
   - Ball smoothly transitions from floor into vertical climb up the wall.
   - Car follows ball up the wall curve, jumps/air-rolls, and pinches into enemy net.
2) Wall Climb & Pinch (30%):
   - Ball already on the curve climbing up the wall (0 to 30 deg momentum).
   - Car on the ramp curve driving up behind it (wheels on surface, NOT flying).
3) High Wall Pinch Execution (20%):
   - Ball high on wall surface, car on wall surface timing jump and dodge into wall.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple
import numpy as np

import rlgym.rocket_league.common_values as cv
from rlgym.api import RewardFunction, StateMutator
from rlgym.rocket_league.api import GameState, Car, PhysicsObject
from rlgym.rocket_league.obs_builders import DefaultObs
from rlgym.rocket_league.action_parsers import LookupTableAction
from rlgym.rocket_league.sim import RocketSimEngine


def basis(forward: np.ndarray, up: Tuple[float, float, float] = (0, 0, 1)) -> np.ndarray:
    """Builds 3x3 orientation matrix matching RocketSim / RLGym convention."""
    f = np.asarray(forward, dtype=np.float64)
    fn = np.linalg.norm(f)
    f = f / fn if fn > 1e-6 else np.array([0., 1., 0.])

    u = np.asarray(up, dtype=np.float64)
    un = np.linalg.norm(u)
    u = u / un if un > 1e-6 else np.array([0., 0., 1.])

    right = np.cross(u, f)
    rn = np.linalg.norm(right)
    if rn < 1e-6:
        u = np.array([0., 1., 0.])
        right = np.cross(u, f)
        rn = np.linalg.norm(right)
    right = right / rn
    up_final = np.cross(f, right)
    return np.column_stack((f, right, up_final))


class KuxirMutator(StateMutator[GameState]):
    """Spawns realistic 0°–30° wall rolls and full Kuxir sequences."""

    def __init__(self, full_seq_ratio: float = 0.50, climb_ratio: float = 0.30):
        super().__init__()
        self.full_seq_ratio = full_seq_ratio
        self.climb_ratio = climb_ratio

    def apply(self, state: GameState, shared_info: Dict[str, Any]) -> None:
        rng = np.random.default_rng()
        side = 1.0 if rng.random() > 0.5 else -1.0  # +1 right wall (x=4096), -1 left wall (x=-4096)
        wall_x = side * 4096.0

        r = rng.random()
        car = state.cars['blue-0']

        # -----------------------------------------------------------------
        # Exact Angle Setup: 0 to 30 degrees into the wall
        # 0 deg = perpendicular into wall (vx = side * speed, vy = 0)
        # 30 deg = angled forward to enemy side (vx = side * speed * cos(30), vy = speed * sin(30))
        # -----------------------------------------------------------------
        angle_deg = float(rng.uniform(0.0, 30.0))
        angle_rad = math.radians(angle_deg)

        dir_x = side * math.cos(angle_rad)
        dir_y = math.sin(angle_rad)  # Positive towards enemy net (y = +5120)

        if r < self.full_seq_ratio:
            # =============================================================
            # MODE 1: Full Sequence Start (Ground roll -> climb -> pinch)
            # Ball starts on the field in own half / midfield, heading to wall
            # =============================================================
            ball_x = side * float(rng.uniform(1200.0, 2400.0))
            ball_y = float(rng.uniform(-3200.0, -1200.0))
            ball_z = cv.BALL_RADIUS + 1.0

            roll_speed = float(rng.uniform(1050.0, 1400.0))
            state.ball.position = np.array([ball_x, ball_y, ball_z], dtype=np.float32)
            state.ball.linear_velocity = np.array([
                dir_x * roll_speed,
                dir_y * roll_speed,
                0.0
            ], dtype=np.float32)
            state.ball.angular_velocity = np.zeros(3, dtype=np.float32)

            # Car starts ON THE GROUND behind the ball, driving along approach line
            offset_dist = float(rng.uniform(220.0, 420.0))
            car_x = ball_x - dir_x * offset_dist
            car_y = ball_y - dir_y * offset_dist
            car_z = 17.0

            car_forward = np.array([dir_x, dir_y, 0.0], dtype=np.float64)
            car.physics.position = np.array([car_x, car_y, car_z], dtype=np.float32)
            car.physics.rotation_mtx = basis(car_forward, up=(0, 0, 1))

            car_speed = float(rng.uniform(950.0, 1350.0))
            car.physics.linear_velocity = (car_forward * car_speed).astype(np.float32)
            car.physics.angular_velocity = np.zeros(3, dtype=np.float32)
            car.boost_amount = float(rng.uniform(80.0, 100.0))
            car.on_ground = True
            car.has_jumped = False
            car.has_flipped = False
            car.has_double_jumped = False

        elif r < self.full_seq_ratio + self.climb_ratio:
            # =============================================================
            # MODE 2: Wall Transition & Climb Start
            # Ball is already entering the wall bevel, converting into climb
            # =============================================================
            ball_x = wall_x - side * float(rng.uniform(80.0, 180.0))
            ball_y = float(rng.uniform(-2200.0, 0.0))
            ball_z = float(rng.uniform(180.0, 420.0))

            climb_speed = float(rng.uniform(900.0, 1300.0))
            state.ball.position = np.array([ball_x, ball_y, ball_z], dtype=np.float32)
            state.ball.linear_velocity = np.array([
                dir_x * 200.0,               # Low residual horizontal velocity
                dir_y * climb_speed * 0.45,  # Forward speed along wall
                float(rng.uniform(300.0, 650.0))  # Upward climb momentum
            ], dtype=np.float32)
            state.ball.angular_velocity = np.zeros(3, dtype=np.float32)

            # Car is driving ON THE RAMP CURVE behind the ball
            car_x = wall_x - side * float(rng.uniform(250.0, 450.0))
            car_y = ball_y - float(rng.uniform(250.0, 450.0))
            car_z = float(rng.uniform(30.0, 160.0))

            car_forward = np.array([dir_x * 0.7, 0.5, 0.5], dtype=np.float64)
            car.physics.position = np.array([car_x, car_y, car_z], dtype=np.float32)
            car.physics.rotation_mtx = basis(car_forward, up=(0, 0, 1))

            car_speed = float(rng.uniform(1100.0, 1500.0))
            car.physics.linear_velocity = (car_forward / np.linalg.norm(car_forward) * car_speed).astype(np.float32)
            car.physics.angular_velocity = np.zeros(3, dtype=np.float32)
            car.boost_amount = float(rng.uniform(85.0, 100.0))
            car.on_ground = True
            car.has_jumped = False
            car.has_flipped = False
            car.has_double_jumped = False

        else:
            # =============================================================
            # MODE 3: High Wall Pinch Execution
            # Ball is rolling smoothly on the vertical wall face
            # =============================================================
            ball_z = float(rng.uniform(420.0, 750.0))
            ball_y = float(rng.uniform(-2000.0, 500.0))
            ball_x = wall_x - side * (cv.BALL_RADIUS + float(rng.uniform(2.0, 15.0)))

            state.ball.position = np.array([ball_x, ball_y, ball_z], dtype=np.float32)
            state.ball.linear_velocity = np.array([
                0.0,
                float(rng.uniform(180.0, 400.0)),
                float(rng.uniform(150.0, 400.0))
            ], dtype=np.float32)
            state.ball.angular_velocity = np.zeros(3, dtype=np.float32)

            # Car is on the wall surface following behind (NOT pre-flying in midair)
            car_x = wall_x - side * float(rng.uniform(40.0, 120.0))
            car_y = ball_y - float(rng.uniform(260.0, 480.0))
            car_z = ball_z - float(rng.uniform(120.0, 260.0))

            # Car orientation on the wall: wheels face wall (-side, 0, 0), nose points up/forward
            car_forward = np.array([0.0, 0.6, 0.8], dtype=np.float64)
            wall_normal = np.array([-side, 0.0, 0.0], dtype=np.float64)

            car.physics.position = np.array([car_x, car_y, car_z], dtype=np.float32)
            car.physics.rotation_mtx = basis(car_forward, up=wall_normal)

            car_speed = float(rng.uniform(1200.0, 1650.0))
            car.physics.linear_velocity = (car_forward / np.linalg.norm(car_forward) * car_speed).astype(np.float32)
            car.physics.angular_velocity = np.zeros(3, dtype=np.float32)
            car.boost_amount = 100.0
            car.on_ground = True
            car.has_jumped = False
            car.has_flipped = False
            car.has_double_jumped = False

        # Opponent (orange-0) placed as passive spectator in opposite half
        opp = state.cars['orange-0']
        opp.physics.position = np.array([0.0, 4800.0, 17.0], dtype=np.float32)
        opp.physics.rotation_mtx = basis(np.array([0.0, -1.0, 0.0]), up=(0, 0, 1))
        opp.physics.linear_velocity = np.zeros(3, dtype=np.float32)
        opp.physics.angular_velocity = np.zeros(3, dtype=np.float32)
        opp.boost_amount = 33.0
        opp.on_ground = True


class KuxirReward(RewardFunction[str, GameState, float]):
    """Reward function covering the entire Kuxir sequence:
    1) 0°–30° entry angle toward wall.
    2) Climbing the wall bevel smoothly without bouncing off.
    3) Driving up the wall / aerial follow.
    4) High-speed Kuxir wall pinch with quadratic speed scaling.
    """

    def __init__(self):
        super().__init__()
        self.prev_ball_speed: Dict[str, float] = {}
        self.best_pinch_speed = 0.0

    def reset(self, initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.prev_ball_speed = {
            'blue-0': float(np.linalg.norm(initial_state.ball.linear_velocity))
        }

    def get_rewards(self, agents: List[str], state: GameState, is_terminated: Dict[str, bool],
                    is_truncated: Dict[str, bool], shared_info: Dict[str, Any]) -> Dict[str, float]:
        rewards: Dict[str, float] = {}

        ball = state.ball
        bp = ball.position
        bv = ball.linear_velocity
        ball_speed = float(np.linalg.norm(bv))

        side = 1.0 if float(bp[0]) >= 0 else -1.0
        dist_wall = 4096.0 - abs(float(bp[0]))
        near_wall = dist_wall < 320.0 and float(bp[2]) > 180.0

        for agent in agents:
            if agent != 'blue-0':
                rewards[agent] = 0.0
                continue

            car = state.cars[agent]
            cp = car.physics.position
            cv_vel = car.physics.linear_velocity
            r = 0.0
            prev_spd = self.prev_ball_speed.get(agent, ball_speed)

            # -------------------------------------------------------------
            # STEP 1: 0° to 30° Ground Roll Setup
            # -------------------------------------------------------------
            if float(bp[2]) < 220.0:
                vx_into_wall = float(bv[0]) * side
                vy_downfield = float(bv[1])

                if vx_into_wall > 200.0:
                    # Angle relative to wall normal
                    angle_deg = math.degrees(math.atan2(max(0.0, vy_downfield), vx_into_wall))
                    if 0.0 <= angle_deg <= 32.0:
                        # Ideal 0 to 30 degree angle into the wall!
                        r += 0.35 * (vx_into_wall / 1000.0)
                    elif angle_deg > 50.0:
                        # Too parallel to wall (won't climb)
                        r -= 0.10

            # -------------------------------------------------------------
            # STEP 2: Wall Climb & Anti-Bounce
            # -------------------------------------------------------------
            if dist_wall < 350.0:
                # Climbing momentum up the wall
                if float(bv[2]) > 150.0:
                    climb_bonus = min(2.0, float(bv[2]) / 350.0) * 0.40
                    r += climb_bonus

                # Smooth wall stickiness (staying glued to wall)
                if dist_wall < 150.0 and float(bp[2]) > 250.0:
                    r += 0.20

                # Anti-bounce penalty: if ball rebounds off wall towards center
                if float(bv[0]) * side < -400.0:
                    r -= 1.5

            # -------------------------------------------------------------
            # STEP 3: Car Following & Positioning
            # -------------------------------------------------------------
            # Reward car gaining height on the wall behind the ball
            if abs(float(cp[0])) > 3700.0 and float(cp[2]) > 100.0:
                r += min(1.0, float(cp[2]) / 400.0) * 0.15

            # -------------------------------------------------------------
            # STEP 4: High-Speed Kuxir Pinch Execution
            # -------------------------------------------------------------
            if car.ball_touches > 0:
                r += 0.5  # Base contact

                if near_wall:
                    r += 2.5

                    # Speed explosion check
                    speed_delta = ball_speed - prev_spd
                    if ball_speed > 1600.0 and speed_delta > 250.0:
                        # Quadratic scaling: the faster the pinch shot, the exponentially higher the reward!
                        pinch_power = (ball_speed - 1600.0) / 300.0
                        pinch_reward = float(min(60.0, pinch_power ** 2))
                        r += pinch_reward

                        if ball_speed > self.best_pinch_speed:
                            self.best_pinch_speed = ball_speed

                        # Flip / Dodge input incentive: bonus if car dodged into the wall
                        if car.has_flipped or car.is_holding_jump:
                            r += 4.0

                        # Shot angle: ball propelled downfield towards enemy goal
                        if bv[1] > 800.0:
                            direction_reward = float(bv[1] / 1500.0) * 5.0
                            r += direction_reward

            # Goal scored bonus
            if state.goal_scored and float(bp[1]) > 5120.0:
                r += 40.0

            self.prev_ball_speed[agent] = ball_speed
            rewards[agent] = float(r)

        return rewards


def make_kuxir_components():
    """Builds standard observation builder and action parser."""
    obs_builder = DefaultObs(
        zero_padding=None,
        pos_coef=np.asarray([1 / cv.SIDE_WALL_X, 1 / cv.BACK_NET_Y, 1 / cv.CEILING_Z]),
        ang_coef=1 / np.pi,
        lin_vel_coef=1 / cv.CAR_MAX_SPEED,
        ang_vel_coef=1 / cv.CAR_MAX_ANG_VEL,
        boost_coef=1 / 100.0,
    )
    action_parser = LookupTableAction()
    return obs_builder, action_parser
