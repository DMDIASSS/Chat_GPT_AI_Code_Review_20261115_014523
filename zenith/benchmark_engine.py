import time
import numpy as np
import rlgym.rocket_league.common_values as cv
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator
from rlgym.rocket_league.obs_builders import DefaultObs
from rlgym.rocket_league.action_parsers import LookupTableAction

engine = RocketSimEngine()
obs_builder = DefaultObs(
    zero_padding=None,
    pos_coef=np.asarray([1 / cv.SIDE_WALL_X, 1 / cv.BACK_NET_Y, 1 / cv.CEILING_Z]),
    ang_coef=1 / np.pi,
    lin_vel_coef=1 / cv.CAR_MAX_SPEED,
    ang_vel_coef=1 / cv.CAR_MAX_ANG_VEL,
    boost_coef=1 / 100.0,
)
action_parser = LookupTableAction()

base = engine.create_base_state()
FixedTeamSizeMutator(1, 1).apply(base, {})
KickoffMutator().apply(base, {})
state = engine.set_state(base, {})

# Benchmark 500 steps (tick_skip=8, so 4,000 physics ticks)
t0 = time.perf_counter()
parsed = action_parser.parse_actions({'blue-0': np.array([12]), 'orange-0': np.array([0])}, state, {})
actions_raw = {
    'blue-0': parsed['blue-0'],
    'orange-0': parsed['orange-0']
}

for i in range(500):
    state = engine.step(actions_raw, {})
    obs = obs_builder.build_obs(['blue-0'], state, {})['blue-0']

dt = time.perf_counter() - t0
print(f"500 steps completed in {dt:.3f}s: {500 / dt:.0f} steps/s ({500 * 8 / dt:.0f} physics ticks/s)")
print("Obs shape:", obs.shape)
