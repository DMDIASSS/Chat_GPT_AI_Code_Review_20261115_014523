"""Universal observation builder for GEMINI_BOT.

Supports both RLBot live game (GameTickPacket) and RLGym / RocketSim (GameState).
Constructs:
- Chronos observation (225 features) with team-relative coordinate inversion and mirroring
- Galactus observation (258 features) with ball prediction lookahead and nearest active big boost
- Native 90-action mask
"""
from __future__ import annotations
import math
import numpy as np
from actions import TABLE, native_action_mask

# Standard Rocket League 34 boost pad locations
BOOST_LOCATIONS = np.array([
    [0.0, -4240.0, 70.0], [-1792.0, -4184.0, 70.0], [1792.0, -4184.0, 70.0],
    [-3072.0, -4096.0, 73.0], [3072.0, -4096.0, 73.0], [-940.0, -3308.0, 70.0],
    [940.0, -3308.0, 70.0], [0.0, -2816.0, 70.0], [-3584.0, -2484.0, 70.0],
    [3584.0, -2484.0, 70.0], [-1788.0, -2300.0, 70.0], [1788.0, -2300.0, 70.0],
    [-2048.0, -1036.0, 70.0], [0.0, -1024.0, 70.0], [2048.0, -1036.0, 70.0],
    [-3584.0, 0.0, 73.0], [-1024.0, 0.0, 70.0], [1024.0, 0.0, 70.0],
    [3584.0, 0.0, 73.0], [-2048.0, 1036.0, 70.0], [0.0, 1024.0, 70.0],
    [2048.0, 1036.0, 70.0], [-1788.0, 2300.0, 70.0], [1788.0, 2300.0, 70.0],
    [-3584.0, 2484.0, 70.0], [3584.0, 2484.0, 70.0], [0.0, 2816.0, 70.0],
    [-940.0, 3308.0, 70.0], [940.0, 3308.0, 70.0], [-3072.0, 4096.0, 73.0],
    [3072.0, 4096.0, 73.0], [-1792.0, 4184.0, 70.0], [1792.0, 4184.0, 70.0],
    [0.0, 4240.0, 70.0]
], dtype=np.float32)

# Symmetry mapping for boost pads when field is mirrored along x-axis
MIRROR_PADS = np.array([
    np.argmin(np.linalg.norm(BOOST_LOCATIONS - xyz * np.array([-1.0, 1.0, 1.0], dtype=np.float32), axis=1))
    for xyz in BOOST_LOCATIONS
], dtype=np.int64)

BIG_PAD_INDICES = [3, 4, 15, 18, 29, 30]

def rotation_to_matrix(pitch: float, yaw: float, roll: float) -> np.ndarray:
    """Computes standard 3x3 rotation matrix from Euler angles (pitch, yaw, roll)."""
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cr, sr = math.cos(roll), math.sin(roll)

    # Columns: Forward, Right, Up
    theta = np.zeros((3, 3), dtype=np.float32)
    theta[0, 0] = cp * cy
    theta[1, 0] = cp * sy
    theta[2, 0] = sp

    theta[0, 1] = cy * sp * sr - cr * sy
    theta[1, 1] = sy * sp * sr + cr * cy
    theta[2, 1] = -cp * sr

    theta[0, 2] = -cr * cy * sp - sr * sy
    theta[1, 2] = -cr * sy * sp + sr * cy
    theta[2, 2] = cp * cr
    return theta

class PhysicsData:
    def __init__(self, pos, vel, ang_vel, rot_mtx):
        self.position = np.asarray(pos, dtype=np.float32)
        self.linear_velocity = np.asarray(vel, dtype=np.float32)
        self.angular_velocity = np.asarray(ang_vel, dtype=np.float32)
        self.rotation_mtx = np.asarray(rot_mtx, dtype=np.float32)

class CarData:
    def __init__(self, physics: PhysicsData, team_num: int, boost_amount: float,
                 on_ground: bool, has_flip: bool, is_demoed: bool, has_jumped: bool):
        self.physics = physics
        self.team_num = team_num
        self.boost_amount = boost_amount
        self.on_ground = on_ground
        self.has_flip = has_flip
        self.is_demoed = is_demoed
        self.has_jumped = has_jumped

class StandardGameState:
    def __init__(self, own_car: CarData, opponent_car: CarData, ball_physics: PhysicsData,
                 boost_pad_timers: np.ndarray, tick_count: int = 0):
        self.cars = {0: own_car, 1: opponent_car}
        self.ball = ball_physics
        self.boost_pad_timers = np.asarray(boost_pad_timers, dtype=np.float32)
        self.tick_count = tick_count

def packet_to_gamestate(packet, own_index: int, opponent_index: int, tick_count: int = 0) -> StandardGameState:
    """Converts RLBot GameTickPacket into normalized StandardGameState."""
    def parse_car(p_car):
        phys = p_car.physics
        pos = [phys.location.x, phys.location.y, phys.location.z]
        vel = [phys.velocity.x, phys.velocity.y, phys.velocity.z]
        ang = [phys.angular_velocity.x, phys.angular_velocity.y, phys.angular_velocity.z]
        rot = rotation_to_matrix(phys.rotation.pitch, phys.rotation.yaw, phys.rotation.roll)
        physics = PhysicsData(pos, vel, ang, rot)
        on_ground = bool(p_car.has_wheel_contact)
        has_flip = not bool(p_car.double_jumped) and not on_ground
        return CarData(
            physics=physics,
            team_num=int(p_car.team),
            boost_amount=float(p_car.boost),
            on_ground=on_ground,
            has_flip=has_flip,
            is_demoed=bool(p_car.is_demolished),
            has_jumped=bool(p_car.jumped)
        )

    own = parse_car(packet.game_cars[own_index])
    opp = parse_car(packet.game_cars[opponent_index])

    b_phys = packet.game_ball.physics
    b_pos = [b_phys.location.x, b_phys.location.y, b_phys.location.z]
    b_vel = [b_phys.velocity.x, b_phys.velocity.y, b_phys.velocity.z]
    b_ang = [b_phys.angular_velocity.x, b_phys.angular_velocity.y, b_phys.angular_velocity.z]
    b_rot = rotation_to_matrix(b_phys.rotation.pitch, b_phys.rotation.yaw, b_phys.rotation.roll)
    ball = PhysicsData(b_pos, b_vel, b_ang, b_rot)

    timers = np.zeros(len(BOOST_LOCATIONS), dtype=np.float32)
    if hasattr(packet, 'game_boosts') and len(packet.game_boosts) == len(BOOST_LOCATIONS):
        for i in range(len(BOOST_LOCATIONS)):
            b = packet.game_boosts[i]
            timers[i] = float(b.timer) if not b.is_active else 0.0

    return StandardGameState(own, opp, ball, timers, tick_count=tick_count)

def _transform_physics(phys: PhysicsData, invert: bool, mirror: bool):
    sign = np.array([-1.0, -1.0, 1.0] if invert else [1.0, 1.0, 1.0], dtype=np.float32)
    pos = phys.position * sign
    vel = phys.linear_velocity * sign
    ang = phys.angular_velocity * sign
    rot = sign[:, None] * phys.rotation_mtx
    if mirror:
        pos = pos * np.array([-1.0, 1.0, 1.0], dtype=np.float32)
        vel = vel * np.array([-1.0, 1.0, 1.0], dtype=np.float32)
        ang = ang * np.array([1.0, -1.0, -1.0], dtype=np.float32)
        rot = np.array([-1.0, 1.0, 1.0], dtype=np.float32)[:, None] * rot
        rot[:, 1] *= -1.0
    return pos, vel, ang, rot

def _player_features(car: CarData, invert: bool, mirror: bool, ball_pos_vel):
    pos, vel, ang, rot = _transform_physics(car.physics, invert, mirror)
    ball_pos, ball_vel = ball_pos_vel
    return np.concatenate((
        pos / 5000.0,
        rot[:, 0],
        rot[:, 2],
        vel / 2300.0,
        ang / 3.0,
        (ang @ rot) / 3.0,
        ((ball_pos - pos) @ rot) / 5000.0,
        ((ball_vel - vel) @ rot) / 2300.0,
        [
            car.boost_amount / 100.0,
            float(car.on_ground),
            float(car.on_ground or car.has_flip),
            float(car.is_demoed),
            float(car.has_jumped)
        ]
    )).astype(np.float32)

class BallForecastEngine:
    """Predicts ball trajectory 5 samples into future: [30, 60, 120, 180, 240] ticks."""
    def __init__(self):
        self._arena = None
        try:
            import rocketsim as rs
            self._rs = rs
            self._arena = rs.Arena(rs.GameMode.SOCCAR)
        except Exception:
            self._rs = None

    def predict(self, ball_physics: PhysicsData, rlbot_ball_prediction=None) -> np.ndarray:
        # 1. If RLBot ball prediction struct is provided, use it directly (ground-truth game physics)
        if rlbot_ball_prediction is not None and hasattr(rlbot_ball_prediction, 'slices'):
            samples = []
            target_ticks = [30, 60, 120, 180, 240]
            num_slices = rlbot_ball_prediction.num_slices
            for t in target_ticks:
                slice_idx = min(t // 2, num_slices - 1)
                s = rlbot_ball_prediction.slices[slice_idx]
                p = s.physics
                samples.append([
                    p.location.x, p.location.y, p.location.z,
                    p.velocity.x, p.velocity.y, p.velocity.z
                ])
            return np.array(samples, dtype=np.float32)

        # 2. If RocketSim is available, simulate future ticks
        if self._arena is not None:
            rs = self._rs
            self._arena.ball.set_state(rs.BallState(
                pos=rs.Vec(*ball_physics.position),
                vel=rs.Vec(*ball_physics.linear_velocity),
                ang_vel=rs.Vec(*ball_physics.angular_velocity)
            ))
            pred = np.empty((245, 6), dtype=np.float32)
            for i in range(245):
                b = self._arena.ball.get_state()
                pred[i] = [*b.pos.as_numpy(), *b.vel.as_numpy()]
                if i < 244:
                    self._arena.step(1)
            return pred[[30, 60, 120, 180, 240]].copy()

        # 3. Analytic ballistic trajectory fallback
        pos = ball_physics.position.copy()
        vel = ball_physics.linear_velocity.copy()
        samples = []
        dt = 1.0 / 120.0
        gravity = np.array([0.0, 0.0, -650.0], dtype=np.float32)
        curr_p = pos.copy()
        curr_v = vel.copy()
        for t in range(241):
            if t in (30, 60, 120, 180, 240):
                samples.append(np.concatenate([curr_p, curr_v]))
            curr_v += gravity * dt
            curr_p += curr_v * dt
            if curr_p[2] < 93.0:
                curr_p[2] = 93.0
                curr_v[2] = -curr_v[2] * 0.6
        return np.array(samples, dtype=np.float32)

def build_features(state: StandardGameState, agent_id: int, previous_action: np.ndarray,
                   kind: str, ball_forecast: np.ndarray = None) -> tuple[np.ndarray, bool]:
    """Constructs native features: 225 for Chronos, 258 for Galactus."""
    own = state.cars[agent_id]
    other_id = 1 if agent_id == 0 else 0
    other = state.cars[other_id]

    invert = (own.team_num == 1)
    # Chronos mirrors when on right side of field to reduce state space
    mirror = (kind == 'chronos' and own.physics.position[0] * (-1.0 if invert else 1.0) > 0.0)

    ball_pos, ball_vel, ball_ang, _ = _transform_physics(state.ball, invert, mirror)
    ball_pos_vel = (ball_pos, ball_vel)

    prev = np.asarray(previous_action, dtype=np.float32).copy()
    timers = state.boost_pad_timers[::-1] if invert else state.boost_pad_timers
    pads = (timers == 0.0)

    timer_features = timers[::-1] if kind == 'chronos' else timers
    features = np.where(pads, 1.0, 1.0 / (1.0 + timer_features)).astype(np.float32)

    if mirror:
        features = features[MIRROR_PADS]
        prev[[1, 3, 4]] *= -1.0

    parts = [
        ball_pos / 5000.0,
        ball_vel / 2300.0,
        ball_ang / 3.0,
        prev,
        features
    ]

    if kind == 'galactus':
        pos = own.physics.position * np.array([-1.0, -1.0, 1.0] if invert else [1.0, 1.0, 1.0], dtype=np.float32)
        relative = np.zeros(3, dtype=np.float32)
        distance = 1500.0 ** 2
        for i in BIG_PAD_INDICES:
            delta = BOOST_LOCATIONS[i] - pos
            d = float(np.square(delta[:2]).sum())
            if pads[i] and d <= distance:
                relative = delta
                distance = d
        parts.append(relative / 5000.0)

    # Own car features (29) + 58 zeros for 3v3 slot compatibility
    parts.extend([
        _player_features(own, invert, mirror, ball_pos_vel),
        np.zeros(58, dtype=np.float32)
    ])

    # Opponent car features (slot 0 by default for 1v1, rest zeros)
    slots = np.zeros((3, 29), dtype=np.float32)
    slots[0] = _player_features(other, invert, mirror, ball_pos_vel)
    parts.append(slots.ravel())

    if kind == 'galactus':
        if ball_forecast is None or ball_forecast.shape != (5, 6):
            raise ValueError(f"Expected 5x6 ball prediction, got {ball_forecast.shape if ball_forecast is not None else None}")
        pred = ball_forecast.copy()
        if invert:
            pred *= np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0], dtype=np.float32)
        pred[:, :3] /= 5000.0
        pred[:, 3:] /= 2300.0
        parts.append(pred.ravel())

    out = np.concatenate(parts).astype(np.float32)
    expected = 225 if kind == 'chronos' else 258
    if out.shape != (expected,):
        raise ValueError(f"Expected {expected} features for {kind}, got {out.shape}")
    return out, mirror
