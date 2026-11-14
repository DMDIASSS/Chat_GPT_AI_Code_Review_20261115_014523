"""
Zenith Live 3D Spectator
Real-time 60 FPS 3D visualization of Zenith playing Rocket League via RLViser.
Features:
- Real-time 3D arena rendering using native RLViser engine (no Rocket League installation required).
- Continuous weight hot-reloading: automatically updates policy weights whenever training saves a new checkpoint.
- Self-play match mode (Zenith Blue vs Zenith Orange) or target practice / drill modes.
- Goal detection, live scoreboard, touch statistics, and automatic kickoff resets.
- Zero training disruption: runs read-only on CPU or GPU without interfering with background training.
"""
from __future__ import annotations

import os
import sys
import time
import math
import random
import argparse
from pathlib import Path
import psutil
import numpy as np
import torch

# Ensure zenith is cwd so rlviser_py automatically launches zenith\rlviser.exe (Rocket League follow-cam build)
APP_ROOT = Path(r"E:\Downloads\Chat_GPT_AI")
ZENITH_ROOT = APP_ROOT / "zenith"
os.chdir(str(ZENITH_ROOT))
sys.path.insert(0, str(ZENITH_ROOT))

import RocketSim as rs
import rlviser_py as rlv
from zenith.policy import ZenithPolicy


# ---------------------------------------------------------------------------
# 90-Action Lookup Table (1-to-1 match with RLGymCPP DefaultAction)
# ---------------------------------------------------------------------------
def make_action_table() -> tuple[np.ndarray, int]:
    r_b = [0.0, 1.0]
    r_f = [-1.0, 0.0, 1.0]
    actions = []

    # Ground actions (24)
    for throttle in r_f:
        for steer in r_f:
            for boost in r_b:
                for handbrake in r_b:
                    if boost == 1.0 and throttle != 1.0:
                        continue
                    actions.append([throttle, steer, 0.0, steer, 0.0, 0.0, boost, handbrake])

    num_ground = len(actions)

    # Aerial actions (66)
    for pitch in r_f:
        for yaw in r_f:
            for roll in r_f:
                for jump in r_b:
                    for boost in r_b:
                        if jump == 1.0 and yaw != 0.0:
                            continue
                        if pitch == roll and roll == jump and jump == 0.0:
                            continue
                        handbrake = 1.0 if (jump == 1.0 and (pitch != 0.0 or yaw != 0.0 or roll != 0.0)) else 0.0
                        actions.append([boost, yaw, pitch, yaw, roll, jump, boost, handbrake])

    return np.array(actions, dtype=np.float32), num_ground


def make_action_masks(actions: np.ndarray, num_ground: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ground_mask = np.zeros(len(actions), dtype=bool)
    air_mask = np.zeros(len(actions), dtype=bool)
    jump_mask = np.zeros(len(actions), dtype=bool)
    boost_mask = np.zeros(len(actions), dtype=bool)

    for i in range(len(actions)):
        a = actions[i]
        throttle, steer, pitch, yaw, roll, jump, boost, handbrake = a

        if jump > 0.5:
            jump_mask[i] = True
        if boost > 0.5:
            boost_mask[i] = True
        if i < num_ground:
            ground_mask[i] = True
        if i >= num_ground and jump <= 0.5:
            air_mask[i] = True

        # Add additional yaw-only actions to air mask (matches RLGymCPP DefaultAction)
        if i < num_ground:
            if throttle == boost and (yaw != 0.0) == (handbrake > 0.5):
                air_mask[i] = True

    return ground_mask, air_mask, jump_mask, boost_mask


def get_action_mask(
    car_state: rs.CarState,
    ground_mask: np.ndarray,
    air_mask: np.ndarray,
    jump_mask: np.ndarray,
    boost_mask: np.ndarray
) -> np.ndarray:
    if car_state.is_on_ground:
        mask = ground_mask.copy()
    else:
        mask = air_mask.copy()

    if car_state.has_flip_or_jump:
        mask |= jump_mask

    if car_state.boost <= 0.0:
        mask &= ~boost_mask

    if not mask.any():
        mask[:] = True
    return mask


# ---------------------------------------------------------------------------
# Vector Math & 145-Dim Observation Builder
# ---------------------------------------------------------------------------
def build_observation(
    car: rs.Car,
    opp: rs.Car,
    arena: rs.Arena,
    tracker: rs.BallPredictor,
    prev_act: list[float] | None = None,
    is_orange: bool = False
) -> np.ndarray:
    cs = car.get_state()
    opp_cs = opp.get_state()
    bs = arena.ball.get_state()

    s = -1.0 if is_orange else 1.0
    c_p = rs.Vec(s * cs.pos.x, s * cs.pos.y, cs.pos.z)
    c_v = rs.Vec(s * cs.vel.x, s * cs.vel.y, cs.vel.z)
    c_f = rs.Vec(s * cs.rot_mat.forward.x, s * cs.rot_mat.forward.y, cs.rot_mat.forward.z)
    c_u = rs.Vec(s * cs.rot_mat.up.x, s * cs.rot_mat.up.y, cs.rot_mat.up.z)
    c_r = rs.Vec(c_f.y * c_u.z - c_f.z * c_u.y, c_f.z * c_u.x - c_f.x * c_u.z, c_f.x * c_u.y - c_f.y * c_u.x)

    def to_loc(v: rs.Vec) -> list[float]:
        return [
            c_f.x * v.x + c_f.y * v.y + c_f.z * v.z,
            c_r.x * v.x + c_r.y * v.y + c_r.z * v.z,
            c_u.x * v.x + c_u.y * v.y + c_u.z * v.z
        ]

    b_p = rs.Vec(s * bs.pos.x, s * bs.pos.y, bs.pos.z)
    b_v = rs.Vec(s * bs.vel.x, s * bs.vel.y, bs.vel.z)
    b_ang = rs.Vec(s * bs.ang_vel.x, s * bs.ang_vel.y, bs.ang_vel.z)

    rel_b_p = to_loc(rs.Vec(b_p.x - c_p.x, b_p.y - c_p.y, b_p.z - c_p.z))
    rel_b_v = to_loc(rs.Vec(b_v.x - c_v.x, b_v.y - c_v.y, b_v.z - c_v.z))
    rel_b_ang = to_loc(b_ang)

    obs: list[float] = []

    # 1. Local Ball Physics (9 floats)
    obs.extend([rel_b_p[0] / 5000.0, rel_b_p[1] / 5000.0, rel_b_p[2] / 5000.0])
    obs.extend([rel_b_v[0] / 2300.0, rel_b_v[1] / 2300.0, rel_b_v[2] / 2300.0])
    obs.extend([rel_b_ang[0] / 3.0,    rel_b_ang[1] / 3.0,    rel_b_ang[2] / 3.0])

    # 2. Self Car World & Local Kinematics (15 floats)
    obs.extend([c_p.x / 5000.0, c_p.y / 5000.0, c_p.z / 2000.0])
    obs.extend([c_f.x, c_f.y, c_f.z])
    obs.extend([c_u.x, c_u.y, c_u.z])
    loc_c_vel = to_loc(c_v)
    obs.extend([loc_c_vel[0] / 2300.0, loc_c_vel[1] / 2300.0, loc_c_vel[2] / 2300.0])
    loc_c_ang = to_loc(rs.Vec(s * cs.ang_vel.x, s * cs.ang_vel.y, cs.ang_vel.z))
    obs.extend([loc_c_ang[0] / 5.5, loc_c_ang[1] / 5.5, loc_c_ang[2] / 5.5])

    # 3. Mechanics & Resets (6 floats - HasFlipReset is strictly false on ground)
    has_reset = (not cs.is_on_ground) and cs.has_flip_reset
    obs.append(cs.boost / 100.0)
    obs.append(1.0 if cs.is_on_ground else 0.0)
    obs.append(1.0 if cs.has_flip_or_jump else 0.0)
    obs.append(1.0 if has_reset else 0.0)
    obs.append(1.0 if cs.is_flipping else 0.0)
    wheels = sum(1 for w in cs.wheels_with_contact if w)
    obs.append(float(wheels) / 4.0)

    # 4. Previous Action (8 floats)
    if prev_act is None:
        obs.extend([0.0] * 8)
    else:
        obs.extend(prev_act)

    # 5. Opponent Local Kinematics (13 floats)
    o_p = rs.Vec(s * opp_cs.pos.x, s * opp_cs.pos.y, opp_cs.pos.z)
    o_v = rs.Vec(s * opp_cs.vel.x, s * opp_cs.vel.y, opp_cs.vel.z)
    o_f = rs.Vec(s * opp_cs.rot_mat.forward.x, s * opp_cs.rot_mat.forward.y, opp_cs.rot_mat.forward.z)
    o_u = rs.Vec(s * opp_cs.rot_mat.up.x, s * opp_cs.rot_mat.up.y, opp_cs.rot_mat.up.z)
    rel_o_p = to_loc(rs.Vec(o_p.x - c_p.x, o_p.y - c_p.y, o_p.z - c_p.z))
    rel_o_v = to_loc(rs.Vec(o_v.x - c_v.x, o_v.y - c_v.y, o_v.z - c_v.z))
    opp_fwd = to_loc(o_f)
    opp_up = to_loc(o_u)
    obs.extend([rel_o_p[0] / 5000.0, rel_o_p[1] / 5000.0, rel_o_p[2] / 5000.0])
    obs.extend([rel_o_v[0] / 2300.0, rel_o_v[1] / 2300.0, rel_o_v[2] / 2300.0])
    obs.extend(opp_fwd)
    obs.extend(opp_up)
    obs.append(opp_cs.boost / 100.0)

    # 6. Boost Pads (34 floats)
    pads = list(arena.get_boost_pads())
    if is_orange:
        pads = list(reversed(pads))
    for p in pads:
        obs.append(1.0 if p.get_state().is_active else 0.0)

    # 7. Ball Prediction Horizon (30 floats)
    preds = tracker.get_ball_prediction(bs, 0, 150, 1)
    for t in [12, 30, 60, 96, 144]:
        pr = preds[t]
        pr_p = rs.Vec(s * pr.pos.x, s * pr.pos.y, pr.pos.z)
        pr_v = rs.Vec(s * pr.vel.x, s * pr.vel.y, pr.vel.z)
        p_loc = to_loc(rs.Vec(pr_p.x - c_p.x, pr_p.y - c_p.y, pr_p.z - c_p.z))
        v_loc = to_loc(rs.Vec(pr_v.x - c_v.x, pr_v.y - c_v.y, pr_v.z - c_v.z))
        obs.extend([p_loc[0] / 5000.0, p_loc[1] / 5000.0, p_loc[2] / 5000.0])
        obs.extend([v_loc[0] / 2300.0, v_loc[1] / 2300.0, v_loc[2] / 2300.0])

    # Zero pad to 145 floats
    while len(obs) < 145:
        obs.append(0.0)

    return np.array(obs, dtype=np.float32)


# ---------------------------------------------------------------------------
# Kickoff & Scenario Spawning
# ---------------------------------------------------------------------------
KICKOFF_CONFIGS = [
    # Center face-off
    {"blue": (0.0, -4600.0, 17.0, math.pi / 2), "orange": (0.0, 4600.0, 17.0, -math.pi / 2)},
    # Diagonal right blue / diagonal left orange
    {"blue": (2048.0, -2560.0, 17.0, 3 * math.pi / 4), "orange": (-2048.0, 2560.0, 17.0, -math.pi / 4)},
    # Diagonal left blue / diagonal right orange
    {"blue": (-2048.0, -2560.0, 17.0, math.pi / 4), "orange": (2048.0, 2560.0, 17.0, -3 * math.pi / 4)},
    # Off-center blue / off-center orange
    {"blue": (-256.0, -3840.0, 17.0, math.pi / 2), "orange": (256.0, 3840.0, 17.0, -math.pi / 2)},
    {"blue": (256.0, -3840.0, 17.0, math.pi / 2), "orange": (-256.0, 3840.0, 17.0, -math.pi / 2)},
]


def reset_scenario(arena: rs.Arena, car_blue: rs.Car, car_orange: rs.Car, scenario: str = "kickoff"):
    if scenario == "clash":
        # Ball at center, both cars close and charging
        bs = rs.BallState()
        bs.pos = rs.Vec(0.0, 0.0, 93.15)
        bs.vel = rs.Vec(0.0, 0.0, 0.0)
        bs.ang_vel = rs.Vec(0.0, 0.0, 0.0)
        arena.ball.set_state(bs)

        cs_b = rs.CarState()
        cs_b.pos = rs.Vec(0.0, -1200.0, 17.0)
        cs_b.vel = rs.Vec(0.0, 500.0, 0.0)
        cs_b.rot_mat = rs.Angle(math.pi / 2, 0.0, 0.0).as_rot_mat()
        cs_b.boost = 50.0
        cs_b.is_on_ground = True
        car_blue.set_state(cs_b)

        cs_o = rs.CarState()
        cs_o.pos = rs.Vec(0.0, 1200.0, 17.0)
        cs_o.vel = rs.Vec(0.0, -500.0, 0.0)
        cs_o.rot_mat = rs.Angle(-math.pi / 2, 0.0, 0.0).as_rot_mat()
        cs_o.boost = 50.0
        cs_o.is_on_ground = True
        car_orange.set_state(cs_o)

    elif scenario == "aerial":
        # High floating ball with upward arc
        bs = rs.BallState()
        bs.pos = rs.Vec(0.0, 0.0, 800.0)
        bs.vel = rs.Vec(0.0, 0.0, 300.0)
        bs.ang_vel = rs.Vec(0.0, 0.0, 0.0)
        arena.ball.set_state(bs)

        cs_b = rs.CarState()
        cs_b.pos = rs.Vec(0.0, -1800.0, 17.0)
        cs_b.vel = rs.Vec(0.0, 800.0, 0.0)
        cs_b.rot_mat = rs.Angle(math.pi / 2, 0.0, 0.0).as_rot_mat()
        cs_b.boost = 100.0
        cs_b.is_on_ground = True
        car_blue.set_state(cs_b)

        cs_o = rs.CarState()
        cs_o.pos = rs.Vec(0.0, 1800.0, 17.0)
        cs_o.vel = rs.Vec(0.0, -800.0, 0.0)
        cs_o.rot_mat = rs.Angle(-math.pi / 2, 0.0, 0.0).as_rot_mat()
        cs_o.boost = 100.0
        cs_o.is_on_ground = True
        car_orange.set_state(cs_o)

    elif scenario == "dribble":
        # Blue carrying ball towards Orange net
        bs = rs.BallState()
        bs.pos = rs.Vec(0.0, -500.0, 180.0)
        bs.vel = rs.Vec(0.0, 1100.0, 0.0)
        arena.ball.set_state(bs)

        cs_b = rs.CarState()
        cs_b.pos = rs.Vec(0.0, -600.0, 17.0)
        cs_b.vel = rs.Vec(0.0, 1100.0, 0.0)
        cs_b.rot_mat = rs.Angle(math.pi / 2, 0.0, 0.0).as_rot_mat()
        cs_b.boost = 80.0
        cs_b.is_on_ground = True
        car_blue.set_state(cs_b)

        cs_o = rs.CarState()
        cs_o.pos = rs.Vec(0.0, 3200.0, 17.0)
        cs_o.vel = rs.Vec(0.0, 0.0, 0.0)
        cs_o.rot_mat = rs.Angle(-math.pi / 2, 0.0, 0.0).as_rot_mat()
        cs_o.boost = 100.0
        cs_o.is_on_ground = True
        car_orange.set_state(cs_o)

    else:
        # Standard kickoff
        cfg = random.choice(KICKOFF_CONFIGS)

        bs = rs.BallState()
        bs.pos = rs.Vec(0.0, 0.0, 93.15)
        bs.vel = rs.Vec(0.0, 0.0, 0.0)
        bs.ang_vel = rs.Vec(0.0, 0.0, 0.0)
        arena.ball.set_state(bs)

        bx, by, bz, byaw = cfg["blue"]
        cs_b = rs.CarState()
        cs_b.pos = rs.Vec(bx, by, bz)
        cs_b.vel = rs.Vec(0.0, 0.0, 0.0)
        cs_b.ang_vel = rs.Vec(0.0, 0.0, 0.0)
        cs_b.rot_mat = rs.Angle(byaw, 0.0, 0.0).as_rot_mat()
        cs_b.boost = 33.3
        cs_b.is_on_ground = True
        car_blue.set_state(cs_b)

        ox, oy, oz, oyaw = cfg["orange"]
        cs_o = rs.CarState()
        cs_o.pos = rs.Vec(ox, oy, oz)
        cs_o.vel = rs.Vec(0.0, 0.0, 0.0)
        cs_o.ang_vel = rs.Vec(0.0, 0.0, 0.0)
        cs_o.rot_mat = rs.Angle(oyaw, 0.0, 0.0).as_rot_mat()
        cs_o.boost = 33.3
        cs_o.is_on_ground = True
        car_orange.set_state(cs_o)

    # Reset all boost pads to active
    for p in arena.get_boost_pads():
        ps = p.get_state()
        ps.is_active = True
        ps.cooldown = 0.0
        p.set_state(ps)


reset_to_kickoff = reset_scenario


# ---------------------------------------------------------------------------
# Main Spectator Loop
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Zenith Live 3D Spectator")
    parser.add_argument("--opponent", choices=["self", "idle", "random"], default="self",
                        help="Opponent mode (self = mirror self-play, idle = target, random = semi-random)")
    parser.add_argument("--scenario", choices=["kickoff", "clash", "aerial", "dribble"], default="kickoff",
                        help="Match start scenario (kickoff = standard 1v1, clash = close face-off, aerial = high ball, dribble = ball carry)")
    parser.add_argument("--fps", type=int, default=60, help="Target visualizer FPS (default: 60)")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu",
                        help="Device for inference (default: cpu leaves 100%% GPU for training)")
    args = parser.parse_args()

    print("=" * 70)
    print("                ZENITH REAL-TIME 3D LIVE SPECTATOR")
    print("=" * 70)
    print(" * Viewer Engine : Native RLViser 3D Renderer (Standalone Window)")
    print(" * Policy Model  : Zenith Dual-Trunk Actor-Critic (256-width, ~231k params)")
    print(f" * Opponent Mode : {args.opponent.upper()} (Blue = Zenith, Orange = Opponent)")
    print(f" * Scenario Mode : {args.scenario.upper()}")
    print(" * Hot-Reloading : ACTIVE (watches for fresh training checkpoints)")
    print(" * Training Safety: 100% Read-Only (Zero interruption to background training)")
    print("=" * 70)

    # 0. Clean up any stale or dangling RLViser instances from prior sessions
    for proc in psutil.process_iter(['name']):
        try:
            if 'rlviser' in (proc.info['name'] or '').lower():
                proc.kill()
        except Exception:
            pass
    time.sleep(0.3)

    # 1. Initialize RocketSim
    mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
    rs.init(mesh_dir)

    arena = rs.Arena(rs.GameMode.SOCCAR)
    car_blue = arena.add_car(rs.Team.BLUE, rs.CarConfig(rs.CarConfig.OCTANE))
    car_orange = arena.add_car(rs.Team.ORANGE, rs.CarConfig(rs.CarConfig.OCTANE))
    tracker = rs.BallPredictor()

    # 2. Setup RLViser (Single-instance: rlv.render will connect or spawn exactly 1 instance)
    print("[Spectator] Connecting to RLViser (Single-Instance 3D Renderer)...")
    locs = [p.get_pos().as_tuple() for p in arena.get_boost_pads()]
    rlv.set_boost_pad_locations(locs)

    # 3. Action table & masks matching C++ DefaultAction
    action_table, num_ground = make_action_table()
    ground_mask, air_mask, jump_mask, boost_mask = make_action_masks(action_table, num_ground)

    # 4. Load Policy
    device = torch.device(args.device if (args.device == "cuda" and torch.cuda.is_available()) else "cpu")
    policy = ZenithPolicy(145, 90, 256).to(device)
    policy.eval()

    # Track checkpoint mtime for hot-reload
    export_pt = ZENITH_ROOT / "export" / "zenith_rlbot" / "zenith.pt"
    ckpt_pt = ZENITH_ROOT / "runs" / "zenith_scratch_01" / "checkpoints" / "latest_checkpoint.pt"

    last_loaded_mtime = 0.0
    current_step = 0
    current_iteration = 0

    current_stage_name = "Stage 2"

    def try_reload():
        nonlocal last_loaded_mtime, current_step, current_iteration, current_stage_name
        # Prefer full checkpoint with training metadata if available
        target_path = ckpt_pt if ckpt_pt.exists() else export_pt
        if not target_path.exists():
            return False

        try:
            mtime = target_path.stat().st_mtime
            if mtime > last_loaded_mtime:
                ckpt = torch.load(str(target_path), map_location=device)
                if isinstance(ckpt, dict) and "model" in ckpt:
                    policy.load_state_dict(ckpt["model"])
                    current_step = ckpt.get("total_steps", 0)
                    current_iteration = ckpt.get("iteration", 0)
                    director = ckpt.get("director", {})
                    stg_num = director.get("stage", 3) if isinstance(director, dict) else ckpt.get("stage", 3)
                    stage_map = {
                        0: "Stage 0 (Bronze-Silver)",
                        1: "Stage 1 (Gold-Plat)",
                        2: "Stage 2 (Diamond-Champ)",
                        3: "Stage 3 (GC-SSL)"
                    }
                    current_stage_name = stage_map.get(stg_num, f"Stage {stg_num}")
                elif isinstance(ckpt, dict) and "student_state_dict" in ckpt:
                    policy.load_state_dict(ckpt["student_state_dict"])
                    current_step = ckpt.get("total_steps", 0)
                    current_iteration = ckpt.get("iteration", 0)
                elif isinstance(ckpt, dict):
                    policy.load_state_dict(ckpt)
                last_loaded_mtime = mtime
                return True
        except Exception:
            pass
        return False

    if try_reload():
        print(f"[Spectator] Initial weights loaded! Step: {current_step:,} | Iter: {current_iteration:,} | {current_stage_name}")
    else:
        print("[Spectator] Initial weights loaded (Fresh). Waiting for training checkpoint...")

    reset_scenario(arena, car_blue, car_orange, args.scenario)

    # Telemetry and scoreboard
    score_blue = 0
    score_orange = 0
    touches_blue = 0
    touches_orange = 0
    last_touch_car_id = 0

    prev_act_blue = [0.0] * 8
    prev_act_orange = [0.0] * 8

    # Frame timing
    tick_skip = 8
    action_delay = 7
    phys_subticks = 2  # 2 physics ticks per render frame -> 60 render FPS at 120Hz physics
    target_dt = 1.0 / max(1, args.fps)

    ticks_since_decision = 0
    goal_cooldown = 0
    frame_count = 0
    packet_id = 0
    last_stat_time = time.time()

    print("\n[RLViser Camera Controls]")
    print("  * Key '1' : Lock camera onto Zenith (Blue)")
    print("  * Key '2' : Lock camera onto Opponent (Orange)")
    print("  * Key 'C' : Toggle Ball Cam / Free Cam")
    print("  * Key 'F' : Free Fly Spectator Mode")
    print("  * Left-Click + Drag : Rotate camera | Right-Click + Drag : Pan | Scroll : Zoom")
    print("  * Spacebar : Pause/Resume simulation | Ctrl+C in terminal : Exit\n")

    try:
        while True:
            t0 = time.perf_counter()

            # Check RLViser pause state
            if rlv.get_game_paused():
                time.sleep(0.05)
                continue

            # Hot-reload check every 60 frames (~1 sec)
            frame_count += 1
            if frame_count % 60 == 0:
                if try_reload():
                    print(f" >>> [HOT-RELOAD] New weights applied! Current Training Progress: {current_step:,} steps (Iter {current_iteration})")

            # Check decision step (every 8 physics ticks = ~15 decisions / sec)
            if ticks_since_decision >= tick_skip or ticks_since_decision == 0:
                # Blue Car Decision
                obs_b = build_observation(car_blue, car_orange, arena, tracker, prev_act_blue, is_orange=False)
                mask_b = get_action_mask(car_blue.get_state(), ground_mask, air_mask, jump_mask, boost_mask)
                obs_t_b = torch.from_numpy(obs_b).unsqueeze(0).to(device)
                mask_t_b = torch.from_numpy(mask_b).unsqueeze(0).to(device)

                with torch.inference_mode():
                    act_b_idx, _, _ = policy.get_action(obs_t_b, mask_t_b, temperature=0.20, deterministic=False)
                act_b = action_table[act_b_idx.item()]
                prev_act_blue = list(act_b)

                ctrl_b = rs.CarControls()
                ctrl_b.throttle = float(act_b[0])
                ctrl_b.steer = float(act_b[1])
                ctrl_b.pitch = float(act_b[2])
                ctrl_b.yaw = float(act_b[3])
                ctrl_b.roll = float(act_b[4])
                ctrl_b.jump = bool(act_b[5] > 0.5)
                ctrl_b.boost = bool(act_b[6] > 0.5)
                ctrl_b.handbrake = bool(act_b[7] > 0.5)
                car_blue.set_controls(ctrl_b)

                # Orange Car Decision
                if args.opponent == "self":
                    obs_o = build_observation(car_orange, car_blue, arena, tracker, prev_act_orange, is_orange=True)
                    mask_o = get_action_mask(car_orange.get_state(), ground_mask, air_mask, jump_mask, boost_mask)
                    obs_t_o = torch.from_numpy(obs_o).unsqueeze(0).to(device)
                    mask_t_o = torch.from_numpy(mask_o).unsqueeze(0).to(device)

                    with torch.inference_mode():
                        act_o_idx, _, _ = policy.get_action(obs_t_o, mask_t_o, temperature=0.20, deterministic=False)
                    act_o = action_table[act_o_idx.item()]
                    prev_act_orange = list(act_o)

                    ctrl_o = rs.CarControls()
                    ctrl_o.throttle = float(act_o[0])
                    ctrl_o.steer = float(act_o[1])
                    ctrl_o.pitch = float(act_o[2])
                    ctrl_o.yaw = float(act_o[3])
                    ctrl_o.roll = float(act_o[4])
                    ctrl_o.jump = bool(act_o[5] > 0.5)
                    ctrl_o.boost = bool(act_o[6] > 0.5)
                    ctrl_o.handbrake = bool(act_o[7] > 0.5)
                    car_orange.set_controls(ctrl_o)
                elif args.opponent == "random":
                    ctrl_o = rs.CarControls()
                    ctrl_o.throttle = random.choice([-1.0, 1.0, 1.0])
                    ctrl_o.steer = random.choice([-1.0, 0.0, 1.0])
                    ctrl_o.boost = random.random() < 0.3
                    car_orange.set_controls(ctrl_o)
                else:
                    # idle
                    car_orange.set_controls(rs.CarControls())

                ticks_since_decision = 0

            # Step physics by phys_subticks (2 ticks)
            arena.step(phys_subticks)
            ticks_since_decision += phys_subticks

            # Touch tracking
            bs = arena.ball.get_state()
            cs_b = car_blue.get_state()
            cs_o = car_orange.get_state()

            # Check ball contact
            if cs_b.ball_hit_info.is_valid and cs_b.ball_hit_info.tick_count_when_hit == arena.tick_count:
                touches_blue += 1
                last_touch_car_id = car_blue.id
            if cs_o.ball_hit_info.is_valid and cs_o.ball_hit_info.tick_count_when_hit == arena.tick_count:
                touches_orange += 1
                last_touch_car_id = car_orange.id

            # Goal detection (standard soccar goal: y > 5120 is Orange goal / Blue scores; y < -5120 is Blue goal / Orange scores)
            if goal_cooldown > 0:
                goal_cooldown -= 1
                if goal_cooldown == 0:
                    reset_scenario(arena, car_blue, car_orange, args.scenario)
                    ticks_since_decision = 0
            else:
                if bs.pos.y > 5120.0 and abs(bs.pos.x) < 893.0 and bs.pos.z < 642.0:
                    score_blue += 1
                    print(f"  ⚽ [GOAL] BLUE (Zenith) SCORES! Score: Blue {score_blue} - {score_orange} Orange")
                    goal_cooldown = 45  # ~0.75s celebration pause
                elif bs.pos.y < -5120.0 and abs(bs.pos.x) < 893.0 and bs.pos.z < 642.0:
                    score_orange += 1
                    print(f"  ⚽ [GOAL] ORANGE SCORES! Score: Blue {score_blue} - {score_orange} Orange")
                    goal_cooldown = 45

            # Render to RLViser
            packet_id += 1
            pads = [p.get_state().is_active for p in arena.get_boost_pads()]
            cars = [
                (1, 0, rs.CarConfig(rs.CarConfig.OCTANE), car_blue.get_state()),
                (2, 1, rs.CarConfig(rs.CarConfig.OCTANE), car_orange.get_state())
            ]
            rlv.render(packet_id, float(args.fps), arena.game_mode, pads, bs, cars)

            # Periodic status line in terminal (every 3 seconds)
            now = time.time()
            if now - last_stat_time >= 3.0:
                b_vel = math.sqrt(cs_b.vel.x**2 + cs_b.vel.y**2 + cs_b.vel.z**2)
                b_boost = cs_b.boost
                print(f"[ZENITH LIVE] Score: Blue {score_blue} - {score_orange} Orange | Hits: B {touches_blue} / O {touches_orange} | Zenith Spd: {b_vel:4.0f} uu | Boost: {b_boost:3.0f}% | {current_stage_name} | Step: {current_step:,}")
                last_stat_time = now

            # Sleep to match target frame rate
            dt = time.perf_counter() - t0
            sleep_time = target_dt - dt
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[Spectator] Stopping spectator session...")
    finally:
        try:
            rlv.quit()
        except Exception:
            pass
        for proc in psutil.process_iter(['name']):
            try:
                if 'rlviser' in (proc.info['name'] or '').lower():
                    proc.kill()
            except Exception:
                pass
        print("[Spectator] RLViser closed cleanly. Happy training!")


if __name__ == "__main__":
    main()
