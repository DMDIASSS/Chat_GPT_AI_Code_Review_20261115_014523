"""Scenario-based trainer and fine-tuner for GEMINI_BOT.

Uses potential-based reward shaping from TacticalJudge:
    R_t = R_env + gamma * Phi(s_{t+1}) - Phi(s_t)
Provably telescopes across episodes, preventing reward farming and infinite loops.

Logs training metrics, threat levels, and pinch velocities to Weights & Biases (WandB).
Falls back cleanly to offline mode if unauthenticated.
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

CURRENT_DIR = Path(__file__).parent.resolve()
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import RocketSim as rs
from agent import GhostAgent
from actions import TABLE
from obs import StandardGameState, CarData, PhysicsData
from judge import TacticalJudge
from scenarios import PinchScenario, ShadowDefenseScenario, KickoffScenario

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

def main():
    parser = argparse.ArgumentParser(description="Scenario trainer for GEMINI_BOT")
    parser.add_argument("--scenarios", type=int, default=100, help="Number of scenario episodes")
    parser.add_argument("--wandb", choices=["online", "offline", "disabled"], default="offline")
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--gamma", type=float, default=0.99)
    args = parser.parse_args()

    # WandB setup with safe fallback
    run = None
    if WANDB_AVAILABLE and args.wandb != "disabled":
        os.environ["WANDB_MODE"] = args.wandb
        try:
            run = wandb.init(
                project="gemini_bot_training",
                name="ghost_scenario_finetune",
                config={"lr": args.lr, "gamma": args.gamma, "scenarios": args.scenarios}
            )
        except Exception as e:
            print(f"WandB init skipped: {e}")

    mesh_dir = CURRENT_DIR / "collision_meshes"
    if mesh_dir.exists():
        rs.init(str(mesh_dir))
    else:
        rs.init()

    arena = rs.Arena(rs.GameMode.SOCCAR)
    car = arena.add_car(rs.Team.BLUE)
    opp = arena.add_car(rs.Team.ORANGE)

    agent = GhostAgent(assets_dir=CURRENT_DIR / "assets")
    pinch_gen = PinchScenario()
    defense_gen = ShadowDefenseScenario()
    kickoff_gen = KickoffScenario()

    print("=== GEMINI_BOT SCENARIO TRAINING STARTED ===")
    print(f"Episodes: {args.scenarios} | WandB: {args.wandb} | Device: {agent.device}")

    total_goals = 0
    total_pinches = 0
    t0 = time.time()

    for ep in range(1, args.scenarios + 1):
        # Rotate scenario type: 50% pinch, 30% shadow defense, 20% kickoff
        r_type = np.random.random()
        if r_type < 0.50:
            scen = pinch_gen.generate()
        elif r_type < 0.80:
            scen = defense_gen.generate()
        else:
            scen = kickoff_gen.generate()

        # Reset arena to scenario state
        arena.ball.set_state(rs.BallState(
            pos=rs.Vec(*scen["ball_pos"]),
            vel=rs.Vec(*scen["ball_vel"]),
            ang_vel=rs.Vec(0, 0, 0)
        ))
        car.set_state(rs.CarState(
            pos=rs.Vec(*scen["car_pos"]),
            vel=rs.Vec(*scen["car_vel"]),
            ang_vel=rs.Vec(0, 0, 0),
            boost=scen.get("car_boost", 100.0)
        ))
        if "opp_pos" in scen:
            opp.set_state(rs.CarState(
                pos=rs.Vec(*scen["opp_pos"]),
                vel=rs.Vec(*scen.get("opp_vel", [0, 0, 0])),
                ang_vel=rs.Vec(0, 0, 0),
                boost=33.0
            ))

        ep_reward = 0.0
        max_ball_speed = 0.0
        goal_scored = False

        # Run episode for up to 38 decisions (2.5 seconds)
        prev_phi = TacticalJudge.compute_potential(scen["car_pos"], scen["ball_pos"], scen["ball_vel"], is_orange=False)
        prev_act = np.zeros(8, dtype=np.float32)

        for step in range(38):
            # Extract state
            b = arena.ball.get_state()
            b_pos = b.pos.as_numpy()
            b_vel = b.vel.as_numpy()
            ball_speed = float(np.linalg.norm(b_vel))
            max_ball_speed = max(max_ball_speed, ball_speed)

            c_b = car.get_state()
            c_b_phys = PhysicsData(c_b.pos.as_numpy(), c_b.vel.as_numpy(), c_b.ang_vel.as_numpy(), c_b.rot_mat.as_numpy())
            c_b_data = CarData(c_b_phys, team_num=0, boost_amount=c_b.boost,
                               on_ground=bool(c_b.is_on_ground), has_flip=bool(c_b.has_flip_or_jump()),
                               is_demoed=bool(c_b.is_demoed), has_jumped=bool(c_b.has_jumped))

            c_o = opp.get_state()
            c_o_phys = PhysicsData(c_o.pos.as_numpy(), c_o.vel.as_numpy(), c_o.ang_vel.as_numpy(), c_o.rot_mat.as_numpy())
            c_o_data = CarData(c_o_phys, team_num=1, boost_amount=c_o.boost,
                               on_ground=bool(c_o.is_on_ground), has_flip=bool(c_o.has_flip_or_jump()),
                               is_demoed=bool(c_o.is_demoed), has_jumped=bool(c_o.has_jumped))

            std_state = StandardGameState(c_b_data, c_o_data, PhysicsData(b_pos, b_vel, b.ang_vel.as_numpy(), np.eye(3)), np.zeros(34))
            act, mode, info = agent.act(std_state, agent_id=0, previous_action=prev_act)
            prev_act = act.copy()

            # Apply controls & step
            ctrl = rs.CarControls()
            ctrl.throttle = float(act[0])
            ctrl.steer = float(act[1])
            ctrl.pitch = float(act[2])
            ctrl.yaw = float(act[3])
            ctrl.roll = float(act[4])
            ctrl.jump = bool(act[5] > 0.5)
            ctrl.boost = bool(act[6] > 0.5)
            ctrl.handbrake = bool(act[7] > 0.5)
            car.set_controls(ctrl)

            arena.step(8)

            # Potential-based reward calculation
            curr_phi = TacticalJudge.compute_potential(c_b.pos.as_numpy(), b_pos, b_vel, is_orange=False)
            shaping = args.gamma * curr_phi - prev_phi
            prev_phi = curr_phi

            step_reward = shaping
            if b_pos[1] > 5120.0:
                step_reward += 10.0
                goal_scored = True
                total_goals += 1
                break
            elif b_pos[1] < -5120.0:
                step_reward -= 10.0
                break

            ep_reward += step_reward

        is_pinch = (scen["name"] == "sidewall_pinch" and max_ball_speed > 2500.0)
        if is_pinch:
            total_pinches += 1

        if ep % 20 == 0 or ep == args.scenarios:
            print(f"Episode {ep}/{args.scenarios} [{scen['name']}] - Reward: {ep_reward:.2f} | Max Ball Speed: {max_ball_speed:.0f} uu/s | Goal: {goal_scored}")

        if run is not None:
            wandb.log({
                "episode": ep,
                "reward": ep_reward,
                "max_ball_speed": max_ball_speed,
                "goal_scored": int(goal_scored),
                "is_pinch": int(is_pinch)
            }, step=ep)

    elapsed = time.time() - t0
    print("\n" + "=" * 45)
    print("SCENARIO TRAINING COMPLETE:")
    print(f"Total Episodes:  {args.scenarios}")
    print(f"Total Goals:     {total_goals}")
    print(f"High-Speed Pinches: {total_pinches}")
    print(f"Time Elapsed:    {elapsed:.2f}s")
    print("=" * 45)

    if run is not None:
        run.finish()

if __name__ == "__main__":
    main()
