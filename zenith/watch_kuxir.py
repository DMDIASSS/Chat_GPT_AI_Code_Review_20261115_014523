"""Zenith Kuxir Pinch Real-Time 3D Spectator (RLViser).

Single-instance guaranteed 3D viewer that renders the learner bot attempting
wall-roll setups and supersonic Kuxir pinches against the arena wall.
Automatically hot-reloads freshly saved training checkpoints in real time.
"""
from __future__ import annotations

import os
import sys
import time
import math
import random
from pathlib import Path
from typing import Dict, Any
import numpy as np
import psutil
import torch

ZENITH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ZENITH_DIR.parent
if str(ZENITH_DIR) not in sys.path:
    sys.path.insert(0, str(ZENITH_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure CWD is zenith directory so rlviser_py finds zenith/rlviser.exe and settings.txt
os.chdir(str(ZENITH_DIR))

import rlviser_py as rlv
import RocketSim as rs
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
from kuxir_policy import KuxirActorCritic, NEXTO_STUDENT_PATH
from kuxir_env import KuxirMutator, make_kuxir_components

CKPT_PATH = ZENITH_DIR / "runs" / "kuxir_pinch" / "checkpoints" / "latest_checkpoint.pt"
BEST_PATH = ZENITH_DIR / "runs" / "kuxir_pinch" / "best_kuxir.pt"


def cleanup_stale_viewers():
    """Kills any orphaned RLViser instances and waits for UDP port 34254 to be free."""
    for proc in psutil.process_iter(['name']):
        try:
            name = (proc.info['name'] or '').lower()
            if 'rlviser' in name:
                proc.kill()
        except Exception:
            pass
    time.sleep(0.5)

    import socket
    for _ in range(15):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(('127.0.0.1', 34254))
            s.close()
            break
        except OSError:
            time.sleep(0.1)


def main():
    print("=" * 75)
    print("             ZENITH KUXIR PINCH 3D LIVE SPECTATOR")
    print("=" * 75)
    print(" * Viewer Engine : Standalone 3D RLViser (Single-Instance Follow-Cam)")
    print(" * Policy Model  : Zenith Kuxir Actor (512x512 MLP, 90 Actions)")
    print(" * Hot-Reloading : ACTIVE (watches training checkpoints automatically)")
    print(" * Sequence      : 1) 0-30 deg Wall Roll -> 2) Climb Bevel -> 3) Pinch Shot")
    print("=" * 75)

    # 1. Clean up old viewers to ensure exactly ONE instance opens
    cleanup_stale_viewers()

    # 2. Launch RLViser from zenith directory
    print("[Spectator] Launching single-instance RLViser 3D viewer...")
    rlv.launch()
    time.sleep(0.5)

    # 3. Setup RocketSim Engine
    engine = RocketSimEngine()
    team_mutator = FixedTeamSizeMutator(1, 1)
    kuxir_mutator = KuxirMutator(full_seq_ratio=0.50, climb_ratio=0.30)
    obs_builder, action_parser = make_kuxir_components()

    # Setup boost pad locations in viewer
    arena_internal = engine._arena
    locs = [p.get_pos().as_tuple() for p in arena_internal.get_boost_pads()]
    rlv.set_boost_pad_locations(locs)

    # 4. Load Policy Model
    device = torch.device("cpu")  # CPU is ultra-lightweight for single match spectator
    policy = KuxirActorCritic().to(device)

    last_loaded_mtime = 0.0
    current_iter = 0
    current_steps = 0
    best_pinch_speed = 0.0

    def reload_policy() -> bool:
        nonlocal last_loaded_mtime, current_iter, current_steps, best_pinch_speed
        target = BEST_PATH if BEST_PATH.exists() else (CKPT_PATH if CKPT_PATH.exists() else NEXTO_STUDENT_PATH)
        if not target.exists():
            return False

        try:
            mtime = target.stat().st_mtime
            if mtime > last_loaded_mtime:
                ckpt = torch.load(str(target), map_location=device)
                if isinstance(ckpt, dict) and "actor_state" in ckpt:
                    policy.actor.load_state_dict(ckpt["actor_state"])
                    current_iter = ckpt.get("iteration", 0)
                    current_steps = ckpt.get("total_steps", 0)
                    best_pinch_speed = ckpt.get("max_pinch_speed", 0.0)
                    print(f" >>> [HOT-RELOAD] Loaded checkpoint: Iter {current_iter} ({current_steps:,} steps) | Peak: {best_pinch_speed * 0.036:.1f} km/h")
                else:
                    # Raw state dict or base student
                    state_dict = {k.replace("model.", ""): v for k, v in ckpt.items()}
                    policy.actor.load_state_dict(state_dict)
                    print(f" >>> [LOADED] Base Nexto Student weights loaded ({target.name})")

                last_loaded_mtime = mtime
                policy.eval()
                return True
        except Exception as e:
            pass
        return False

    reload_policy()

    # 5. Reset Environment
    base = engine.create_base_state()
    team_mutator.apply(base, {})
    kuxir_mutator.apply(base, {})
    state = engine.set_state(base, {})

    packet_id = 0
    episode = 1
    episode_step = 0
    pinches_detected = 0
    goals_scored = 0
    session_peak_speed = 0.0

    last_touch_was_wall = False
    prev_ball_speed = 0.0

    target_fps = 60.0
    dt = 1.0 / target_fps
    tick_skip = 8
    frame_timer = time.perf_counter()

    action_lookup = action_parser._lookup_table

    print("\n[RLViser Controls]")
    print("  * '1' : Follow Zenith Learner Bot (Ball-Cam)")
    print("  * '2' : Follow Opponent / Arena")
    print("  * Spacebar : Pause / Resume 3D simulation")
    print("  * Left-Click Drag : Orbit camera | Right-Click Drag : Pan | Scroll : Zoom")
    print("  * Ctrl+C in terminal : Exit cleanly\n")

    try:
        while True:
            t0 = time.perf_counter()

            if rlv.get_game_paused():
                time.sleep(0.05)
                continue

            # Hot-reload check every ~1 sec (60 frames)
            if packet_id % 60 == 0:
                reload_policy()

            # -------------------------------------------------------------
            # Policy Step
            # -------------------------------------------------------------
            obs = obs_builder.build_obs(['blue-0'], state, {})['blue-0']
            obs_t = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)

            with torch.no_grad():
                act_t, _, _, _ = policy.get_action(obs_t, deterministic=True)

            act_id = int(act_t.item())
            parsed = action_parser.parse_actions({'blue-0': np.array([act_id])}, state, {})
            actions_raw = {
                'blue-0': parsed['blue-0'],
                'orange-0': np.zeros((8, 8), dtype=np.float32)
            }

            # Step physics by 8 ticks
            state = engine.step(actions_raw, {})
            episode_step += 1

            # -------------------------------------------------------------
            # Pinch Detection & Telemetry
            # -------------------------------------------------------------
            ball = state.ball
            bp = ball.position
            bv = ball.linear_velocity
            ball_spd = float(np.linalg.norm(bv))

            car_b = state.cars['blue-0']
            cp = car_b.physics.position
            cv_vel = car_b.physics.linear_velocity
            car_spd = float(np.linalg.norm(cv_vel))

            dist_wall = 4096.0 - abs(float(bp[0]))
            near_wall = dist_wall < 320.0 and float(bp[2]) > 180.0

            # Pinch event
            if car_b.ball_touches > 0 and near_wall and ball_spd > 1650.0:
                delta = ball_spd - prev_ball_speed
                if delta > 300.0:
                    pinches_detected += 1
                    kmh = ball_spd * 0.036
                    if ball_spd > session_peak_speed:
                        session_peak_speed = ball_spd
                    print(f"  >>> [KUXIR PINCH] Exit Velocity: {ball_spd:4.0f} uu/s ({kmh:5.1f} km/h) | Shot Y-Vel: {bv[1]:+4.0f}")

            # Goal event
            if state.goal_scored and float(bp[1]) > 5120.0:
                goals_scored += 1
                kmh = ball_spd * 0.036
                print(f"  >>> [GOAL SCORED] Cross-map pinch in the net! (Peak: {kmh:.1f} km/h)")
                time.sleep(0.4)
                # Reset
                base = engine.create_base_state()
                team_mutator.apply(base, {})
                kuxir_mutator.apply(base, {})
                state = engine.set_state(base, {})
                episode += 1
                episode_step = 0

            # Timeout reset: 220 steps (~15 seconds) so bot has ample time for the full sequence
            elif episode_step >= 220:
                base = engine.create_base_state()
                team_mutator.apply(base, {})
                kuxir_mutator.apply(base, {})
                state = engine.set_state(base, {})
                episode += 1
                episode_step = 0

            prev_ball_speed = ball_spd

            # -------------------------------------------------------------
            # Render to RLViser
            # -------------------------------------------------------------
            packet_id += 1
            pads = [p.get_state().is_active for p in arena_internal.get_boost_pads()]
            cars = [
                (1, 0, rs.CarConfig(rs.CarConfig.OCTANE), arena_internal.get_cars()[0].get_state()),
                (2, 1, rs.CarConfig(rs.CarConfig.OCTANE), arena_internal.get_cars()[1].get_state())
            ]
            rlv.render(packet_id, target_fps, rs.GameMode.SOCCAR, pads, arena_internal.ball.get_state(), cars)

            # Frame rate throttle (smooth 60 FPS)
            elapsed = time.perf_counter() - t0
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Periodic console HUD update
            if packet_id % 30 == 0:
                ctrls = action_lookup[act_id]
                ctrl_str = f"Thr:{ctrls[0]:+.0f} Steer:{ctrls[1]:+.0f} Jmp:{int(ctrls[5])} Bst:{int(ctrls[6])} Handbrake:{int(ctrls[7])}"
                if float(bp[2]) < 200.0 and abs(float(bp[0])) < 3700.0:
                    mode = "0-30 DEG ROLL SETUP"
                elif abs(float(bp[0])) >= 3700.0 and float(bp[2]) < 380.0:
                    mode = "WALL CLIMB BEVEL"
                else:
                    mode = "PINCH EXECUTION"
                print(
                    f"\r[{mode}] Ep {episode:3d} (Step {episode_step:3d}/220) | Car: {car_spd:4.0f} uu/s ({car_spd*0.036:4.1f} km/h) | "
                    f"Ball: {ball_spd:4.0f} uu/s ({ball_spd*0.036:4.1f} km/h) | "
                    f"Pinches: {pinches_detected} | Peak: {session_peak_speed*0.036:4.1f} km/h | {ctrl_str}    ",
                    end="", flush=True
                )

    except KeyboardInterrupt:
        print("\n\n[Spectator] Exiting spectator viewer...")
    finally:
        rlv.quit()
        time.sleep(0.3)
        cleanup_stale_viewers()
        print("[Spectator] RLViser closed cleanly.")


if __name__ == '__main__':
    main()
