import numpy as np
import RocketSim as rs
import rlgym.rocket_league.common_values as cv
from rlgym.rocket_league.obs_builders import DefaultObs
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator

# Setup RocketSimEngine
engine = RocketSimEngine()
obs_builder = DefaultObs(
    zero_padding=None,
    pos_coef=np.asarray([1 / cv.SIDE_WALL_X, 1 / cv.BACK_NET_Y, 1 / cv.CEILING_Z]),
    ang_coef=1 / np.pi,
    lin_vel_coef=1 / cv.CAR_MAX_SPEED,
    ang_vel_coef=1 / cv.CAR_MAX_ANG_VEL,
    boost_coef=1 / 100.0,
)

base = engine.create_base_state()
FixedTeamSizeMutator(1, 1).apply(base, {})
KickoffMutator().apply(base, {})
state = engine.set_state(base, {})

ref_obs = obs_builder.build_obs(['blue-0', 'orange-0'], state, {})['blue-0']
print("Reference obs shape:", ref_obs.shape)
print("Reference obs (first 20):", np.round(ref_obs[:20], 4))
