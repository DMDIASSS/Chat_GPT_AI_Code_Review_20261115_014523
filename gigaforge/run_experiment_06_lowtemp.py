"""Experiment 06: Low-Temperature Near-Tie Rollout Exploration (T=0.25) + MechanicsGoalPotential.

Eliminates the 90-action softmax tail-sampling noise that caused stochastic rollouts at T=1.0
to lose 68% of goals against deterministic argmax original_chronos and corrupt GAE advantages.
At T=0.25, exploration concentrates exclusively on near-tie top actions (the exact states where
argmax can flip at evaluation time) while executing mechanical sequences (kickoffs, speedflips,
aerials) cleanly on-distribution.
"""
from __future__ import annotations
import json, pathlib, shutil, sys, time
import torch

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "NovaForge"))
sys.path.insert(0, str(ROOT))
import run as gf_run
from research import latest_in
from run_experiment_04_mechanics import (
    sync_native_release,
    evaluate_direct_h2h,
    build_wise_soup,
    check_divergence,
    meshes_dir,
)


def train_lowtemp_arm(
    run_dir: pathlib.Path,
    family: str,
    arm_name: str,
    anchor_dir: pathlib.Path,
    critic_init_dir: pathlib.Path,
    opponent_dir: pathlib.Path,
    potential_weights: list[float],
    policy_temperature: float = 0.25,
    mechanics_scale: float = 0.8,
    total_steps: int = 327680,
    warmup_iters: int = 4,
    actor_lr: float = 1.25e-6,
    anchor_coef: float = 0.15,
    games: int = 128,
    seed: int = 671001,
) -> pathlib.Path:
    arm_dir = run_dir / "branches" / family / arm_name
    ckpt_dir = arm_dir / "checkpoints"
    arm_dir.mkdir(parents=True, exist_ok=True)
    stop_file = run_dir / "STOP"
    stop_file.unlink(missing_ok=True)
    metrics_file = arm_dir / "metrics.jsonl"

    recipe = {
        "family": family,
        "hitbox": "breakout" if family == "chronos" else "octane",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "games": games,
        "simulation_threads": 4,
        "torch_threads": 2,
        "seed": seed,
        "gamma": 0.999,
        "gae_lambda": 0.97,
        "rollout": 8192,
        "batch": 256,
        "minibatch": 256,
        "epochs": 2,
        "clip_range": 0.05,
        "policy_temperature": policy_temperature,
        "critic_lr": 2.5e-4,
        "actor_lr": actor_lr,
        "warmup_iterations": warmup_iters,
        "freeze_shared": True,
        "anchor_coef": anchor_coef,
        "potential_weights": potential_weights,
        "mechanics_reward": True,
        "mechanics_scale": mechanics_scale,
        "trajectory_seconds": 60.0,
        "meshes": str(meshes_dir()),
        "anchor": str(anchor_dir.resolve()),
        "critic_init": str(critic_init_dir.resolve()),
        "checkpoints": str(ckpt_dir.resolve()),
        "stop_file": str(stop_file.resolve()),
        "metrics_file": str(metrics_file.resolve()),
        "stop_at": total_steps,
        "fixed_rollout": True,
        "opponent": gf_run.descriptor(opponent_dir, family),
    }
    (arm_dir / "recipe.json").write_text(json.dumps(recipe, indent=2))

    ckpt = latest_in(arm_dir)
    if ckpt is not None and int(ckpt.name) >= total_steps:
        print(f"[{family}/{arm_name}] Already trained to {ckpt.name}, reusing.", flush=True)
        gf_run.seal_generation(ckpt, family)
        return ckpt

    print(
        f"\n=== Training Low-Temp {family}/{arm_name} (T={policy_temperature}, steps={total_steps}, "
        f"warmup={warmup_iters}, lr={actor_lr}, anchor={anchor_coef}, mech_scale={mechanics_scale}) ===",
        flush=True,
    )
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0

    ckpt = latest_in(arm_dir)
    if ckpt is None:
        raise RuntimeError(f"Training {family}/{arm_name} produced no checkpoint!")
    gf_run.seal_generation(ckpt, family)
    gf_run.verify_generation(ckpt)

    rows = [json.loads(line) for line in metrics_file.read_text().splitlines() if line.strip()]
    warmup_rows = rows[:max(1, warmup_iters)]
    mean_warmup_rew = sum(r.get("Average Step Reward", 0) for r in warmup_rows) / len(warmup_rows)
    r_last = rows[-1]
    print(f"[{family}/{arm_name}] Finished {ckpt.name} steps in {elapsed:.1f}s ({int(ckpt.name)/elapsed:.0f} SPS)", flush=True)
    print(f"  Mean warmup step reward at T={policy_temperature}: {mean_warmup_rew:+.5f} (vs -0.018 at T=1.0!)", flush=True)
    print(
        f"  Final iter ({int(r_last.get('Total Iterations',0))}): "
        f"step_rew={r_last.get('Average Step Reward',0):+.5f}, "
        f"mech_rew={r_last.get('Rewards/mechanics-goal-potential-v1',0):+.5f}, "
        f"critic_loss={r_last.get('Critic Loss',0):.4f}, "
        f"policy_loss={r_last.get('Policy Loss',0):+.5f}, "
        f"anchor_kl={r_last.get('Guard Anchor KL',0):.5f}, "
        f"clip={r_last.get('SB3 Clip Fraction',0):.4f}, "
        f"entropy={r_last.get('Policy Entropy',0):.4f}",
        flush=True,
    )
    return ckpt


if __name__ == "__main__":
    sync_native_release()
    run_dir = ROOT / "runs" / "research03"
    r02_dir = ROOT / "runs" / "research02"

    parent_chronos = run_dir / "parents" / "chronos"
    parent_galactus = run_dir / "parents" / "galactus"
    e40_1245k = r02_dir / "branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/1245184"
    e40_1277k = r02_dir / "branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/1277952"
    e40_critic = r02_dir / "branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/1310720"
    gal_critic = r02_dir / "branches/galactus/possession/f31e15e118f1_0/checkpoints/1376256"
    ckpt_mech_v2 = run_dir / "branches/chronos/chronos_evolved40_mech_v2/checkpoints/1376256"

    results = {"dev": {}, "confirm": {}}

    # 1. Train chronos_lowtemp_mech_orig (from original_chronos at T=0.25)
    ckpt_lt_orig = train_lowtemp_arm(
        run_dir=run_dir,
        family="chronos",
        arm_name="chronos_lowtemp_mech_orig",
        anchor_dir=parent_chronos,
        critic_init_dir=e40_critic,
        opponent_dir=parent_chronos,
        potential_weights=[0.30, 0.15, 0.30, 0.15, 0.20],
        policy_temperature=0.25,
        mechanics_scale=0.8,
        total_steps=327680,
        warmup_iters=4,
        actor_lr=1.25e-6,
        anchor_coef=0.15,
        games=128,
        seed=671001,
    )
    check_divergence(run_dir, "chronos", ckpt_lt_orig, "chronos_lowtemp_mech_orig")
    results["dev"]["chronos_lowtemp_mech_orig"] = evaluate_direct_h2h(
        run_dir, "chronos", ckpt_lt_orig, "chronos_lowtemp_mech_orig", pairs=50, seconds=100.0, seed=610000000
    )

    # 2. Train chronos_lowtemp_mech_e40 (from evolved_40_1245k at T=0.25)
    ckpt_lt_e40 = train_lowtemp_arm(
        run_dir=run_dir,
        family="chronos",
        arm_name="chronos_lowtemp_mech_e40",
        anchor_dir=e40_1245k,
        critic_init_dir=e40_critic,
        opponent_dir=parent_chronos,
        potential_weights=[0.28, 0.12, 0.15, 0.05, 0.05],
        policy_temperature=0.25,
        mechanics_scale=0.6,
        total_steps=262144,
        warmup_iters=3,
        actor_lr=1.0e-6,
        anchor_coef=0.20,
        games=128,
        seed=672002,
    )
    check_divergence(run_dir, "chronos", ckpt_lt_e40, "chronos_lowtemp_mech_e40")
    results["dev"]["chronos_lowtemp_mech_e40"] = evaluate_direct_h2h(
        run_dir, "chronos", ckpt_lt_e40, "chronos_lowtemp_mech_e40", pairs=50, seconds=100.0, seed=610000000
    )

    # 3. Build WiSE-FT soups with the low-temperature models
    soup_lt = build_wise_soup(
        run_dir=run_dir,
        family="chronos",
        soup_name="chronos_lowtemp_wise_soup",
        components=[
            (parent_chronos, 0.25),
            (ckpt_lt_orig, 0.30),
            (ckpt_lt_e40, 0.25),
            (ckpt_mech_v2, 0.20),
        ],
        template_ckpt=ckpt_lt_orig,
    )
    check_divergence(run_dir, "chronos", soup_lt, "chronos_lowtemp_wise_soup")
    results["dev"]["chronos_lowtemp_wise_soup"] = evaluate_direct_h2h(
        run_dir, "chronos", soup_lt, "chronos_lowtemp_wise_soup", pairs=50, seconds=100.0, seed=610000000
    )

    # 4. Train Galactus low-temperature mechanics arm
    ckpt_gal_lt = train_lowtemp_arm(
        run_dir=run_dir,
        family="galactus",
        arm_name="galactus_lowtemp_mech",
        anchor_dir=parent_galactus,
        critic_init_dir=gal_critic,
        opponent_dir=parent_galactus,
        potential_weights=[0.25, 0.18, 0.25, 0.18, 0.28],
        policy_temperature=0.25,
        mechanics_scale=0.8,
        total_steps=262144,
        warmup_iters=4,
        actor_lr=1.0e-6,
        anchor_coef=0.18,
        games=64,
        seed=673003,
    )
    check_divergence(run_dir, "galactus", ckpt_gal_lt, "galactus_lowtemp_mech")
    results["dev"]["galactus_lowtemp_mech"] = evaluate_direct_h2h(
        run_dir, "galactus", ckpt_gal_lt, "galactus_lowtemp_mech", pairs=50, seconds=100.0, seed=610000000
    )

    # 5. Evaluate best Chronos lowtemp candidates on 200-game confirmation suite (seed=810000000, 135s)
    chronos_cands = [
        v for k, v in results["dev"].items() if v["family"] == "chronos"
    ]
    chronos_cands.sort(key=lambda r: (r["score_rate"], r["goal_diff"]), reverse=True)
    best_c = chronos_cands[0]
    results["confirm"][best_c["arm"]] = evaluate_direct_h2h(
        run_dir, "chronos", pathlib.Path(best_c["checkpoint"]), f"{best_c['arm']}_confirm", pairs=100, seconds=135.0, seed=810000000
    )

    if results["dev"]["galactus_lowtemp_mech"]["score_rate"] >= 0.50:
        results["confirm"]["galactus_lowtemp_mech"] = evaluate_direct_h2h(
            run_dir, "galactus", ckpt_gal_lt, "galactus_lowtemp_mech_confirm", pairs=100, seconds=135.0, seed=810000000
        )

    (run_dir / "experiment06_summary.json").write_text(json.dumps(results, indent=2))
    print("\nEXPERIMENT 06 SUMMARY SAVED:", run_dir / "experiment06_summary.json", flush=True)
