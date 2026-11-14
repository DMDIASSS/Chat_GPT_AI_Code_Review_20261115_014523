"""Experiment 05: Warm-Optimizer Continuation with MechanicsGoalPotential + Targeted WiSE-FT Soup.

1. Screens evolved_40 checkpoints (1212k, 1245k, 1277k, 1310k) and shortlist_42 on dev seeds.
2. Continues directly from checkpoint 1245184 WITH full Adam optimizer state (POLICY_OPTIM.lt &
   CRITIC_OPTIM.lt) and matched gamma=0.999, gae_lambda=0.97 + MechanicsGoalPotential (mech_scale=0.6).
3. Builds targeted WiSE-FT policy soups of the top performing models on the shared frozen trunk.
4. Evaluates top candidates on independent confirmation seeds (seed=810000000, 200 games, 135s).
"""
from __future__ import annotations
import json, math, pathlib, shutil, sys, time
import torch
from scipy.stats import t as student_t

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "NovaForge"))
sys.path.insert(0, str(ROOT))
import rlgym.rocket_league.sim as sim
import run as gf_run
from research import latest_in
from nova.giga_teachers import GigaNetwork
from run_experiment_04_mechanics import evaluate_direct_h2h, build_wise_soup, check_divergence, meshes_dir


def train_warm_continuation(
    run_dir: pathlib.Path,
    arm_name: str,
    source_ckpt: pathlib.Path,
    anchor_dir: pathlib.Path,
    opponent_dir: pathlib.Path,
    delta_steps: int = 131072,
    mechanics_scale: float = 0.6,
    potential_weights: list[float] = [0.28, 0.12, 0.15, 0.05, 0.05],
    actor_lr: float = 3.5e-6,
    anchor_coef: float = 0.20,
    seed: int = 571001,
) -> pathlib.Path:
    arm_dir = run_dir / "branches" / "chronos" / arm_name
    ckpt_dir = arm_dir / "checkpoints"
    start_step = int(source_ckpt.name)
    target_step = start_step + delta_steps

    existing = latest_in(arm_dir)
    if existing is not None and int(existing.name) >= target_step:
        print(f"[chronos/{arm_name}] Already trained to {existing.name}, reusing.", flush=True)
        gf_run.seal_generation(existing, "chronos")
        return existing

    if arm_dir.exists():
        shutil.rmtree(arm_dir)
    init_sub = ckpt_dir / str(start_step)
    init_sub.mkdir(parents=True, exist_ok=True)
    for f in source_ckpt.iterdir():
        if f.is_file():
            shutil.copy2(f, init_sub / f.name)

    stop_file = run_dir / "STOP"
    stop_file.unlink(missing_ok=True)
    metrics_file = arm_dir / "metrics.jsonl"

    recipe = {
        "family": "chronos",
        "hitbox": "breakout",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "games": 128,
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
        "critic_lr": 3e-4,
        "actor_lr": actor_lr,
        "warmup_iterations": 0,
        "freeze_shared": True,
        "anchor_coef": anchor_coef,
        "potential_weights": potential_weights,
        "mechanics_reward": True,
        "mechanics_scale": mechanics_scale,
        "trajectory_seconds": 60.0,
        "meshes": str(meshes_dir()),
        "anchor": str(anchor_dir.resolve()),
        "checkpoints": str(ckpt_dir.resolve()),
        "stop_file": str(stop_file.resolve()),
        "metrics_file": str(metrics_file.resolve()),
        "stop_at": target_step,
        "fixed_rollout": True,
        "opponent": gf_run.descriptor(opponent_dir, "chronos"),
    }
    (arm_dir / "recipe.json").write_text(json.dumps(recipe, indent=2))

    print(
        f"\n=== Warm Continuation chronos/{arm_name} ({start_step} -> {target_step}, "
        f"lr={actor_lr}, anchor={anchor_coef}, mech_scale={mechanics_scale}) ===",
        flush=True,
    )
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0

    ckpt = latest_in(arm_dir)
    if ckpt is None or int(ckpt.name) <= start_step:
        raise RuntimeError(f"Warm continuation {arm_name} did not advance past {start_step}")
    gf_run.seal_generation(ckpt, "chronos")
    gf_run.verify_generation(ckpt)

    rows = [json.loads(line) for line in metrics_file.read_text().splitlines() if line.strip()]
    r_last = rows[-1]
    print(f"[chronos/{arm_name}] Advanced to {ckpt.name} in {elapsed:.1f}s ({delta_steps/elapsed:.0f} SPS)", flush=True)
    print(
        f"  Final iter ({int(r_last.get('Total Iterations',0))}): "
        f"mech_rew={r_last.get('Rewards/mechanics-goal-potential-v1',0):+.5f}, "
        f"critic_loss={r_last.get('Critic Loss',0):.4f}, "
        f"policy_loss={r_last.get('Policy Loss',0):+.5f}, "
        f"anchor_kl={r_last.get('Guard Anchor KL',0):.5f}, "
        f"clip={r_last.get('SB3 Clip Fraction',0):.4f}",
        flush=True,
    )
    return ckpt


if __name__ == "__main__":
    run_dir = ROOT / "runs" / "research03"
    r02_dir = ROOT / "runs" / "research02"
    parent_chronos = run_dir / "parents" / "chronos"

    e40_base = r02_dir / "branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints"
    e40_1212k = e40_base / "policy_versions/1212416"
    e40_1245k = e40_base / "1245184"
    e40_1277k = e40_base / "1277952"
    e40_1310k = e40_base / "1310720"
    shortlist_42 = r02_dir / "shortlist/chronos/edbee138a6c4efb442fadc04aa629cd6eaab72ab6f15035eaea86edaeb8c1edc"
    ckpt_e40_mech_v1 = run_dir / "branches/chronos/chronos_evolved40_mechanics/checkpoints/262144"

    dev_results = {}
    # Load already-computed evolved_40_1245k and chronos_evolved40_mechanics from experiment04
    exp04 = json.loads((run_dir / "experiment04_summary.json").read_text())
    dev_results["evolved_40_1245k"] = exp04["evolved_40_1245k"]
    dev_results["chronos_evolved40_mechanics"] = exp04["chronos_evolved40_mechanics"]

    # 1. Screen the remaining evolved_40 checkpoints & shortlist_42 on the 100-game dev screen
    for label, path in [
        ("evolved_40_1212k", e40_1212k),
        ("evolved_40_1277k", e40_1277k),
        ("evolved_40_1310k", e40_1310k),
        ("shortlist_42", shortlist_42),
    ]:
        gf_run.seal_generation(path, "chronos")
        dev_results[label] = evaluate_direct_h2h(run_dir, "chronos", path, label, pairs=50, seconds=100.0, seed=610000000)

    # 2. Run warm-optimizer MechanicsGoalPotential continuation from 1245184 -> 1376256
    ckpt_mech_v2 = train_warm_continuation(
        run_dir=run_dir,
        arm_name="chronos_evolved40_mech_v2",
        source_ckpt=e40_1245k,
        anchor_dir=parent_chronos,
        opponent_dir=parent_chronos,
        delta_steps=131072,
        mechanics_scale=0.6,
        potential_weights=[0.28, 0.12, 0.15, 0.05, 0.05],
        actor_lr=3.5e-6,
        anchor_coef=0.20,
        seed=571001,
    )
    check_divergence(run_dir, "chronos", ckpt_mech_v2, "chronos_evolved40_mech_v2")
    dev_results["chronos_evolved40_mech_v2"] = evaluate_direct_h2h(
        run_dir, "chronos", ckpt_mech_v2, "chronos_evolved40_mech_v2", pairs=50, seconds=100.0, seed=610000000
    )

    # 3. Build targeted WiSE-FT soups from the top evolved_40 + mechanics checkpoints
    soup_a = build_wise_soup(
        run_dir=run_dir,
        family="chronos",
        soup_name="chronos_soup_elite_a",
        components=[
            (e40_1245k, 0.40),
            (ckpt_e40_mech_v1, 0.30),
            (ckpt_mech_v2, 0.30),
        ],
        template_ckpt=e40_1245k,
    )
    check_divergence(run_dir, "chronos", soup_a, "chronos_soup_elite_a")
    dev_results["chronos_soup_elite_a"] = evaluate_direct_h2h(
        run_dir, "chronos", soup_a, "chronos_soup_elite_a", pairs=50, seconds=100.0, seed=610000000
    )

    soup_b = build_wise_soup(
        run_dir=run_dir,
        family="chronos",
        soup_name="chronos_soup_elite_b",
        components=[
            (parent_chronos, 0.20),
            (e40_1212k, 0.25),
            (e40_1245k, 0.30),
            (ckpt_e40_mech_v1, 0.25),
        ],
        template_ckpt=e40_1245k,
    )
    check_divergence(run_dir, "chronos", soup_b, "chronos_soup_elite_b")
    dev_results["chronos_soup_elite_b"] = evaluate_direct_h2h(
        run_dir, "chronos", soup_b, "chronos_soup_elite_b", pairs=50, seconds=100.0, seed=610000000
    )

    print("\n=== DEV SCREEN RANKING (100 games vs original_chronos, seed=610000000) ===", flush=True)
    ranked = sorted(dev_results.values(), key=lambda r: (r["score_rate"], r["goal_diff"]), reverse=True)
    for r in ranked:
        print(
            f"  {r['arm']:30s}: {r['score_rate']*100:5.2f}% ({r['wins']}W/{r['draws']}D/{r['losses']}L, "
            f"GD={r['goal_diff']:+3d}, CI=[{r['ci_95'][0]*100:.2f}%, {r['ci_95'][1]*100:.2f}%])",
            flush=True,
        )

    # 4. Evaluate top 2 candidates on independent 200-game confirmation seeds (seed=810000000, 135s)
    confirm_results = {}
    for top in ranked[:2]:
        arm = top["arm"]
        ckpt = pathlib.Path(top["checkpoint"])
        confirm_results[arm] = evaluate_direct_h2h(
            run_dir, "chronos", ckpt, f"{arm}_confirm", pairs=100, seconds=135.0, seed=810000000
        )

    (run_dir / "experiment05_summary.json").write_text(
        json.dumps({"dev": dev_results, "confirm": confirm_results}, indent=2)
    )
    print("\nEXPERIMENT 05 SUMMARY SAVED:", run_dir / "experiment05_summary.json", flush=True)
