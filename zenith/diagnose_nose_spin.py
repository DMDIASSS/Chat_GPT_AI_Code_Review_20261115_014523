import numpy as np
import torch
import RocketSim as rs
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kuxir_policy import KuxirActorCritic
from kuxir_env import KuxirMutator, make_kuxir_components

engine = RocketSimEngine()
team_mutator = FixedTeamSizeMutator(1, 1)
kuxir_mutator = KuxirMutator(full_seq_ratio=0.50, climb_ratio=0.30)
obs_builder, action_parser = make_kuxir_components()

policy = KuxirActorCritic()
ckpt = torch.load(r'E:\Downloads\Chat_GPT_AI\zenith\runs\kuxir_pinch\checkpoints\latest_checkpoint.pt', map_location='cpu')
policy.actor.load_state_dict(ckpt['actor_state'])
policy.eval()

base = engine.create_base_state()
team_mutator.apply(base, {})
kuxir_mutator.apply(base, {})
state = engine.set_state(base, {})

action_lookup = action_parser._lookup_table

print(f"--- Simulating 40 decision steps (320 physics ticks) ---")
for step in range(40):
    obs = obs_builder.build_obs(['blue-0'], state, {})['blue-0']
    obs_t = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        act_t, _, _, _ = policy.get_action(obs_t, deterministic=True)
    act_id = int(act_t.item())
    ctrls = action_lookup[act_id]
    
    parsed = action_parser.parse_actions({'blue-0': np.array([act_id])}, state, {})
    state = engine.step({'blue-0': parsed['blue-0'], 'orange-0': np.zeros((8, 8), dtype=np.float32)}, {})
    
    car = state.cars['blue-0']
    cp = car.physics.position
    cv = car.physics.linear_velocity
    ang = car.physics.angular_velocity
    rot = car.physics.rotation_mtx
    # Forward vector is rot[:, 0], Up vector is rot[:, 2]
    fwd = rot[:, 0]
    up = rot[:, 2]
    
    print(f"Step {step:02d} | Act {act_id:02d} {ctrls} | Pos: ({cp[0]:.0f}, {cp[1]:.0f}, {cp[2]:.0f}) | "
          f"Fwd Z: {fwd[2]:+.2f} | Up Z: {up[2]:+.2f} | AngVel: ({ang[0]:.1f}, {ang[1]:.1f}, {ang[2]:.1f}) | Ground: {car.on_ground}")
