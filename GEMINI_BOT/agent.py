"""GhostAgent: Dual-Master Hierarchical Controller (Chronos + Galactus + Judge).

Integrates the two grandmasters with zero dilution:
- Chronos: Pure defensive anchor, shadow defense, speedflips, 50-50s
- Galactus: Pure offensive monster, aerial reads, wall hits, double taps
- Judge: Real-time tactical arbiter that assigns 100% authority with hysteresis
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
from actions import TABLE, native_action_mask, action_to_controller
from obs import build_features, BallForecastEngine, StandardGameState
from judge import TacticalJudge, MODE_DEFENSE, MODE_OFFENSE, MODE_PINCH

def _load_sequence(path: Path | str, widths: list[int], in_sz: int, act_cls, out_sz: int = None):
    layers = []
    sz = in_sz
    for w in widths:
        layers.extend([nn.Linear(sz, w), nn.LayerNorm(w), act_cls()])
        sz = w
    if out_sz is not None:
        layers.append(nn.Linear(sz, out_sz))
    seq = nn.Sequential(*layers)
    if path is not None and Path(path).exists():
        arch = torch.jit.load(str(path), map_location='cpu')
        seq.load_state_dict(dict(arch.named_parameters()), strict=True)
    seq.eval()
    for p in seq.parameters():
        p.requires_grad = False
    return seq

class GhostAgent:
    def __init__(self, assets_dir: Path | str = None, device: str = None):
        if assets_dir is None:
            assets_dir = Path(__file__).parent / "assets"
        else:
            assets_dir = Path(assets_dir)

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        # 1. Load Chronos
        c_dir = assets_dir / "chronos"
        self.chronos_head = _load_sequence(c_dir / "SHARED_HEAD.lt", [960, 960], 225, nn.ReLU).to(self.device)
        self.chronos_policy = _load_sequence(c_dir / "POLICY.lt", [960, 800, 640, 640], 960, nn.ReLU, 90).to(self.device)

        # 2. Load Galactus
        g_dir = assets_dir / "galactus"
        self.galactus_head = _load_sequence(g_dir / "SHARED_HEAD.lt", [1024, 1024], 258, nn.LeakyReLU).to(self.device)
        self.galactus_policy = _load_sequence(g_dir / "POLICY.lt", [1024, 1024, 1024, 1024], 1024, nn.LeakyReLU, 90).to(self.device)

        # 3. Engines
        self.forecast_engine = BallForecastEngine()
        self.judge = TacticalJudge(commitment_steps=4)
        self.lookup_table = TABLE

        self.last_action_row = np.zeros(8, dtype=np.float32)
        self.last_mode = MODE_DEFENSE

    def act(self, state: StandardGameState, agent_id: int = 0,
            previous_action: np.ndarray = None, rlbot_ball_prediction=None) -> tuple[np.ndarray, str, dict]:
        """Runs one decision step and returns (action_8d, mode_name, info_dict)."""
        if previous_action is None:
            previous_action = self.last_action_row

        own = state.cars[agent_id]
        opp_id = 1 if agent_id == 0 else 0
        opp = state.cars[opp_id]
        is_orange = (own.team_num == 1)

        # 1. Evaluate tactical situation via Judge
        mode = self.judge.evaluate_state(
            own_pos=own.physics.position,
            own_vel=own.physics.linear_velocity,
            opp_pos=opp.physics.position,
            opp_vel=opp.physics.linear_velocity,
            ball_pos=state.ball.position,
            ball_vel=state.ball.linear_velocity,
            own_boost=own.boost_amount,
            is_orange=is_orange
        )
        self.last_mode = mode

        # 2. Compute ball prediction for Galactus
        ball_forecast = self.forecast_engine.predict(state.ball, rlbot_ball_prediction)

        # 3. Build features & run the selected expert
        with torch.no_grad():
            if mode in (MODE_OFFENSE, MODE_PINCH):
                # Galactus expert execution
                feats, mirror = build_features(state, agent_id, previous_action, kind='galactus', ball_forecast=ball_forecast)
                inp = torch.from_numpy(feats).unsqueeze(0).to(self.device)
                logits = self.galactus_policy(self.galactus_head(inp)).squeeze(0).cpu().numpy()
            else:
                # Chronos expert execution
                feats, mirror = build_features(state, agent_id, previous_action, kind='chronos')
                inp = torch.from_numpy(feats).unsqueeze(0).to(self.device)
                feat = self.chronos_head(inp)
                logits = self.chronos_policy(feat).squeeze(0).cpu().numpy()

            # 4. Action Masking
            mask = native_action_mask(own.on_ground, own.has_flip, own.boost_amount)
            logits[~mask] = -1e9

            action_idx = int(np.argmax(logits))
            action_row = self.lookup_table[action_idx].copy()

            # If Chronos mirrored the field, mirror the steering and air roll
            if mirror:
                action_row[1] *= -1.0 # steer
                action_row[3] *= -1.0 # yaw
                action_row[4] *= -1.0 # roll

        self.last_action_row = action_row.copy()
        info = {
            "mode": mode,
            "action_idx": action_idx,
            "threat": self.judge.last_threat,
            "opportunity": self.judge.last_opportunity,
            "is_mirrored": mirror
        }
        return action_row, mode, info
