"""
Zenith Master Training Engine
High-throughput PPO loop orchestrating:
- Native multi-arena RocketSim C++ simulation
- Top-p (nucleus) action sampling & action masking
- 12-component dynamic reward shaping
- Chronos & Galactus teacher distillation (KL kickstart)
- Prioritized Fictitious Self-Play (PFSP)
- 5 curriculum skill drills (Arsenal Flip Reset Musty, Prejump saves, Anti-fake)
- Continuous Referee gauntlet with automatic rollback protection
"""
from __future__ import annotations

import os
import sys
import time
import json
import pathlib
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from .policy import ZenithPolicy
from .reward_director import RewardDirector
from .teachers import TeacherEnsemble
from .coach import Coach
from .league import LeagueManager
from .referee import Referee
from .zenith_sim import ZenithArenaPool


class ZenithTrainer:
    def __init__(
        self,
        num_arenas: int = 32,
        rollout_steps: int = 128,
        mesh_dir: str | None = None,
        run_dir: str = r"E:\Downloads\Chat_GPT_AI\zenith\runs\zenith_master_01",
        lr: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        vf_coef: float = 0.5,
        ent_coef: float = 0.01,
        ppo_epochs: int = 3,
        minibatch_size: int = 512,
        eval_interval: int = 100_000,
        snapshot_interval: int = 50_000,
        device: str | None = None
    ):
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        print(f"[Zenith] Operating on device: {self.device}")
        if self.device.type == "cuda":
            print(f"[Zenith] GPU: {torch.cuda.get_device_name(0)} (VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**2):.0f} MiB)")

        self.num_arenas = num_arenas
        self.rollout_steps = rollout_steps
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_range = clip_range
        self.vf_coef = vf_coef
        self.ent_coef = ent_coef
        self.ppo_epochs = ppo_epochs
        self.minibatch_size = minibatch_size
        self.eval_interval = eval_interval
        self.snapshot_interval = snapshot_interval

        self.run_dir = pathlib.Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ckpt_dir = self.run_dir / "checkpoints"
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.run_dir / "metrics.jsonl"

        if mesh_dir is None:
            self.mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
        else:
            self.mesh_dir = mesh_dir

        print(f"[Zenith] Initializing simulation pool with {num_arenas} arenas (64 agents)...")
        self.pool = ZenithArenaPool(
            num_arenas=num_arenas,
            tick_skip=8,
            action_delay=7,
            mesh_dir=self.mesh_dir,
            base_seed=42,
            car0_hitbox="breakout",
            car1_hitbox="octane"
        )

        print("[Zenith] Initializing student Actor-Critic policy...")
        self.student = ZenithPolicy(obs_dim=145, num_actions=90, hidden_dim=512).to(self.device)
        self.optimizer = optim.AdamW(self.student.parameters(), lr=lr, weight_decay=1e-4)

        print("[Zenith] Initializing cooperating systems...")
        self.reward_director = RewardDirector(stage="balanced")
        self.teachers = TeacherEnsemble(device=self.device)
        self.mirror_map = self.pool.get_action_mirror_map()
        self.coach = Coach(num_arenas=num_arenas)
        self.coach.initialize_pool(self.pool)

        self.league = LeagueManager(
            snapshot_dir=self.run_dir / "league_snapshots",
            max_snapshots=20,
            device=self.device
        )
        # Register initial snapshot
        self.league.register_snapshot(self.student, step_count=0)

        self.referee = Referee(
            mesh_dir=self.mesh_dir,
            chronos_path=self.teachers.DEFAULT_CHRONOS_PATH,
            galactus_path=self.teachers.DEFAULT_GALACTUS_PATH,
            best_checkpoint_dir=self.run_dir / "best_champions",
            num_eval_arenas=16,
            device=self.device
        )

        self.total_steps = 0
        self.last_eval_step = 0
        self.last_snap_step = 0
        self.start_time = time.time()

    def collect_rollouts(self) -> dict[str, torch.Tensor]:
        """
        Collects one rollout horizon across all arenas.
        Student operates on Blue cars (even indices).
        Opponents operate on Orange cars (odd indices).
        """
        num_students = self.num_arenas
        total_players = self.num_arenas * 2

        # Rollout storage tensors
        obs_buf = torch.zeros((self.rollout_steps, num_students, 145), dtype=torch.float32, device=self.device)
        masks_buf = torch.zeros((self.rollout_steps, num_students, 90), dtype=torch.uint8, device=self.device)
        actions_buf = torch.zeros((self.rollout_steps, num_students), dtype=torch.long, device=self.device)
        log_probs_buf = torch.zeros((self.rollout_steps, num_students), dtype=torch.float32, device=self.device)
        values_buf = torch.zeros((self.rollout_steps, num_students), dtype=torch.float32, device=self.device)
        rewards_buf = torch.zeros((self.rollout_steps, num_students), dtype=torch.float32, device=self.device)
        terminals_buf = torch.zeros((self.rollout_steps, num_students), dtype=torch.float32, device=self.device)
        teacher_probs_buf = torch.zeros((self.rollout_steps, num_students, 90), dtype=torch.float32, device=self.device)

        r_comps_accum = []
        cur_weights = self.reward_director.get_weights()

        st = self.pool.get_current_state()
        cur_obs = torch.from_numpy(st["obs"]).to(self.device)
        cur_masks = torch.from_numpy(st["masks"]).to(self.device)

        self.student.eval()

        for step_idx in range(self.rollout_steps):
            # 1. Student inference (Blue cars: 0, 2, 4, ...)
            student_obs = cur_obs[0::2]
            student_masks = cur_masks[0::2]

            with torch.inference_mode():
                actions, log_probs, values = self.student.get_action(
                    student_obs,
                    student_masks,
                    temperature=0.25,
                    top_p=0.90,
                    deterministic=False
                )

                # Teacher distillation target
                teacher_probs = self.teachers.compute_teacher_probs(
                    self.pool,
                    player_idx=0,
                    masks=student_masks
                )

            # 2. Opponent inference (Orange cars: 1, 3, 5, ...)
            opp_obs = cur_obs[1::2]
            opp_masks = cur_masks[1::2]

            opp_actions = np.zeros(self.num_arenas, dtype=np.int32)
            n_self = self.num_arenas // 2
            n_chronos = (self.num_arenas - n_self) // 2
            n_galactus = self.num_arenas - n_self - n_chronos

            # 50% arenas: Self-play PFSP
            if n_self > 0:
                opp_actions[:n_self] = self.league.get_opponent_actions(
                    opp_obs[:n_self], opp_masks[:n_self], deterministic=False
                ).cpu().numpy()

            # 25% arenas: Live Chronos sparring (with proper un-mirroring)
            if n_chronos > 0:
                c_idx_start = n_self
                c_idx_end = n_self + n_chronos
                c_obs_np = self.pool.get_teacher_obs_batch(1, "chronos")[c_idx_start:c_idx_end]
                c_obs = torch.from_numpy(c_obs_np).to(self.device)
                c_masks = opp_masks[c_idx_start:c_idx_end]
                with torch.inference_mode():
                    c_logits = self.teachers.chronos(c_obs).masked_fill(c_masks == 0, -1e9)
                    c_raw = torch.argmax(c_logits, dim=-1).cpu().numpy()
                mirror_flags = self.pool.get_teacher_mirror_flags(1)[c_idx_start:c_idx_end]
                for k in range(n_chronos):
                    if mirror_flags[k]:
                        opp_actions[c_idx_start + k] = self.mirror_map[c_raw[k]]
                    else:
                        opp_actions[c_idx_start + k] = c_raw[k]

            # 25% arenas: Live Galactus sparring
            if n_galactus > 0:
                g_idx_start = n_self + n_chronos
                g_idx_end = self.num_arenas
                g_obs_np = self.pool.get_teacher_obs_batch(1, "galactus")[g_idx_start:g_idx_end]
                g_obs = torch.from_numpy(g_obs_np).to(self.device)
                g_masks = opp_masks[g_idx_start:g_idx_end]
                with torch.inference_mode():
                    g_logits = self.teachers.galactus(g_obs).masked_fill(g_masks == 0, -1e9)
                    opp_actions[g_idx_start:g_idx_end] = torch.argmax(g_logits, dim=-1).cpu().numpy()

            # Store student transition
            obs_buf[step_idx] = student_obs
            masks_buf[step_idx] = student_masks
            actions_buf[step_idx] = actions
            log_probs_buf[step_idx] = log_probs
            values_buf[step_idx] = values
            teacher_probs_buf[step_idx] = teacher_probs

            # Combine actions into flat numpy array
            all_actions = np.zeros(total_players, dtype=np.int32)
            all_actions[0::2] = actions.cpu().numpy()
            all_actions[1::2] = opp_actions

            # 3. Step physics simulation
            step_res = self.pool.step(all_actions, cur_weights)

            # Next observations
            cur_obs = torch.from_numpy(step_res["obs"]).to(self.device)
            cur_masks = torch.from_numpy(step_res["masks"]).to(self.device)

            # Rewards and terminals for student
            r_all = step_res["rewards"]
            t_all = step_res["terminals"]
            rewards_buf[step_idx] = torch.from_numpy(r_all[0::2]).to(self.device)
            terminals_buf[step_idx] = torch.from_numpy(t_all[0::2]).to(self.device)
            r_comps_accum.append(step_res["reward_components"][0::2])

            # Coach monitors terminals & resets
            self.coach.handle_terminals(
                self.pool,
                step_res["terminals"],
                step_res["goals_blue"],
                step_res["goals_orange"]
            )

        # Value estimation for final state (bootstrapping)
        with torch.inference_mode():
            next_values = self.student.get_value(cur_obs[0::2])

        # Compute GAE advantages
        advantages = torch.zeros_like(rewards_buf)
        last_gae_lam = 0.0
        for t in reversed(range(self.rollout_steps)):
            if t == self.rollout_steps - 1:
                next_non_terminal = 1.0 - terminals_buf[t]
                next_val = next_values
            else:
                next_non_terminal = 1.0 - terminals_buf[t]
                next_val = values_buf[t + 1]

            delta = rewards_buf[t] + self.gamma * next_val * next_non_terminal - values_buf[t]
            advantages[t] = last_gae_lam = delta + self.gamma * self.gae_lambda * next_non_terminal * last_gae_lam

        returns = advantages + values_buf

        # Flatten buffers across time and arena dimensions
        batch_size = self.rollout_steps * num_students
        self.total_steps += batch_size

        mean_comps = np.mean(np.concatenate(r_comps_accum, axis=0), axis=0)
        telemetry_comps = {name: float(mean_comps[i]) for i, name in enumerate(self.reward_director.COMPONENT_NAMES)}

        return {
            "obs": obs_buf.reshape(batch_size, 145),
            "masks": masks_buf.reshape(batch_size, 90),
            "actions": actions_buf.reshape(batch_size),
            "log_probs": log_probs_buf.reshape(batch_size),
            "values": values_buf.reshape(batch_size),
            "advantages": advantages.reshape(batch_size),
            "returns": returns.reshape(batch_size),
            "teacher_probs": teacher_probs_buf.reshape(batch_size, 90),
            "telemetry_comps": telemetry_comps,
            "mean_reward": float(rewards_buf.mean().item())
        }

    def train_epoch(self, batch: dict[str, torch.Tensor]) -> dict[str, float]:
        """
        Runs mini-batch PPO optimization with KL teacher distillation.
        """
        self.student.train()
        total_samples = batch["obs"].shape[0]

        # Normalize advantages
        adv = batch["advantages"]
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)

        policy_losses = []
        value_losses = []
        entropy_losses = []
        kd_losses = []

        for _ in range(self.ppo_epochs):
            indices = torch.randperm(total_samples, device=self.device)
            for start in range(0, total_samples, self.minibatch_size):
                end = start + self.minibatch_size
                mb_idx = indices[start:end]

                mb_obs = batch["obs"][mb_idx]
                mb_masks = batch["masks"][mb_idx]
                mb_actions = batch["actions"][mb_idx]
                mb_old_log_probs = batch["log_probs"][mb_idx]
                mb_returns = batch["returns"][mb_idx]
                mb_adv = adv[mb_idx]
                mb_teacher_probs = batch["teacher_probs"][mb_idx]

                # Evaluate current policy
                new_log_probs, new_values, entropy = self.student.evaluate_actions(
                    mb_obs,
                    mb_actions,
                    mb_masks
                )

                # Clipped surrogate objective
                ratio = torch.exp(new_log_probs - mb_old_log_probs)
                surr1 = ratio * mb_adv
                surr2 = torch.clamp(ratio, 1.0 - self.clip_range, 1.0 + self.clip_range) * mb_adv
                policy_loss = -torch.min(surr1, surr2).mean()

                # Value loss (Huber/MSE)
                value_loss = 0.5 * F.mse_loss(new_values, mb_returns)

                # Entropy bonus
                entropy_loss = -entropy.mean()

                # Kickstart distillation loss (KL against Chronos + Galactus)
                logits = self.student.actor(mb_obs)
                kd_loss = self.teachers.compute_kd_loss(logits, mb_teacher_probs, mb_masks)

                # Total loss
                loss = policy_loss + self.vf_coef * value_loss + self.ent_coef * entropy_loss + kd_loss

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.student.parameters(), max_norm=0.5)
                self.optimizer.step()

                policy_losses.append(policy_loss.item())
                value_losses.append(value_loss.item())
                entropy_losses.append(entropy.mean().item())
                kd_losses.append(kd_loss.item())

        return {
            "policy_loss": float(np.mean(policy_losses)),
            "value_loss": float(np.mean(value_losses)),
            "entropy": float(np.mean(entropy_losses)),
            "kd_loss": float(np.mean(kd_losses))
        }

    def run_loop(self, target_steps: int = 10_000_000):
        """
        Master non-stop execution loop.
        """
        print(f"[Zenith] Commencing non-stop training loop -> Target: {target_steps:,} steps...")
        iteration = 0

        while self.total_steps < target_steps:
            iter_start = time.time()
            iteration += 1

            # 1. Rollout
            rollout = self.collect_rollouts()

            # 2. Optimization
            train_metrics = self.train_epoch(rollout)

            # 3. Schedule updates
            self.reward_director.update_schedule(self.total_steps)

            iter_duration = time.time() - iter_start
            batch_size = self.rollout_steps * self.num_arenas
            fps = batch_size / max(1e-4, iter_duration)

            # 4. Telemetry logging
            comps = rollout["telemetry_comps"]
            print(
                f"[Iter {iteration:04d} | Step {self.total_steps:,}] "
                f"FPS: {fps:.0f} | Rew: {rollout['mean_reward']:.2f} | "
                f"Goal: {comps['goal']:.3f} | Touch: {comps['touch']:.3f} | "
                f"Air: {comps['aerial_touch']:.3f} | Reset: {comps['flip_reset']:.3f} | "
                f"Musty: {comps['musty_flick']:.3f} | Save: {comps['save']:.3f} | "
                f"Prejump: {comps['prejump']:.3f} | FakePen: {comps['fake_penalty']:.3f} | "
                f"KD_Loss: {train_metrics['kd_loss']:.4f} | Pi_Loss: {train_metrics['policy_loss']:.4f}"
            )

            # Save periodic metric record
            metric_entry = {
                "iteration": iteration,
                "step": self.total_steps,
                "timestamp": time.time(),
                "fps": fps,
                "mean_reward": rollout["mean_reward"],
                **comps,
                **train_metrics,
                "kd_weight": self.teachers.current_kd_weight
            }
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(metric_entry) + "\n")

            # 5. Snapshot registration for League PFSP
            if self.total_steps - self.last_snap_step >= self.snapshot_interval:
                self.last_snap_step = self.total_steps
                snap_name = self.league.register_snapshot(self.student, self.total_steps)
                print(f"[League] Registered new snapshot: {snap_name}")

            # 6. Periodic Referee Benchmark & Rollback Guard
            if self.total_steps - self.last_eval_step >= self.eval_interval:
                self.last_eval_step = self.total_steps
                print("\n" + "=" * 70)
                print(f"[Referee] EXECUTING OFFICIAL GAUNTLET AT STEP {self.total_steps:,}...")
                print("=" * 70)

                # Gauntlet vs Chronos
                telem_chronos = self.referee.evaluate_gauntlet(self.student, opponent_name="chronos", max_games=32)
                is_best_c, msg_c = self.referee.check_checkpoint(self.student, self.total_steps, telem_chronos)
                print(f"[Referee vs Chronos] {msg_c}")
                print(
                    f"   Score: {telem_chronos['student_wins']}-{telem_chronos['opponent_wins']} "
                    f"({telem_chronos['win_rate']:.1%}) [{telem_chronos['win_rate_ci_lower']:.1%}, {telem_chronos['win_rate_ci_upper']:.1%}] | "
                    f"Resets: {telem_chronos['resets_triggered']} | Mustys: {telem_chronos['mustys_triggered']} | Saves: {telem_chronos['saves_triggered']}"
                )

                # Gauntlet vs Galactus
                telem_galactus = self.referee.evaluate_gauntlet(self.student, opponent_name="galactus", max_games=32)
                print(
                    f"[Referee vs Galactus] Score: {telem_galactus['student_wins']}-{telem_galactus['opponent_wins']} "
                    f"({telem_galactus['win_rate']:.1%}) | Resets: {telem_galactus['resets_triggered']} | Mustys: {telem_galactus['mustys_triggered']}"
                )

                # Anneal teacher distillation based on win-rate
                avg_win_rate = 0.5 * (telem_chronos["win_rate"] + telem_galactus["win_rate"])
                self.teachers.anneal_kd_weight(avg_win_rate)
                print(f"[Distillation] Teacher KD weight annealed to: {self.teachers.current_kd_weight:.3f}")

                # Rollback Guard Action
                if "ROLLBACK RECOMMENDED" in msg_c:
                    print("[Referee Rollback Guard] Triggering safety rollback to best verified checkpoint!")
                    restored = self.referee.restore_best_checkpoint(self.student)
                    if restored:
                        # Reset optimizer momentum
                        self.optimizer = optim.AdamW(self.student.parameters(), lr=self.optimizer.param_groups[0]["lr"])
                        # Temporarily boost teacher distillation to recover ground
                        self.teachers.current_kd_weight = max(0.5, self.teachers.initial_kd_weight)
                        print("[Referee Rollback Guard] Policy restored, optimizer reset, KD guidance boosted.")

                print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Zenith Non-Stop RL Trainer")
    parser.add_argument("--arenas", type=int, default=32, help="Number of parallel soccar arenas")
    parser.add_argument("--rollout", type=int, default=128, help="Rollout steps per arena per iteration")
    parser.add_argument("--run-dir", type=str, default=r"E:\Downloads\Chat_GPT_AI\zenith\runs\zenith_master_01")
    parser.add_argument("--eval-interval", type=int, default=50_000, help="Steps between referee evaluations")
    parser.add_argument("--snapshot-interval", type=int, default=25_000, help="Steps between league snapshots")
    parser.add_argument("--target-steps", type=int, default=20_000_000, help="Total training steps target")
    args = parser.parse_args()

    trainer = ZenithTrainer(
        num_arenas=args.arenas,
        rollout_steps=args.rollout,
        run_dir=args.run_dir,
        eval_interval=args.eval_interval,
        snapshot_interval=args.snapshot_interval
    )
    trainer.run_loop(target_steps=args.target_steps)


if __name__ == "__main__":
    main()
