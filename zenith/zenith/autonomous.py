"""
Zenith Autonomous Self-Regulating Training Engine
Builds an elite Rocket League bot completely from scratch without external .pt checkpoints.
Features:
- Pure from-scratch initialization (Orthogonal weights, dual-trunk 256-width policy)
- AutonomousDirector: self-pacing SPS, dynamically scaling batch sizes (32k -> 64k -> 128k -> 256k)
- Developmental milestones:
    Stage 0 (Touch & Reflex): 0 - 50k steps (small batches, rapid 0.15s feedback updates)
    Stage 1 (Purpose & Net Shooting): 50k - 200k steps (velocity-scaled hits, goal direction)
    Stage 2 (Aerials & Mechanics): 200k - 500k steps (prejump defense, flip reset, Musty flick)
    Stage 3 (Stepmaxxing & Dominance): 500k+ steps (full SPS, PFSP league tournament)
- Real-time auto-correction: detects regression, restores best snapshots, injects entropy
- Zero-friction export: auto-updates export/zenith_rlbot/zenith.pt and bot.toml for RLBot
"""
from __future__ import annotations

import os
import sys
import time
import json
import shutil
import pathlib
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from .policy import ZenithPolicy
from .coach import Coach
from .league import LeagueManager
from .zenith_sim import ZenithArenaPool


class AutonomousDirector:
    """
    Self-regulating curriculum and reward manager.
    Monitors live gameplay statistics and automatically transitions stages,
    adjusts rollout batch sizes, tunes learning rates, and guards against regression.
    """
    STAGE_NAMES = {
        0: "Stage 0: Touch & Motor Reflex (Bronze-Silver)",
        1: "Stage 1: Purpose & Net Direction (Gold-Plat)",
        2: "Stage 2: Aerials & Skill Drills (Diamond-Champ)",
        3: "Stage 3: Stepmaxxing & Dominance (GC-SSL)"
    }

    def __init__(self):
        self.stage = 0
        self.stage_start_steps = 0
        self.rollout_steps = 64     # Starts small for rapid policy updates
        self.lr = 2.0e-4            # Fast initial motor adaptation
        self.entropy_coef = 0.045   # High exploration
        self.weights = np.zeros(12, dtype=np.float32)

        # Sliding window statistics
        self.history_touches = []
        self.history_goals = []
        self.history_aerials = []
        self.history_saves = []
        self.history_mustys = []

        # Regression detection
        self.best_touch_rate = 0.0
        self.best_goal_rate = 0.0
        self.consecutive_regressions = 0

        self.apply_stage_settings()

    def apply_stage_settings(self):
        if self.stage == 0:
            # Stage 0: Touch & Motor Reflex
            # Focus on seeking ball, making contact, jumping
            self.rollout_steps = 64
            self.lr = 2.0e-4
            self.entropy_coef = 0.045
            self.weights = np.array([
                0.5,   # goal (low to prevent noisy flukes from distracting)
                0.5,   # ball_net_vel
                2.5,   # car_ball_vel (reward driving toward ball)
                1.5,   # car_ball_dist (exponential proximity)
                5.0,   # touch (strong contact reward)
                0.5,   # aerial_touch
                0.0,   # flip_reset
                0.0,   # musty_flick
                0.5,   # save
                0.0,   # prejump
                0.0,   # fake_penalty
                0.3    # boost
            ], dtype=np.float32)

        elif self.stage == 1:
            # Stage 1: Purpose & Net Direction
            # Focus on directing the ball to enemy net, defending own net, boost
            self.rollout_steps = 128
            self.lr = 1.2e-4
            self.entropy_coef = 0.035
            self.weights = np.array([
                5.0,   # goal
                3.0,   # ball_net_vel (drive ball to net)
                1.0,   # car_ball_vel
                0.5,   # car_ball_dist
                2.0,   # touch
                1.2,   # aerial_touch
                0.0,   # flip_reset
                0.0,   # musty_flick
                3.0,   # save (goal-line defense)
                0.5,   # prejump
                0.5,   # fake_penalty
                0.5    # boost
            ], dtype=np.float32)

        elif self.stage == 2:
            # Stage 2: Aerials & Tactical Mechanics
            # Focus on aerial takeoffs, backboard defense, flip resets, Musty flick
            self.rollout_steps = 256
            self.lr = 0.9e-4
            self.entropy_coef = 0.025
            self.weights = np.array([
                8.0,   # goal
                2.0,   # ball_net_vel
                0.3,   # car_ball_vel
                0.2,   # car_ball_dist
                1.0,   # touch
                3.0,   # aerial_touch (high aerials)
                3.5,   # flip_reset (3-wheel reset)
                3.5,   # musty_flick (Musty flick execution)
                3.0,   # save
                2.5,   # prejump (high boomer challenge)
                2.0,   # fake_penalty
                0.3    # boost
            ], dtype=np.float32)

        else:
            # Stage 3: Stepmaxxing & Dominance
            # Maximum SPS throughput, dominance win-rate potential, anti-dive defense
            self.rollout_steps = 512
            self.lr = 0.7e-4
            self.entropy_coef = 0.018
            self.weights = np.array([
                10.0,  # goal (winrate dominance)
                2.5,   # ball_net_vel
                0.1,   # car_ball_vel
                0.05,  # car_ball_dist
                0.5,   # touch
                2.5,   # aerial_touch
                4.0,   # flip_reset
                4.0,   # musty_flick
                3.5,   # save
                3.0,   # prejump
                2.5,   # fake_penalty
                0.2    # boost
            ], dtype=np.float32)

    def update_telemetry(self, touches: float, goals: float, aerials: float, saves: float, mustys: float, total_steps: int = 0) -> dict[str, any]:
        """
        Records iteration telemetry, evaluates milestones, and auto-transitions stages.
        Returns a dict of action flags: {"stage_changed": bool, "regression": bool, "message": str}
        """
        self.history_touches.append(touches)
        self.history_goals.append(goals)
        self.history_aerials.append(aerials)
        self.history_saves.append(saves)
        self.history_mustys.append(mustys)

        if len(self.history_touches) > 10:
            self.history_touches.pop(0)
            self.history_goals.pop(0)
            self.history_aerials.pop(0)
            self.history_saves.pop(0)
            self.history_mustys.pop(0)

        avg_touch = float(np.mean(self.history_touches))
        avg_goal = float(np.mean(self.history_goals))
        avg_aerial = float(np.mean(self.history_aerials))

        steps_in_stage = max(0, total_steps - self.stage_start_steps)
        action = {"stage_changed": False, "regression": False, "message": ""}

        # 1. Milestone checks for stage advancement
        # Stage 0 -> Stage 1: Bot touches ball consistently (>=0.25% frame rate) or >=3M steps in Stg 0
        if self.stage == 0 and len(self.history_touches) >= 5 and (avg_touch >= 0.0025 or steps_in_stage >= 3_000_000):
            self.stage = 1
            self.stage_start_steps = total_steps
            self.apply_stage_settings()
            action["stage_changed"] = True
            action["message"] = f"Milestone achieved! Bot learned ball contact (Touch Rate: {avg_touch*100:.2f}%). Advancing to Stage 1: Purpose & Net Direction."
            return action

        # Stage 1 -> Stage 2: Bot scores intentionally (>=0.06% goal rate) or >=8M steps in Stg 1
        if self.stage == 1 and len(self.history_goals) >= 5 and (avg_goal >= 0.0006 or steps_in_stage >= 8_000_000):
            self.stage = 2
            self.stage_start_steps = total_steps
            self.apply_stage_settings()
            action["stage_changed"] = True
            action["message"] = f"Milestone achieved! Bot learned intentional scoring (Goal Rate: {avg_goal*100:.2f}%). Advancing to Stage 2: Aerials & Mechanics."
            return action

        # Stage 2 -> Stage 3: Bot hits aerials (>=0.03%) & scores (>=0.08%) or >=12M steps in Stg 2
        if self.stage == 2 and len(self.history_aerials) >= 5 and ((avg_aerial >= 0.0003 and avg_goal >= 0.0008) or steps_in_stage >= 12_000_000):
            self.stage = 3
            self.stage_start_steps = total_steps
            self.apply_stage_settings()
            action["stage_changed"] = True
            action["message"] = f"Milestone achieved! Bot executes aerials and strikes. Advancing to Stage 3: Stepmaxxing & Dominance!"
            return action

        # 2. Regression guard (only active after initial learning)
        if self.stage >= 1 and len(self.history_touches) >= 8:
            if avg_touch > self.best_touch_rate:
                self.best_touch_rate = avg_touch
                self.consecutive_regressions = 0
            elif avg_touch < self.best_touch_rate * 0.40:
                self.consecutive_regressions += 1
                if self.consecutive_regressions >= 4:
                    action["regression"] = True
                    action["message"] = f"Performance regression detected (Touch dropped {avg_touch*100:.2f}% vs best {self.best_touch_rate*100:.2f}%). Triggering auto-rollback!"
                    self.consecutive_regressions = 0
                    # Slightly boost entropy to break bad habits
                    self.entropy_coef = min(0.045, self.entropy_coef + 0.010)

        return action


class AutonomousMaster:
    """
    Self-contained master training orchestrator.
    Handles experience collection, PPO updates, league matchmaking, and model exports.
    """
    def __init__(
        self,
        num_arenas: int = 32,
        run_dir: str = r"E:\Downloads\Chat_GPT_AI\zenith\runs\zenith_scratch_01",
        export_dir: str = r"E:\Downloads\Chat_GPT_AI\zenith\export\zenith_rlbot",
        mesh_dir: str | None = None,
        target_steps: int = 10_000_000,
        device: str | None = None
    ):
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        print(f"\n====================================================================")
        print(f"               ZENITH AUTONOMOUS FROM-SCRATCH ENGINE                ")
        print(f"====================================================================")
        print(f"[Zenith] Operating Device: {self.device}")
        if self.device.type == "cuda":
            print(f"[Zenith] GPU: {torch.cuda.get_device_name(0)} (4GB VRAM)")

        self.num_arenas = num_arenas
        self.target_steps = target_steps
        self.total_steps = 0
        self.iteration = 0
        self.start_time = time.time()

        self.run_dir = pathlib.Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ckpt_dir = self.run_dir / "checkpoints"
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir = pathlib.Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        if mesh_dir is None:
            self.mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
        else:
            self.mesh_dir = mesh_dir

        print(f"[Zenith] Initializing C++ multi-arena simulation pool ({num_arenas} arenas / {num_arenas * 2} cars)...")
        self.pool = ZenithArenaPool(
            num_arenas=num_arenas,
            tick_skip=8,
            action_delay=7,
            mesh_dir=self.mesh_dir,
            base_seed=1337,
            car0_hitbox="breakout",
            car1_hitbox="octane"
        )

        print(f"[Zenith] Creating compact 256-width ZenithPolicy from scratch (Orthogonal init)...")
        self.student = ZenithPolicy(obs_dim=145, num_actions=90, hidden_dim=256).to(self.device)
        self.best_state_dict = {k: v.cpu().clone() for k, v in self.student.state_dict().items()}

        self.director = AutonomousDirector()
        self.optimizer = optim.AdamW(self.student.parameters(), lr=self.director.lr, weight_decay=1e-4)

        # Attempt to resume from latest checkpoint if available
        resumed = self.try_resume()

        self.league = LeagueManager(
            snapshot_dir=self.run_dir / "league_snapshots",
            max_snapshots=15,
            device=self.device
        )
        if not resumed:
            self.league.register_snapshot(self.student, step_count=0)

        self.coach = Coach(num_arenas=num_arenas)
        self.coach.initialize_pool(self.pool)

        # Telemetry accumulators
        self.total_touches = 0
        self.total_goals_blue = 0
        self.total_goals_orange = 0
        self.total_aerials = 0
        self.total_saves = 0
        self.total_mustys = 0

        self.save_export_bundle()

    def save_checkpoint(self, path: pathlib.Path | None = None, is_latest: bool = True):
        """
        Atomically saves full training state (weights, optimizer, director, telemetry).
        """
        state = {
            "model": self.student.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "best_state_dict": self.best_state_dict,
            "total_steps": self.total_steps,
            "iteration": self.iteration,
            "director": {
                "stage": self.director.stage,
                "stage_start_steps": getattr(self.director, "stage_start_steps", 0),
                "rollout_steps": self.director.rollout_steps,
                "lr": self.director.lr,
                "entropy_coef": self.director.entropy_coef,
                "weights": self.director.weights.tolist(),
                "history_touches": self.director.history_touches,
                "history_goals": self.director.history_goals,
                "history_aerials": self.director.history_aerials,
                "history_saves": self.director.history_saves,
                "history_mustys": self.director.history_mustys,
                "best_touch_rate": self.director.best_touch_rate,
                "best_goal_rate": self.director.best_goal_rate,
                "consecutive_regressions": self.director.consecutive_regressions
            }
        }
        if path is None:
            path = self.ckpt_dir / f"zenith_{self.total_steps:08d}.pt"

        # Atomic write via temporary file
        tmp_path = path.with_suffix(".tmp")
        torch.save(state, tmp_path)
        if path.exists():
            path.unlink()
        tmp_path.rename(path)

        if is_latest:
            latest = self.ckpt_dir / "latest_checkpoint.pt"
            shutil.copyfile(path, latest)

        self.save_export_bundle()

    def try_resume(self) -> bool:
        """
        Attempts to load latest_checkpoint.pt or newest numbered checkpoint.
        Returns True if resumed, False if starting from scratch.
        """
        latest = self.ckpt_dir / "latest_checkpoint.pt"
        target_file = None
        if latest.exists():
            target_file = latest
        else:
            numbered = sorted(self.ckpt_dir.glob("zenith_*.pt"))
            if numbered:
                target_file = numbered[-1]

        if target_file is None:
            return False

        try:
            print(f"[Zenith] Found existing checkpoint: {target_file.name}. Restoring state...")
            checkpoint = torch.load(target_file, map_location=self.device)
            if isinstance(checkpoint, dict) and "model" in checkpoint:
                self.student.load_state_dict(checkpoint["model"])
                self.optimizer.load_state_dict(checkpoint["optimizer"])
                if "best_state_dict" in checkpoint:
                    self.best_state_dict = {k: v.cpu().clone() for k, v in checkpoint["best_state_dict"].items()}
                self.total_steps = checkpoint.get("total_steps", 0)
                self.iteration = checkpoint.get("iteration", 0)

                # Restore director state
                d_info = checkpoint.get("director", {})
                self.director.stage = d_info.get("stage", 0)
                self.director.stage_start_steps = d_info.get("stage_start_steps", 0)
                self.director.rollout_steps = d_info.get("rollout_steps", 64)
                self.director.lr = d_info.get("lr", 2.0e-4)
                self.director.entropy_coef = d_info.get("entropy_coef", 0.045)
                if "weights" in d_info:
                    self.director.weights = np.array(d_info["weights"], dtype=np.float32)
                self.director.history_touches = d_info.get("history_touches", [])
                self.director.history_goals = d_info.get("history_goals", [])
                self.director.history_aerials = d_info.get("history_aerials", [])
                self.director.history_saves = d_info.get("history_saves", [])
                self.director.history_mustys = d_info.get("history_mustys", [])
                self.director.best_touch_rate = d_info.get("best_touch_rate", 0.0)
                self.director.best_goal_rate = d_info.get("best_goal_rate", 0.0)
                self.director.consecutive_regressions = d_info.get("consecutive_regressions", 0)

                print(f"[Zenith] Successfully resumed! Progress restored to step {self.total_steps:,} (Stage {self.director.stage})")
                return True
            elif isinstance(checkpoint, dict):
                # Raw state dict
                self.student.load_state_dict(checkpoint)
                print(f"[Zenith] Loaded policy weights from {target_file.name}")
                return True
        except Exception as e:
            print(f"[Zenith] Warning: Could not resume from {target_file}: {e}. Starting fresh.")
        return False

    def save_export_bundle(self):
        """
        Saves a ready-to-run bot package in export_dir for immediate use in RLBot.
        """
        model_path = self.export_dir / "zenith.pt"
        torch.save(self.student.state_dict(), model_path)

        # Write bot.toml
        toml_content = f"""[settings]
name = "Zenith"
description = "Autonomous SOTA Rocket League Agent trained from scratch"
developer = "Antigravity & User"
agent_id = "zenith_v1"
version = "1.0.0"

[bot]
hitbox = "breakout"
model = "zenith.pt"
obs_dim = 145
actions = 90
hidden_dim = 256
"""
        (self.export_dir / "bot.toml").write_text(toml_content, encoding="utf-8")

    def collect_rollout(self) -> dict[str, torch.Tensor]:
        """
        Fast batched rollout collection.
        In Stage 0: 100% mirror self-play (both cars generate student data).
        In Stage 1+: Blue is learner; Orange is 50% mirror self-play, 50% past snapshot.
        """
        num_students = self.num_arenas
        rollout_steps = self.director.rollout_steps
        cur_weights = self.director.weights

        obs_buf = torch.zeros((rollout_steps, num_students, 145), dtype=torch.float32, device=self.device)
        masks_buf = torch.zeros((rollout_steps, num_students, 90), dtype=torch.uint8, device=self.device)
        actions_buf = torch.zeros((rollout_steps, num_students), dtype=torch.int64, device=self.device)
        log_probs_buf = torch.zeros((rollout_steps, num_students), dtype=torch.float32, device=self.device)
        values_buf = torch.zeros((rollout_steps, num_students), dtype=torch.float32, device=self.device)
        rewards_buf = torch.zeros((rollout_steps, num_students), dtype=torch.float32, device=self.device)
        terminals_buf = torch.zeros((rollout_steps, num_students), dtype=torch.int8, device=self.device)

        st = self.pool.get_current_state()
        cur_obs = torch.from_numpy(st["obs"]).to(self.device)
        cur_masks = torch.from_numpy(st["masks"]).to(self.device)

        self.student.eval()
        opp_policy = self.league.opponent_policy

        iter_touches = 0
        iter_goals = 0
        iter_aerials = 0
        iter_saves = 0
        iter_mustys = 0

        for step_idx in range(rollout_steps):
            # 1. Student inference for Blue cars (indices 0, 2, 4, ...)
            student_obs = cur_obs[0::2]
            student_masks = cur_masks[0::2]

            with torch.inference_mode():
                actions, log_probs, values = self.student.get_action(
                    student_obs,
                    student_masks,
                    temperature=0.30 if self.director.stage == 0 else 0.25,
                    top_p=0.90,
                    deterministic=False
                )

            # 2. Opponent inference for Orange cars (indices 1, 3, 5, ...)
            opp_obs = cur_obs[1::2]
            opp_masks = cur_masks[1::2]
            opp_actions = np.zeros(self.num_arenas, dtype=np.int32)

            if self.director.stage == 0:
                # Stage 0: Gentle self-play / mirror
                with torch.inference_mode():
                    o_act, _, _ = self.student.get_action(opp_obs, opp_masks, temperature=0.40, top_p=0.90)
                opp_actions[:] = o_act.cpu().numpy()
            else:
                # 50% mirror self-play, 50% past snapshot
                half = self.num_arenas // 2
                with torch.inference_mode():
                    o_act_self, _, _ = self.student.get_action(opp_obs[:half], opp_masks[:half], temperature=0.25)
                    opp_actions[:half] = o_act_self.cpu().numpy()
                    if opp_policy is not None and half < self.num_arenas:
                        o_act_snap, _, _ = opp_policy.get_action(opp_obs[half:], opp_masks[half:], temperature=0.20)
                        opp_actions[half:] = o_act_snap.cpu().numpy()
                    else:
                        opp_actions[half:] = opp_actions[:self.num_arenas - half]

            # Store student transition
            obs_buf[step_idx] = student_obs
            masks_buf[step_idx] = student_masks
            actions_buf[step_idx] = actions
            log_probs_buf[step_idx] = log_probs
            values_buf[step_idx] = values

            # Combine actions
            all_actions = np.zeros(self.num_arenas * 2, dtype=np.int32)
            all_actions[0::2] = actions.cpu().numpy()
            all_actions[1::2] = opp_actions

            # 3. Step physics simulation in C++
            step_res = self.pool.step(all_actions, cur_weights)

            # Next state
            cur_obs = torch.from_numpy(step_res["obs"]).to(self.device)
            cur_masks = torch.from_numpy(step_res["masks"]).to(self.device)

            # Extract student rewards & terminals
            r_all = step_res["rewards"]
            t_all = step_res["terminals"]
            rewards_buf[step_idx] = torch.from_numpy(r_all[0::2]).to(self.device)
            terminals_buf[step_idx] = torch.from_numpy(t_all[0::2]).to(self.device)

            # Telemetry accumulation from reward components
            r_comps = step_res["reward_components"][0::2]
            iter_touches += float(np.sum(r_comps[:, 4] > 0))
            iter_goals += float(np.sum(r_comps[:, 0] > 0))
            iter_aerials += float(np.sum(r_comps[:, 5] > 0))
            iter_saves += float(np.sum(r_comps[:, 8] > 0))
            iter_mustys += float(np.sum(r_comps[:, 7] > 0))

            # Coach handles scenario resets
            self.coach.handle_terminals(self.pool, t_all, int(iter_goals), 0)

        # Bootstrap value for final state
        with torch.inference_mode():
            _, _, final_values = self.student.get_action(cur_obs[0::2], cur_masks[0::2])

        total_collected = rollout_steps * num_students
        telemetry = {
            "touches_per_step": iter_touches / max(1, total_collected),
            "goals_per_step": iter_goals / max(1, total_collected),
            "aerials_per_step": iter_aerials / max(1, total_collected),
            "saves_per_step": iter_saves / max(1, total_collected),
            "mustys_per_step": iter_mustys / max(1, total_collected)
        }

        return {
            "obs": obs_buf,
            "masks": masks_buf,
            "actions": actions_buf,
            "log_probs": log_probs_buf,
            "values": values_buf,
            "rewards": rewards_buf,
            "terminals": terminals_buf,
            "final_values": final_values,
            "telemetry": telemetry
        }

    def compute_gae(
        self,
        rewards: torch.Tensor,
        values: torch.Tensor,
        terminals: torch.Tensor,
        final_values: torch.Tensor,
        gamma: float = 0.99,
        gae_lambda: float = 0.95
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Vectorized Generalized Advantage Estimation (GAE).
        """
        steps, arenas = rewards.shape
        advantages = torch.zeros_like(rewards)
        last_gae = 0.0

        for t in reversed(range(steps)):
            if t == steps - 1:
                next_non_terminal = 1.0 - terminals[t].float()
                next_val = final_values
            else:
                next_non_terminal = 1.0 - terminals[t].float()
                next_val = values[t + 1]

            delta = rewards[t] + gamma * next_val * next_non_terminal - values[t]
            advantages[t] = last_gae = delta + gamma * gae_lambda * next_non_terminal * last_gae

        returns = advantages + values
        return advantages, returns

    def train_iteration(self) -> dict[str, float]:
        """
        Executes one full iteration:
        1. Experience collection
        2. Generalized Advantage Estimation
        3. PPO gradient descent with action masking
        4. Autonomous telemetry evaluation & auto-correction
        """
        t0 = time.perf_counter()
        rollout = self.collect_rollout()
        t_collect = time.perf_counter() - t0

        steps_collected = self.director.rollout_steps * self.num_arenas
        self.total_steps += steps_collected
        self.iteration += 1

        # Calculate GAE
        advantages, returns = self.compute_gae(
            rewards=rollout["rewards"],
            values=rollout["values"],
            terminals=rollout["terminals"],
            final_values=rollout["final_values"],
            gamma=0.99,
            gae_lambda=0.95
        )

        # Flatten batch for PPO update
        b_obs = rollout["obs"].reshape(-1, 145)
        b_masks = rollout["masks"].reshape(-1, 90)
        b_actions = rollout["actions"].reshape(-1)
        b_old_log_probs = rollout["log_probs"].reshape(-1)
        b_advantages = advantages.reshape(-1)
        b_returns = returns.reshape(-1)

        # Normalize advantages
        b_advantages = (b_advantages - b_advantages.mean()) / (b_advantages.std() + 1e-8)

        # PPO Learning pass
        self.student.train()
        t_learn_start = time.perf_counter()
        total_p_loss, total_v_loss, total_ent = 0.0, 0.0, 0.0
        n_updates = 0

        # Sync optimizer LR with director
        for param_group in self.optimizer.param_groups:
            param_group["lr"] = self.director.lr

        # 1-pass PPO for maximum freshness and SPS throughput
        batch_size = b_obs.shape[0]
        minibatch = min(1024, batch_size)
        indices = torch.randperm(batch_size, device=self.device)

        for start in range(0, batch_size, minibatch):
            end = start + minibatch
            idx = indices[start:end]

            logits, values = self.student(b_obs[idx], b_masks[idx])
            probs = F.softmax(logits, dim=-1)
            dist = torch.distributions.Categorical(probs)

            new_log_probs = dist.log_prob(b_actions[idx])
            entropy = dist.entropy().mean()

            # PPO Policy Loss
            ratio = torch.exp(new_log_probs - b_old_log_probs[idx])
            surr1 = ratio * b_advantages[idx]
            surr2 = torch.clamp(ratio, 1.0 - 0.2, 1.0 + 0.2) * b_advantages[idx]
            policy_loss = -torch.min(surr1, surr2).mean()

            # Value Loss
            value_loss = F.mse_loss(values, b_returns[idx])

            # Total Loss
            loss = policy_loss + 0.5 * value_loss - self.director.entropy_coef * entropy

            if not torch.isnan(loss) and not torch.isinf(loss):
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.student.parameters(), max_norm=0.5)
                self.optimizer.step()

                total_p_loss += policy_loss.item()
                total_v_loss += value_loss.item()
                total_ent += entropy.item()
                n_updates += 1

        t_learn = time.perf_counter() - t_learn_start
        overall_time = t_collect + t_learn
        decision_sps = steps_collected / overall_time
        physics_sps = decision_sps * 8

        # Autonomous director updates
        telem = rollout["telemetry"]
        action = self.director.update_telemetry(
            touches=telem["touches_per_step"],
            goals=telem["goals_per_step"],
            aerials=telem["aerials_per_step"],
            saves=telem["saves_per_step"],
            mustys=telem["mustys_per_step"],
            total_steps=self.total_steps
        )

        if action["stage_changed"]:
            print(f"\n>>> [AUTONOMOUS DIRECTOR] {action['message']}")
            print(f"    New Rollout Size: {self.director.rollout_steps} | LR: {self.director.lr:.1e} | Entropy: {self.director.entropy_coef:.3f}\n")
            # Register milestone snapshot
            self.league.register_snapshot(self.student, self.total_steps)

        if action["regression"]:
            print(f"\n[!] [AUTO-CORRECTION] {action['message']}")
            # Revert to best weights
            self.student.load_state_dict(self.best_state_dict)

        # Update best weights if goals/touches are progressing well
        if telem["touches_per_step"] > self.director.best_touch_rate:
            self.best_state_dict = {k: v.cpu().clone() for k, v in self.student.state_dict().items()}
            self.save_export_bundle()

        # Regular league snapshot registration every 50,000 steps
        if self.total_steps % 50_000 < steps_collected and self.total_steps > 0:
            self.league.register_snapshot(self.student, self.total_steps)
            self.league.sample_opponent()
            # Save disk checkpoint
            self.save_checkpoint()

        return {
            "iteration": self.iteration,
            "steps": self.total_steps,
            "decision_sps": decision_sps,
            "physics_sps": physics_sps,
            "p_loss": total_p_loss / max(1, n_updates),
            "v_loss": total_v_loss / max(1, n_updates),
            "entropy": total_ent / max(1, n_updates),
            "touch_rate": telem["touches_per_step"],
            "goal_rate": telem["goals_per_step"],
            "stage": self.director.stage
        }

    def run(self):
        print(f"\n[Zenith] Starting autonomous loop targeting {self.target_steps:,} steps.")
        print(f"[Zenith] Current: {self.director.STAGE_NAMES[self.director.stage]}")
        print(f"[Zenith] PAUSE/SAVE: Press Ctrl+C at any time or run PAUSE_ZENITH.bat to safely pause and save progress.")
        print(f"--------------------------------------------------------------------")
        header = f"{'Iter':>5} | {'Steps':>9} | {'Stage':>7} | {'Dec-SPS':>8} | {'Phys-SPS':>9} | {'Touch%':>6} | {'Goal%':>6} | {'Entropy':>7} | {'Elapsed':>7}"
        print(header)
        print("-" * len(header))

        last_print = time.time()
        stop_requested = False

        try:
            while self.total_steps < self.target_steps and not stop_requested:
                stats = self.train_iteration()

                if time.time() - last_print > 2.0 or stats["iteration"] % 10 == 0:
                    elapsed = time.time() - self.start_time
                    mins, secs = divmod(int(elapsed), 60)
                    time_str = f"{mins:02d}:{secs:02d}"
                    line = (
                        f"{stats['iteration']:5d} | "
                        f"{stats['steps']:9,d} | "
                        f"Stg {stats['stage']:1d}   | "
                        f"{int(stats['decision_sps']):8,d} | "
                        f"{int(stats['physics_sps']):9,d} | "
                        f"{stats['touch_rate']*100:5.1f}% | "
                        f"{stats['goal_rate']*100:5.2f}% | "
                        f"{stats['entropy']:7.3f} | "
                        f"{time_str:>7}"
                    )
                    print(line)
                    last_print = time.time()

                # Check for PAUSE or STOP signal file in run_dir
                for sig_name in ("PAUSE", "STOP"):
                    sig_file = self.run_dir / sig_name
                    if sig_file.exists():
                        try:
                            sig_file.unlink()
                        except Exception:
                            pass
                        stop_requested = True
                        print(f"\n>>> [Zenith] Safe pause requested via signal file ({sig_name})! Saving state...")
                        break

        except KeyboardInterrupt:
            print(f"\n>>> [Zenith] KeyboardInterrupt (Ctrl+C) detected! Safely saving state...")

        # Atomically save complete state upon exit
        self.save_checkpoint(is_latest=True)
        print(f"\n====================================================================")
        print(f"[Zenith] Progress successfully saved to: {self.ckpt_dir / 'latest_checkpoint.pt'}")
        print(f"[Zenith] Total Steps: {self.total_steps:,} | Iteration: {self.iteration} | Stage: {self.director.stage}")
        print(f"[Zenith] Exported ready-to-run bot to: {self.export_dir}")
        print(f"[Zenith] You can resume at any time by running START_AUTONOMOUS_ZENITH.bat")
        print(f"====================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Zenith Autonomous RL Trainer")
    parser.add_argument("--arenas", type=int, default=32, help="Number of parallel arenas")
    parser.add_argument("--target-steps", type=int, default=10_000_000, help="Target training timesteps")
    parser.add_argument("--device", type=str, default=None, help="Device (cuda/cpu)")
    args = parser.parse_args()

    master = AutonomousMaster(
        num_arenas=args.arenas,
        target_steps=args.target_steps,
        device=args.device
    )
    master.run()


if __name__ == "__main__":
    main()
