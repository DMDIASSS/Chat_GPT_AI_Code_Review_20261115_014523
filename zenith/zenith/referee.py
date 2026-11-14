"""
Zenith Referee: Head-to-Head Benchmark Evaluator & Rollback Guard
Evaluates student policy against Original Chronos and Galactus with statistical confidence bounds
and enforces automatic rollback protection against policy regression.
"""
from __future__ import annotations

import pathlib
import math
import numpy as np
import torch
import torch.nn.functional as F

from .policy import ZenithPolicy
from .teachers import TeacherEnsemble, GigaTeacherNet
from .zenith_sim import ZenithArenaPool


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float, float]:
    """
    Computes Wilson score interval for binomial proportion.
    Returns: (point_estimate, lower_bound, upper_bound)
    """
    if total <= 0:
        return 0.5, 0.0, 1.0
    p = successes / total
    z = 1.96 if confidence >= 0.95 else 1.645  # 95% or 90%
    denom = 1.0 + (z**2) / total
    centre = (p + (z**2) / (2 * total)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) + (z**2) / (4 * total)) / total)) / denom
    return p, max(0.0, centre - spread), min(1.0, centre + spread)


class Referee:
    """
    Independent Gauntlet Evaluator.
    Runs 1v1 duels against Chronos and Galactus in a dedicated arena pool.
    """
    def __init__(
        self,
        mesh_dir: str,
        chronos_path: pathlib.Path | str,
        galactus_path: pathlib.Path | str,
        best_checkpoint_dir: pathlib.Path | str,
        num_eval_arenas: int = 16,
        device: torch.device | str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        self.device = torch.device(device)
        self.mesh_dir = mesh_dir
        self.num_arenas = num_eval_arenas
        self.best_checkpoint_dir = pathlib.Path(best_checkpoint_dir)
        self.best_checkpoint_dir.mkdir(parents=True, exist_ok=True)

        print(f"[Referee] Spawning dedicated evaluation pool with {num_eval_arenas} arenas...")
        self.pool = ZenithArenaPool(
            num_arenas=num_eval_arenas,
            tick_skip=8,
            action_delay=7,
            mesh_dir=mesh_dir,
            base_seed=1337001,
            car0_hitbox="breakout",
            car1_hitbox="octane"
        )
        self.mirror_map = self.pool.get_action_mirror_map()

        print("[Referee] Loading Chronos and Galactus opponents...")
        self.chronos = GigaTeacherNet(pathlib.Path(chronos_path), "chronos").to(self.device).eval()
        self.galactus = GigaTeacherNet(pathlib.Path(galactus_path), "galactus").to(self.device).eval()

        # Best checkpoint tracker
        self.best_win_rate = 0.0
        self.best_checkpoint_path: pathlib.Path | None = None
        self.eval_history: list[dict] = []

    def evaluate_gauntlet(
        self,
        student_policy: ZenithPolicy,
        opponent_name: str = "chronos",
        max_games: int = 32
    ) -> dict:
        """
        Runs evaluation games of student (Blue) vs opponent (Orange).
        Returns comprehensive evaluation telemetry with Wilson confidence bounds.
        """
        student_policy.eval()
        opp_net = self.chronos if opponent_name == "chronos" else self.galactus

        total_players = self.num_arenas * 2
        neutral_weights = np.zeros(12, dtype=np.float32)

        self.pool.reset_all(scenario_id=0)  # Standard Kickoffs
        st = self.pool.get_current_state()
        cur_obs = torch.from_numpy(st["obs"]).to(self.device)
        cur_masks = torch.from_numpy(st["masks"]).to(self.device)

        games_completed = 0
        student_wins = 0
        opponent_wins = 0
        student_goals = 0
        opponent_goals = 0
        total_saves = 0
        total_resets = 0
        total_mustys = 0

        max_steps = 1800 * (max_games // self.num_arenas + 1)
        step = 0

        while games_completed < max_games and step < max_steps:
            step += 1

            # 1. Student actions for Blue cars (indices 0, 2, 4, ...)
            blue_indices = list(range(0, total_players, 2))
            blue_obs = cur_obs[blue_indices]
            blue_masks = cur_masks[blue_indices]

            with torch.inference_mode():
                # Argmax deterministic action during official gauntlet
                blue_logits, _ = student_policy(blue_obs, blue_masks)
                blue_actions = torch.argmax(blue_logits, dim=-1)

            # 2. Opponent actions for Orange cars (indices 1, 3, 5, ...)
            opp_teacher_type = "chronos" if opponent_name == "chronos" else "galactus"
            opp_obs_np = self.pool.get_teacher_obs_batch(1, opp_teacher_type)
            opp_obs = torch.from_numpy(opp_obs_np).to(self.device)
            orange_masks = cur_masks[list(range(1, total_players, 2))]

            with torch.inference_mode():
                opp_logits = opp_net(opp_obs)
                opp_logits = opp_logits.masked_fill(orange_masks == 0, -1e9)
                raw_opp_actions = torch.argmax(opp_logits, dim=-1).cpu().numpy()

            if opponent_name == "chronos":
                mirror_flags = self.pool.get_teacher_mirror_flags(1)
                orange_actions = np.zeros_like(raw_opp_actions)
                for a_idx in range(self.num_arenas):
                    if mirror_flags[a_idx]:
                        orange_actions[a_idx] = self.mirror_map[raw_opp_actions[a_idx]]
                    else:
                        orange_actions[a_idx] = raw_opp_actions[a_idx]
            else:
                orange_actions = raw_opp_actions

            # Combine actions
            all_actions = np.zeros(total_players, dtype=np.int32)
            all_actions[0::2] = blue_actions.cpu().numpy()
            all_actions[1::2] = orange_actions

            # Step simulation
            step_res = self.pool.step(all_actions, neutral_weights)
            cur_obs = torch.from_numpy(step_res["obs"]).to(self.device)
            cur_masks = torch.from_numpy(step_res["masks"]).to(self.device)

            # Collect completed games
            gb = step_res["goals_blue"]
            go = step_res["goals_orange"]
            student_goals += gb
            opponent_goals += go

            if gb > 0 or go > 0:
                games_completed += (gb + go)
                student_wins += gb
                opponent_wins += go

            # Count mechanics from reward components
            r_comps = step_res["reward_components"]
            blue_comps = r_comps[0::2]
            total_resets += int(np.sum(blue_comps[:, 6] > 0))
            total_mustys += int(np.sum(blue_comps[:, 7] > 0))
            total_saves += int(np.sum(blue_comps[:, 8] > 0))

        win_rate, lower_ci, upper_ci = wilson_score_interval(student_wins, max(1, games_completed))

        telemetry = {
            "opponent": opponent_name,
            "games": games_completed,
            "student_wins": student_wins,
            "opponent_wins": opponent_wins,
            "win_rate": win_rate,
            "win_rate_ci_lower": lower_ci,
            "win_rate_ci_upper": upper_ci,
            "goals_for": student_goals,
            "goals_against": opponent_goals,
            "goal_diff": student_goals - opponent_goals,
            "resets_triggered": total_resets,
            "mustys_triggered": total_mustys,
            "saves_triggered": total_saves
        }
        return telemetry

    def check_checkpoint(
        self,
        student_policy: ZenithPolicy,
        current_step: int,
        telemetry: dict
    ) -> tuple[bool, str]:
        """
        Checks whether the candidate policy achieves a new benchmark high
        or triggers a rollback condition.
        Returns: (is_new_best, status_message)
        """
        win_rate = telemetry["win_rate"]
        opp = telemetry["opponent"]

        # Track history
        self.eval_history.append({"step": current_step, **telemetry})

        # Save new best checkpoint
        if win_rate > self.best_win_rate:
            old_best = self.best_win_rate
            self.best_win_rate = win_rate
            ckpt_path = self.best_checkpoint_dir / f"zenith_best_step_{current_step:08d}.pt"
            torch.save(student_policy.state_dict(), ckpt_path)
            self.best_checkpoint_path = ckpt_path
            msg = f"NEW CHAMPION: Win rate vs {opp} improved {old_best:.1%} -> {win_rate:.1%} [{telemetry['win_rate_ci_lower']:.1%}, {telemetry['win_rate_ci_upper']:.1%}]!"
            return True, msg

        # Rollback check: If win rate drops by more than 8% compared to best and games >= 32
        if self.best_win_rate >= 0.50 and (self.best_win_rate - win_rate) > 0.08:
            msg = f"REGRESSION DETECTED: Win rate dropped to {win_rate:.1%} (Best: {self.best_win_rate:.1%}). ROLLBACK RECOMMENDED."
            return False, msg

        msg = f"Gauntlet finished: {win_rate:.1%} vs {opp} (Best: {self.best_win_rate:.1%})"
        return False, msg

    def restore_best_checkpoint(self, student_policy: ZenithPolicy):
        """
        Restores policy weights to the highest performing verified checkpoint.
        """
        if self.best_checkpoint_path and self.best_checkpoint_path.exists():
            print(f"[Referee] Restoring policy to verified best checkpoint: {self.best_checkpoint_path.name}")
            state_dict = torch.load(self.best_checkpoint_path, map_location=self.device)
            student_policy.load_state_dict(state_dict)
            return True
        return False
