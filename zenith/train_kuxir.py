"""Zenith Kuxir Pinch & Wall-Roll Autonomous Trainer.

Fine-tunes a pre-trained base model (Nexto Student) on RocketSim to master:
1) Shepherding and rolling the ball up the side wall ramp.
2) Supersonic wall approach, air roll, and directional flip/dodge into the ball
   against the wall collider to execute maximum-speed Kuxir pinches.
"""
from __future__ import annotations

import os
import sys
import time
import math
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import torch
import torch.nn.functional as F

# Add paths
ZENITH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ZENITH_DIR.parent
if str(ZENITH_DIR) not in sys.path:
    sys.path.insert(0, str(ZENITH_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import rlgym.rocket_league.common_values as cv
from rlgym.rocket_league.sim import RocketSimEngine
from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator
from kuxir_policy import KuxirActorCritic, build_anchor_policy, NEXTO_STUDENT_PATH
from kuxir_env import KuxirMutator, KuxirReward, make_kuxir_components

RUNS_DIR = ZENITH_DIR / "runs" / "kuxir_pinch"
CKPT_DIR = RUNS_DIR / "checkpoints"
EXPORT_DIR = ZENITH_DIR / "export" / "zenith_kuxir"

CKPT_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


class ParallelKuxirEnvPool:
    """Manages N independent RocketSim arenas running in lockstep."""

    def __init__(self, num_envs: int = 16, episode_max_steps: int = 220):
        self.num_envs = num_envs
        self.episode_max_steps = episode_max_steps

        self.engines: List[RocketSimEngine] = [RocketSimEngine() for _ in range(num_envs)]
        self.team_mutator = FixedTeamSizeMutator(1, 1)
        self.kuxir_mutator = KuxirMutator(full_seq_ratio=0.50, climb_ratio=0.30)
        self.reward_fns: List[KuxirReward] = [KuxirReward() for _ in range(num_envs)]
        self.obs_builder, self.action_parser = make_kuxir_components()

        self.states = []
        self.step_counts = np.zeros(num_envs, dtype=np.int32)

        # Initialize all arenas
        for i in range(num_envs):
            base = self.engines[i].create_base_state()
            self.team_mutator.apply(base, {})
            self.kuxir_mutator.apply(base, {})
            st = self.engines[i].set_state(base, {})
            self.reward_fns[i].reset(st, {})
            self.states.append(st)

    def reset_env(self, env_idx: int):
        base = self.engines[env_idx].create_base_state()
        self.team_mutator.apply(base, {})
        self.kuxir_mutator.apply(base, {})
        st = self.engines[env_idx].set_state(base, {})
        self.reward_fns[env_idx].reset(st, {})
        self.states[env_idx] = st
        self.step_counts[env_idx] = 0
        return st

    def step(self, actions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, List[Dict[str, Any]]]:
        """Steps all N environments by 8 physics ticks."""
        next_obs = []
        rewards = np.zeros(self.num_envs, dtype=np.float32)
        dones = np.zeros(self.num_envs, dtype=bool)
        infos = []

        for i in range(self.num_envs):
            act_id = int(actions[i])
            parsed = self.action_parser.parse_actions({'blue-0': np.array([act_id])}, self.states[i], {})
            actions_raw = {
                'blue-0': parsed['blue-0'],
                'orange-0': np.zeros((8, 8), dtype=np.float32)
            }

            st = self.engines[i].step(actions_raw, {})
            self.step_counts[i] += 1

            term = {'blue-0': bool(st.goal_scored)}
            trunc = {'blue-0': bool(self.step_counts[i] >= self.episode_max_steps)}
            done = term['blue-0'] or trunc['blue-0']

            rews = self.reward_fns[i].get_rewards(['blue-0'], st, term, trunc, {})
            r = rews.get('blue-0', 0.0)

            # Record info
            bp = st.ball.position
            bv = st.ball.linear_velocity
            spd = float(np.linalg.norm(bv))
            dist_wall = 4096.0 - abs(float(bp[0]))
            is_pinch_contact = bool(st.cars['blue-0'].ball_touches > 0 and dist_wall < 320.0 and spd > 1600.0)

            info = {
                'ball_speed': spd,
                'is_pinch': is_pinch_contact,
                'goal': bool(st.goal_scored and float(bp[1]) > 5120.0),
                'wall_roll': bool(dist_wall < 250.0 and float(bv[2]) > 150.0)
            }

            if done:
                st = self.reset_env(i)

            self.states[i] = st
            rewards[i] = r
            dones[i] = done
            infos.append(info)

            o = self.obs_builder.build_obs(['blue-0'], st, {})['blue-0']
            next_obs.append(o)

        return np.array(next_obs, dtype=np.float32), rewards, dones, infos


def compute_gae(rewards: np.ndarray, values: np.ndarray, dones: np.ndarray,
                next_val: float, gamma: float = 0.995, lam: float = 0.95):
    """Generalized Advantage Estimation."""
    T = len(rewards)
    adv = np.zeros(T, dtype=np.float32)
    last_adv = 0.0
    for t in reversed(range(T)):
        non_terminal = 0.0 if dones[t] else 1.0
        val_next = next_val if t == T - 1 else values[t + 1]
        delta = rewards[t] + gamma * val_next * non_terminal - values[t]
        adv[t] = delta + gamma * lam * non_terminal * last_adv
        last_adv = adv[t]
    returns = adv + values
    return adv, returns


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Zenith Kuxir Pinch Trainer")
    parser.add_argument("--iterations", type=int, default=0, help="Max iterations (0 = infinite)")
    parser.add_argument("--envs", type=int, default=16, help="Number of parallel arenas")
    parser.add_argument("--rollout", type=int, default=256, help="Rollout length per arena")
    args = parser.parse_args()

    print("=" * 75)
    print("             ZENITH AUTONOMOUS KUXIR PINCH ENGINE")
    print("=" * 75)
    print(" * Initialization : Warm-Start from Nexto Student (Preserves Core Skills)")
    print(" * Base Checkpoint: data/nexto_student_v2.pt")
    print(" * Curriculum     : Phase 1 (Wall-Roll Setup) + Phase 2 (High-Speed Pinch)")
    print(" * Policy Arch    : 92-obs -> 512 -> 512 -> 90 discrete actions (~310k params)")
    print(" * Safety Anchor  : Frozen Nexto Student KL Divergence (Anti-Collapse)")
    print(f" * Sim Arena Pool : {args.envs} Independent RocketSim Arenas (Multithreaded)")
    print("=" * 75)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Zenith] Operating Device: {device}")
    if device.type == "cuda":
        print(f"[Zenith] GPU: {torch.cuda.get_device_name(0)}")

    # 1. Model & Anchor
    policy = KuxirActorCritic().to(device)

    latest_ckpt_path = CKPT_DIR / "latest_checkpoint.pt"
    best_ckpt_path = RUNS_DIR / "best_kuxir.pt"
    export_bot_path = EXPORT_DIR / "kuxir_bot.pt"

    iteration = 0
    total_steps = 0
    all_time_max_pinch = 0.0
    all_time_pinches = 0
    all_time_goals = 0

    if latest_ckpt_path.exists():
        try:
            ckpt = torch.load(str(latest_ckpt_path), map_location=device)
            policy.actor.load_state_dict(ckpt['actor_state'])
            policy.critic.load_state_dict(ckpt['critic_state'])
            iteration = ckpt.get('iteration', 0)
            total_steps = ckpt.get('total_steps', 0)
            all_time_max_pinch = ckpt.get('max_pinch_speed', 0.0)
            all_time_pinches = ckpt.get('total_pinches', 0)
            print(f"[Zenith] RESUMING from checkpoint: Iter {iteration} | Steps {total_steps:,} | Peak {all_time_max_pinch*0.036:.1f} km/h")
        except Exception as e:
            print(f"[Zenith] Could not load checkpoint ({e}), initializing fresh from Nexto Student.")
            policy.load_base_weights(NEXTO_STUDENT_PATH)
    else:
        policy.load_base_weights(NEXTO_STUDENT_PATH)

    anchor_policy = build_anchor_policy(device)
    print("[Zenith] Anchor reference policy initialized and frozen.")

    # 2. Optimizers
    actor_lr = 3e-5
    critic_lr = 1e-4
    actor_optim = torch.optim.AdamW(policy.actor.parameters(), lr=actor_lr, weight_decay=1e-5)
    critic_optim = torch.optim.AdamW(policy.critic.parameters(), lr=critic_lr, weight_decay=1e-5)

    # 3. Simulation Pool
    num_envs = args.envs
    rollout_len = args.rollout  # e.g. 16 * 256 = 4,096 transitions per iteration
    pool = ParallelKuxirEnvPool(num_envs=num_envs, episode_max_steps=220)

    print("\n[Zenith] Starting autonomous training loop...\n")

    try:
        while True:
            iteration += 1
            t_start = time.perf_counter()

            # Buffers
            obs_buf = []
            act_buf = []
            rew_buf = []
            val_buf = []
            logp_buf = []
            done_buf = []

            pinches_this_iter = 0
            goals_this_iter = 0
            max_spd_this_iter = 0.0

            # Gather initial obs
            curr_obs = np.array([
                pool.obs_builder.build_obs(['blue-0'], st, {})['blue-0']
                for st in pool.states
            ], dtype=np.float32)

            policy.eval()

            # -------------------------------------------------------------
            # ROLLOUT PHASE
            # -------------------------------------------------------------
            for step in range(rollout_len):
                obs_t = torch.from_numpy(curr_obs).to(device)

                with torch.no_grad():
                    actions_t, log_probs_t, _, values_t = policy.get_action(obs_t)

                actions_np = actions_t.cpu().numpy()
                log_probs_np = log_probs_t.cpu().numpy()
                values_np = values_t.cpu().numpy()

                next_obs_np, rewards_np, dones_np, infos = pool.step(actions_np)

                obs_buf.append(curr_obs)
                act_buf.append(actions_np)
                rew_buf.append(rewards_np)
                val_buf.append(values_np)
                logp_buf.append(log_probs_np)
                done_buf.append(dones_np)

                # Track events
                for inf in infos:
                    spd = inf['ball_speed']
                    if spd > max_spd_this_iter:
                        max_spd_this_iter = spd
                    if inf['is_pinch']:
                        pinches_this_iter += 1
                    if inf['goal']:
                        goals_this_iter += 1

                curr_obs = next_obs_np
                total_steps += num_envs

            # -------------------------------------------------------------
            # GAE ADVANTAGE ESTIMATION
            # -------------------------------------------------------------
            with torch.no_grad():
                obs_t_last = torch.from_numpy(curr_obs).to(device)
                _, next_val_t = policy(obs_t_last)
                next_vals = next_val_t.cpu().numpy()

            # Convert to arrays: (T, N)
            obs_arr = np.array(obs_buf, dtype=np.float32)      # (T, N, 92)
            act_arr = np.array(act_buf, dtype=np.int64)        # (T, N)
            rew_arr = np.array(rew_buf, dtype=np.float32)      # (T, N)
            val_arr = np.array(val_buf, dtype=np.float32)      # (T, N)
            logp_arr = np.array(logp_buf, dtype=np.float32)    # (T, N)
            done_arr = np.array(done_buf, dtype=bool)          # (T, N)

            adv_arr = np.zeros_like(rew_arr)
            ret_arr = np.zeros_like(rew_arr)

            for env_i in range(num_envs):
                adv, ret = compute_gae(
                    rew_arr[:, env_i], val_arr[:, env_i], done_arr[:, env_i],
                    next_vals[env_i], gamma=0.995, lam=0.95
                )
                adv_arr[:, env_i] = adv
                ret_arr[:, env_i] = ret

            # Flatten across (T * N)
            flat_obs = torch.from_numpy(obs_arr.reshape(-1, 92)).to(device)
            flat_act = torch.from_numpy(act_arr.reshape(-1)).to(device)
            flat_adv = torch.from_numpy(adv_arr.reshape(-1)).to(device)
            flat_ret = torch.from_numpy(ret_arr.reshape(-1)).to(device)
            flat_logp = torch.from_numpy(logp_arr.reshape(-1)).to(device)

            # Normalize advantages
            flat_adv = (flat_adv - flat_adv.mean()) / (flat_adv.std() + 1e-8)

            # -------------------------------------------------------------
            # PPO POLICY & VALUE UPDATE
            # -------------------------------------------------------------
            policy.train()
            batch_size = len(flat_obs)
            minibatch_size = 256
            epochs = 3
            clip_eps = 0.20
            entropy_coef = 0.015
            anchor_coef = 0.04

            actor_losses = []
            critic_losses = []
            kl_divs = []

            for _ in range(epochs):
                perm = torch.randperm(batch_size, device=device)
                for start in range(0, batch_size, minibatch_size):
                    idx = perm[start:start + minibatch_size]

                    b_obs = flat_obs[idx]
                    b_act = flat_act[idx]
                    b_adv = flat_adv[idx]
                    b_ret = flat_ret[idx]
                    b_old_logp = flat_logp[idx]

                    new_logp, entropy, new_val, curr_logits = policy.evaluate_actions(b_obs, b_act)

                    # PPO Surrogate Objective
                    ratio = torch.exp(new_logp - b_old_logp)
                    surr1 = ratio * b_adv
                    surr2 = torch.clamp(ratio, 1.0 - clip_eps, 1.0 + clip_eps) * b_adv
                    policy_loss = -torch.min(surr1, surr2).mean()

                    # Anchor KL Loss (keeps policy grounded in base Nexto driving mechanics)
                    with torch.no_grad():
                        anchor_logits = anchor_policy(b_obs)
                    anchor_kl = F.kl_div(
                        F.log_softmax(curr_logits, dim=-1),
                        F.softmax(anchor_logits, dim=-1),
                        reduction='batchmean'
                    )

                    actor_loss = policy_loss + anchor_coef * anchor_kl - entropy_coef * entropy.mean()

                    actor_optim.zero_grad(set_to_none=True)
                    actor_loss.backward()
                    torch.nn.utils.clip_grad_norm_(policy.actor.parameters(), 0.5)
                    actor_optim.step()

                    # Value MSE Loss
                    val_loss = F.mse_loss(new_val, b_ret)

                    critic_optim.zero_grad(set_to_none=True)
                    val_loss.backward()
                    torch.nn.utils.clip_grad_norm_(policy.critic.parameters(), 0.5)
                    critic_optim.step()

                    actor_losses.append(actor_loss.item())
                    critic_losses.append(val_loss.item())
                    kl_divs.append(anchor_kl.item())

            t_elapsed = time.perf_counter() - t_start
            sps = int(batch_size / max(1e-4, t_elapsed))

            mean_rew = float(rew_arr.mean())
            all_time_pinches += pinches_this_iter
            all_time_goals += goals_this_iter
            if max_spd_this_iter > all_time_max_pinch:
                all_time_max_pinch = max_spd_this_iter

            # -------------------------------------------------------------
            # LOGGING & CHECKPOINT SAVING
            # -------------------------------------------------------------
            kmh = max_spd_this_iter * 0.036
            all_kmh = all_time_max_pinch * 0.036

            print(
                f"[Iter {iteration:4d}] Steps: {total_steps:7,d} | SPS: {sps:5d} | "
                f"Rew/Step: {mean_rew:+.3f} | Pinches: {pinches_this_iter:2d} | "
                f"Max Speed: {max_spd_this_iter:4.0f} uu/s ({kmh:4.1f} km/h) | "
                f"All-Time Peak: {all_kmh:4.1f} km/h | KL: {np.mean(kl_divs):.4f}"
            )

            # Save state
            save_payload = {
                'iteration': iteration,
                'total_steps': total_steps,
                'actor_state': policy.actor.state_dict(),
                'critic_state': policy.critic.state_dict(),
                'max_pinch_speed': all_time_max_pinch,
                'total_pinches': all_time_pinches,
                'mean_reward': mean_rew,
            }

            torch.save(save_payload, str(latest_ckpt_path))

            # New all-time record pinch!
            if max_spd_this_iter >= all_time_max_pinch and max_spd_this_iter > 1800.0:
                torch.save(save_payload, str(best_ckpt_path))
                torch.save(policy.actor.state_dict(), str(export_bot_path))
                print(f"  >>> [NEW RECORD PINCH] {kmh:.1f} km/h ({max_spd_this_iter:.0f} uu/s) -> Saved to best_kuxir.pt & exported to {export_bot_path.name}!")

            if iteration % 10 == 0:
                ckpt_name = CKPT_DIR / f"checkpoint_iter_{iteration:05d}.pt"
                torch.save(save_payload, str(ckpt_name))

            if args.iterations > 0 and iteration >= args.iterations:
                print(f"\n[Zenith] Completed requested {args.iterations} iterations. Exiting.")
                break

    except KeyboardInterrupt:
        print("\n[Zenith] Pause signal received (Ctrl+C). Saving current checkpoint...")
        torch.save(save_payload, str(latest_ckpt_path))
        torch.save(policy.actor.state_dict(), str(export_bot_path))
        print(f"[Zenith] Saved successfully to {latest_ckpt_path.name} and {export_bot_path.name}!")


if __name__ == '__main__':
    main()
