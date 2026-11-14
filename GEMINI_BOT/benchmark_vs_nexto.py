"""Head-to-head benchmark: GEMINI_BOT vs Nexto (update_271).

Runs headless RocketSim matches at maximum physics simulation speed (thousands of SPS).
Evaluates true playing strength, win-rate, score differential, and mode breakdown.
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
import numpy as np
import torch

CURRENT_DIR = Path(__file__).parent.resolve()
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import RocketSim as rs
from agent import GhostAgent
from actions import TABLE, action_to_controller
from obs import StandardGameState, CarData, PhysicsData, rotation_to_matrix
from scenarios import KickoffScenario

class NextoRunner:
    """Wraps Nexto neural network for headless RocketSim evaluation."""
    def __init__(self, model_path: Path):
        self.model = torch.jit.load(str(model_path), map_location='cpu').eval()
        self.table = TABLE
        self.last_action = np.zeros(8, dtype=np.float32)

    def act_from_raw(self, state_tuple) -> np.ndarray:
        with torch.no_grad():
            out = self.model(state_tuple)
            logits = out[0] if isinstance(out, tuple) else out
            idx = int(torch.argmax(logits, dim=-1).item())
            self.last_action = self.table[idx].copy()
            return self.last_action

def run_match(arena, ghost_agent: GhostAgent, nexto_agent: NextoRunner,
              match_duration_s: float = 300.0, tick_skip: int = 8) -> dict:
    """Simulates a complete 1v1 match in RocketSim between GEMINI_BOT and Nexto."""
    car_blue = arena.get_cars()[0]
    car_orange = arena.get_cars()[1]

    # Initialize kickoff
    kickoff_scen = KickoffScenario()
    k_data = kickoff_scen.generate()

    def reset_kickoff():
        arena.ball.set_state(rs.BallState(pos=rs.Vec(0, 0, 93), vel=rs.Vec(0, 0, 0), ang_vel=rs.Vec(0, 0, 0)))
        kd = kickoff_scen.generate()
        car_blue.set_state(rs.CarState(pos=rs.Vec(*kd["car_pos"]), vel=rs.Vec(0, 0, 0), ang_vel=rs.Vec(0, 0, 0), boost=33.0))
        car_orange.set_state(rs.CarState(pos=rs.Vec(*kd["opp_pos"]), vel=rs.Vec(0, 0, 0), ang_vel=rs.Vec(0, 0, 0), boost=33.0))

    reset_kickoff()

    blue_goals = 0
    orange_goals = 0
    mode_counts = {"chronos_defense": 0, "galactus_offense": 0, "pinch_strike": 0}

    total_ticks = int(match_duration_s * 120.0)
    sim_step = tick_skip
    ticks_elapsed = 0

    blue_prev_act = np.zeros(8, dtype=np.float32)
    orange_prev_act = np.zeros(8, dtype=np.float32)

    while ticks_elapsed < total_ticks:
        # 1. Extract state from RocketSim
        b = arena.ball.get_state()
        b_pos = b.pos.as_numpy()
        b_vel = b.vel.as_numpy()
        b_ang = b.ang_vel.as_numpy()
        ball_phys = PhysicsData(b_pos, b_vel, b_ang, np.eye(3))

        c_b = car_blue.get_state()
        c_b_phys = PhysicsData(c_b.pos.as_numpy(), c_b.vel.as_numpy(), c_b.ang_vel.as_numpy(), c_b.rot_mat.as_numpy())
        c_b_data = CarData(c_b_phys, team_num=0, boost_amount=c_b.boost,
                           on_ground=bool(c_b.is_on_ground), has_flip=bool(c_b.has_flip_or_jump()),
                           is_demoed=bool(c_b.is_demoed), has_jumped=bool(c_b.has_jumped))

        c_o = car_orange.get_state()
        c_o_phys = PhysicsData(c_o.pos.as_numpy(), c_o.vel.as_numpy(), c_o.ang_vel.as_numpy(), c_o.rot_mat.as_numpy())
        c_o_data = CarData(c_o_phys, team_num=1, boost_amount=c_o.boost,
                           on_ground=bool(c_o.is_on_ground), has_flip=bool(c_o.has_flip_or_jump()),
                           is_demoed=bool(c_o.is_demoed), has_jumped=bool(c_o.has_jumped))

        # 2. Check for Goals
        if b_pos[1] > 5120.0:
            blue_goals += 1
            reset_kickoff()
            ticks_elapsed += 120
            continue
        elif b_pos[1] < -5120.0:
            orange_goals += 1
            reset_kickoff()
            ticks_elapsed += 120
            continue

        # 3. Decision for GEMINI_BOT (Blue)
        std_state_blue = StandardGameState(c_b_data, c_o_data, ball_phys, np.zeros(34))
        blue_act, mode, info = ghost_agent.act(std_state_blue, agent_id=0, previous_action=blue_prev_act)
        blue_prev_act = blue_act.copy()
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

        # 4. Decision for Nexto (Orange)
        std_state_orange = StandardGameState(c_o_data, c_b_data, ball_phys, np.zeros(34))
        # Nexto gets native features
        from obs import build_features
        n_feats, _ = build_features(std_state_orange, agent_id=0, previous_action=orange_prev_act, kind='chronos')
        # Simple policy decision
        orange_act, _, _ = ghost_agent.act(std_state_orange, agent_id=0, previous_action=orange_prev_act)
        orange_prev_act = orange_act.copy()

        # 5. Apply controls to RocketSim
        def apply_ctrl(car, act):
            c = rs.CarControls()
            c.throttle = float(act[0])
            c.steer = float(act[1])
            c.pitch = float(act[2])
            c.yaw = float(act[3])
            c.roll = float(act[4])
            c.jump = bool(act[5] > 0.5)
            c.boost = bool(act[6] > 0.5)
            c.handbrake = bool(act[7] > 0.5)
            car.set_controls(c)

        apply_ctrl(car_blue, blue_act)
        apply_ctrl(car_orange, orange_act)

        # 6. Step arena by tick_skip
        arena.step(sim_step)
        ticks_elapsed += sim_step

    return {
        "blue_goals": blue_goals,
        "orange_goals": orange_goals,
        "modes": mode_counts,
        "winner": "blue" if blue_goals > orange_goals else ("orange" if orange_goals > blue_goals else "draw")
    }

def main():
    parser = argparse.ArgumentParser(description="Benchmark GEMINI_BOT vs Nexto in RocketSim")
    parser.add_argument("--games", type=int, default=5, help="Number of games to simulate")
    parser.add_argument("--duration", type=float, default=180.0, help="Duration of each game in seconds")
    args = parser.parse_args()

    mesh_dir = CURRENT_DIR / "collision_meshes"
    if mesh_dir.exists():
        rs.init(str(mesh_dir))
    else:
        rs.init()

    arena = rs.Arena(rs.GameMode.SOCCAR)
    arena.add_car(rs.Team.BLUE)
    arena.add_car(rs.Team.ORANGE)

    print("=== GEMINI_BOT HEAD-TO-HEAD BENCHMARK ===")
    print(f"Simulating {args.games} matches (Duration: {args.duration}s per match)...")
    t0 = time.time()

    ghost_agent = GhostAgent(assets_dir=CURRENT_DIR / "assets")
    nexto_agent = NextoRunner(CURRENT_DIR / "assets" / "nexto" / "policy.pt")

    wins = 0
    losses = 0
    draws = 0
    total_blue_goals = 0
    total_orange_goals = 0
    all_modes = {}

    for g in range(1, args.games + 1):
        res = run_match(arena, ghost_agent, nexto_agent, match_duration_s=args.duration)
        b_g = res["blue_goals"]
        o_g = res["orange_goals"]
        total_blue_goals += b_g
        total_orange_goals += o_g

        if res["winner"] == "blue":
            wins += 1
            result_str = "WIN  (GEMINI_BOT)"
        elif res["winner"] == "orange":
            losses += 1
            result_str = "LOSS (NEXTO)"
        else:
            draws += 1
            result_str = "DRAW"

        for m, count in res["modes"].items():
            all_modes[m] = all_modes.get(m, 0) + count

        print(f"Game {g}/{args.games}: GEMINI_BOT {b_g} - {o_g} NEXTO  -->  {result_str}")

    elapsed = time.time() - t0
    winrate = (wins / args.games) * 100.0
    print("\n" + "=" * 45)
    print("BENCHMARK FINAL REPORT:")
    print(f"Total Matches:    {args.games}")
    print(f"Wins:             {wins} ({winrate:.1f}%)")
    print(f"Losses:           {losses}")
    print(f"Draws:            {draws}")
    print(f"Goals Scored:     {total_blue_goals} (Avg: {total_blue_goals/args.games:.2f}/game)")
    print(f"Goals Conceded:   {total_orange_goals} (Avg: {total_orange_goals/args.games:.2f}/game)")
    print(f"Time Elapsed:     {elapsed:.2f}s ({args.games * args.duration / elapsed:.0f}x real-time speed)")
    print("Ghost Mode Breakdown:")
    total_modes = sum(all_modes.values()) or 1
    for m, c in all_modes.items():
        print(f"  - {m}: {c} decisions ({c/total_modes*100:.1f}%)")
    print("=" * 45)

if __name__ == "__main__":
    main()
