"""Replay tracking pieces for RLGym-style training (pure numpy, framework-agnostic).

Glue to RLGym: call `ReplayClip.start_state(...)` inside your state setter, and call `TrackReward.reward`
and `DeviationTerminal.is_terminal` from your reward / terminal-condition classes, passing the
car's current sim position/velocity and the number of steps since reset.
"""
from dataclasses import dataclass
import numpy as np

SIM_HZ = 120


@dataclass
class ReplayTraj:
    t: np.ndarray          # [T] seconds, increasing
    ball_pos: np.ndarray   # [T,3]
    ball_vel: np.ndarray   # [T,3]
    car_pos: np.ndarray    # [T,N,3]
    car_vel: np.ndarray    # [T,N,3]

    def _interp(self, arr, tq):
        tq = np.clip(tq, self.t[0], self.t[-1])
        i = np.clip(np.searchsorted(self.t, tq) - 1, 0, len(self.t) - 2)
        f = (tq - self.t[i]) / np.maximum(self.t[i + 1] - self.t[i], 1e-9)
        return arr[i] * (1 - f) + arr[i + 1] * f

    def car(self, i, tq):   return self._interp(self.car_pos[:, i], tq), self._interp(self.car_vel[:, i], tq)
    def ball(self, tq):     return self._interp(self.ball_pos, tq), self._interp(self.ball_vel, tq)
    @property
    def duration(self): return float(self.t[-1] - self.t[0])


def find_touch_times(traj: ReplayTraj, car_idx, radius=200.0):
    """Times where car `car_idx` is within `radius` uu of the ball (approximate touches)."""
    d = np.linalg.norm(traj.car_pos[:, car_idx] - traj.ball_pos, axis=-1)
    close = d < radius
    starts = np.flatnonzero(close & ~np.r_[False, close[:-1]])     # first frame of each approach
    return traj.t[starts]


class ReplayClip:
    """One training episode: a window of the replay beginning at t0."""
    def __init__(self, traj, t0, length_s, tick_skip=8):
        self.traj, self.t0, self.length_s, self.dt = traj, t0, length_s, tick_skip / SIM_HZ

    @classmethod
    def sample(cls, traj, car_idx, rng, length_s=3.0, lead_s=1.5, tick_skip=8):
        """Start `lead_s` seconds before a random touch so the bot has to drive into the play."""
        touches = find_touch_times(traj, car_idx)
        if len(touches) == 0:
            t0 = rng.uniform(traj.t[0], max(traj.t[0], traj.t[-1] - length_s))
        else:
            t0 = max(traj.t[0], rng.choice(touches) - lead_s)
        t0 = min(t0, max(traj.t[0], traj.t[-1] - length_s))
        return cls(traj, float(t0), length_s, tick_skip)

    def time_at(self, step): return self.t0 + step * self.dt
    def done(self, step):    return step * self.dt >= self.length_s or self.time_at(step) >= self.traj.t[-1]

    def start_state(self):
        """Dict with everything your state setter needs: ball and every car at t0."""
        bp, bv = self.traj.ball(self.t0)
        cars = [self.traj.car(i, self.t0) for i in range(self.traj.car_pos.shape[1])]
        return {"ball_pos": bp, "ball_vel": bv, "cars": cars}


class TrackReward:
    def __init__(self, clip, pos_scale=500.0, vel_scale=1000.0, vel_w=0.3, ball_w=0.3, tol_s=0.0):
        self.clip, self.ps, self.vs, self.vw, self.bw, self.tol = clip, pos_scale, vel_scale, vel_w, ball_w, tol_s

    def reward(self, car_idx, pos, vel, step, ball_pos=None):
        """Reward for being where the replay car was AT THIS TIME. `tol_s > 0` takes the best match inside
        +/- tol_s seconds, with a small penalty for being off-time (forgiving a slightly early/late bot)."""
        t = self.clip.time_at(step)
        best = -1e9
        offsets = [0.0] if self.tol <= 0 else np.linspace(-self.tol, self.tol, 5)
        for off in offsets:
            rp, rv = self.clip.traj.car(car_idx, t + off)
            r = np.exp(-np.linalg.norm(pos - rp) / self.ps) + self.vw * np.exp(-np.linalg.norm(vel - rv) / self.vs)
            r -= 0.2 * abs(off) / max(self.tol, 1e-9) if self.tol > 0 else 0.0
            best = max(best, r)
        if ball_pos is not None:
            bp, _ = self.clip.traj.ball(t)
            best += self.bw * np.exp(-np.linalg.norm(ball_pos - bp) / 800.0)
        return float(best)


class DeviationTerminal:
    def __init__(self, clip, max_err=1500.0, penalty=-1.0):
        self.clip, self.max_err, self.penalty = clip, max_err, penalty

    def check(self, car_idx, pos, step):
        """returns (terminal, extra_reward). The episode ends when too far from the replay car OR the clip is over."""
        if self.clip.done(step):
            return True, 0.0
        rp, _ = self.clip.traj.car(car_idx, self.clip.time_at(step))
        if np.linalg.norm(pos - rp) > self.max_err:
            return True, self.penalty
        return False, 0.0

    def tighten(self, factor=0.9, floor=300.0): self.max_err = max(floor, self.max_err * factor)
