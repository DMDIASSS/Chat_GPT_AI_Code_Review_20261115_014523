"""Experiment 03: Matched-control test of Critic-Warmup + Protected-Trunk + Loosened-KL Fine-Tuning.

Compares:
- Arm A (sparse_goal_control): potential_weights=[0,0,0,0,0] (+10/-10 goals only)
- Arm B (attack_velocity_pbrs): potential_weights=[0.30, 0.15, 0.40, 0.15, 0.25]
Both use games=64, warmup_iterations=12 (98,304 steps of critic warmup across full goals),
freeze_shared=True (preventing critic MSE corruption of shared_head), actor_lr=1.5e-5, anchor_coef=0.05.
"""
from __future__ import annotations
import hashlib, json, pathlib, shutil, subprocess, sys, time
import torch

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "NovaForge"))
sys.path.insert(0, str(ROOT))
import rlgym.rocket_league.sim as sim
import run as gf_run
from research import latest_in
from nova.giga_teachers import GigaNetwork


def meshes_dir() -> pathlib.Path:
    return pathlib.Path(sim.__file__).parent / "collision_meshes"


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def setup_run(run_name: str = "research03") -> pathlib.Path:
    run_dir = ROOT / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    parents = run_dir / "parents"
    for fam in ("chronos", "galactus"):
        src = ROOT / "runs" / "research02" / "parents" / fam
        dst = parents / fam
        if not dst.exists():
            dst.mkdir(parents=True, exist_ok=True)
            for f in ("POLICY.lt", "SHARED_HEAD.lt", "README.md", "native.json"):
                if (src / f).exists():
                    shutil.copy2(src / f, dst / f)
        gf_run.verify_generation(dst)
    return run_dir


def train_arm(
    run_dir: pathlib.Path,
    arm_name: str,
    potential_weights: list[float],
    total_steps: int = 393216,
    warmup_iters: int = 12,
    actor_lr: float = 1.5e-5,
    anchor_coef: float = 0.05,
    seed: int = 371001,
) -> pathlib.Path:
    arm_dir = run_dir / "branches" / "chronos" / arm_name
    ckpt_dir = arm_dir / "checkpoints"
    arm_dir.mkdir(parents=True, exist_ok=True)
    stop_file = run_dir / "STOP"
    stop_file.unlink(missing_ok=True)

    parent_chronos = run_dir / "parents" / "chronos"
    metrics_file = arm_dir / "metrics.jsonl"

    recipe = {
        "family": "chronos",
        "hitbox": "breakout",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "games": 64,
        "simulation_threads": 4,
        "torch_threads": 2,
        "seed": seed,
        "gamma": 0.999,
        "rollout": 8192,
        "batch": 256,
        "minibatch": 64,
        "critic_lr": 3e-4,
        "actor_lr": actor_lr,
        "warmup_iterations": warmup_iters,
        "freeze_shared": True,
        "anchor_coef": anchor_coef,
        "potential_weights": potential_weights,
        "trajectory_seconds": 60.0,
        "meshes": str(meshes_dir()),
        "anchor": str(parent_chronos),
        "checkpoints": str(ckpt_dir),
        "stop_file": str(stop_file),
        "metrics_file": str(metrics_file),
        "stop_at": total_steps,
        "fixed_rollout": True,
        "opponent": gf_run.descriptor(parent_chronos, "chronos"),
    }
    recipe_path = arm_dir / "recipe.json"
    recipe_path.write_text(json.dumps(recipe, indent=2))

    ckpt = latest_in(arm_dir)
    if ckpt is not None and int(ckpt.name) >= total_steps:
        print(f"[{arm_name}] Already trained to {ckpt.name}, reusing.")
        gf_run.seal_generation(ckpt, "chronos")
        return ckpt

    print(f"\n=== Training {arm_name} (target={total_steps} steps, warmup={warmup_iters} iters, lr={actor_lr}, anchor={anchor_coef}, weights={potential_weights}) ===", flush=True)
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0

    ckpt = latest_in(arm_dir)
    if ckpt is None:
        raise RuntimeError(f"Training {arm_name} produced no checkpoint!")
    gf_run.seal_generation(ckpt, "chronos")
    gf_run.verify_generation(ckpt)

    rows = [json.loads(line) for line in metrics_file.read_text().splitlines() if line.strip()]
    r_warmup = rows[min(warmup_iters - 1, len(rows) - 1)]
    r_last = rows[-1]
    print(f"[{arm_name}] Finished {ckpt.name} steps in {elapsed:.1f}s ({int(ckpt.name)/elapsed:.0f} SPS)")
    print(f"  End of warmup (iter {int(r_warmup.get('Total Iterations',0))}): goal_frac={r_warmup.get('game/goal_fraction',0):.5f}, critic_loss={r_warmup.get('Critic Loss',0):.4f}")
    print(f"  Final iter ({int(r_last.get('Total Iterations',0))}): step_rew={r_last.get('Average Step Reward',0):+.5f}, goal_frac={r_last.get('game/goal_fraction',0):.5f}, critic_loss={r_last.get('Critic Loss',0):.4f}, policy_loss={r_last.get('Policy Loss',0):+.5f}, anchor_kl={r_last.get('Guard Anchor KL',0):.5f}, clip={r_last.get('SB3 Clip Fraction',0):.4f}")
    return ckpt


def check_divergence(run_dir: pathlib.Path, ckpt: pathlib.Path, label: str):
    orig = GigaNetwork(run_dir / "parents" / "chronos", "chronos")
    cand = GigaNetwork(ckpt, "chronos")
    cases = json.loads((ROOT.parent / "NovaForge/tests/fixtures/giga_reference.json").read_text())["cases"]
    x = torch.tensor([r["reference"]["chronos"]["features"] for r in cases], dtype=torch.float32)
    m = torch.tensor([r["reference"]["chronos"]["mask"] for r in cases], dtype=torch.bool)
    with torch.no_grad():
        lo = orig(x).masked_fill(~m, -1e10)
        lc = cand(x).masked_fill(~m, -1e10)
        agree = (lo.argmax(-1) == lc.argmax(-1)).float().mean().item()
        l2 = sum((p1 - p2).norm().item() for p1, p2 in zip(orig.parameters(), cand.parameters()))
        max_diff = (orig(x) - cand(x)).abs().max().item()
    print(f"[{label}] vs Original Chronos: action_agreement={agree*100:.1f}%, param_L2_diff={l2:.4f}, max_logit_diff={max_diff:.4f}", flush=True)


def evaluate_direct_h2h(
    run_dir: pathlib.Path,
    ckpt: pathlib.Path,
    arm_name: str,
    pairs: int = 50,
    seconds: float = 100.0,
    seed: int = 610000000,
) -> dict:
    eval_dir = run_dir / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    out_file = eval_dir / f"h2h_{arm_name}_{pairs*2}x{int(seconds)}s.json"
    parent_chronos = run_dir / "parents" / "chronos"

    spec = {
        "candidate": gf_run.descriptor(ckpt, "chronos"),
        "baseline": gf_run.descriptor(parent_chronos, "chronos"),
        "compare_baseline": False,
        "opponents": [dict(gf_run.descriptor(parent_chronos, "chronos"), name="original_chronos")],
        "pairs": pairs,
        "seconds": seconds,
        "seed": seed,
        "output": str(out_file),
        "stop_file": str(run_dir / "STOP"),
    }
    recipe = {
        "family": "chronos",
        "hitbox": "breakout",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "torch_threads": 2,
        "meshes": str(meshes_dir()),
        "evaluation": spec,
    }
    print(f"\n=== Direct H2H Evaluation: {arm_name} vs Original Chronos ({pairs*2} games, {seconds}s each, seed={seed}) ===", flush=True)
    t0 = time.monotonic()
    gf_run.launch(recipe, log=eval_dir / f"h2h_{arm_name}.log")
    elapsed = time.monotonic() - t0
    res = json.loads(out_file.read_text())
    trials = res["trials"]
    wins = sum(1 for r in trials if r["outcome"] > 0)
    draws = sum(1 for r in trials if r["outcome"] == 0)
    losses = sum(1 for r in trials if r["outcome"] < 0)
    gf = sum(r["goals_for"] for r in trials)
    ga = sum(r["goals_against"] for r in trials)
    score = (wins + 0.5 * draws) / len(trials)

    # Paired-seed Student-t 95% CI
    from scipy.stats import t as student_t
    import math
    by_seed = {}
    for r in trials:
        by_seed.setdefault(r["seed"], []).append(0.5 * (r["outcome"] + 1.0))
    pair_scores = [sum(v) / len(v) for v in by_seed.values()]
    n = len(pair_scores)
    mean_s = sum(pair_scores) / n
    var_s = sum((x - mean_s) ** 2 for x in pair_scores) / max(1, n - 1)
    se = math.sqrt(var_s / n)
    margin = float(student_t.ppf(0.975, n - 1)) * se
    ci = (mean_s - margin, mean_s + margin)

    summary_dict = {
        "arm": arm_name,
        "games": len(trials),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_rate": score,
        "goals_for": gf,
        "goals_against": ga,
        "ci_95": [ci[0], ci[1]],
        "wall_seconds": elapsed,
    }
    print(f"[{arm_name}] H2H Result ({len(trials)} games in {elapsed:.1f}s): {wins}W / {draws}D / {losses}L | Score: {score*100:.2f}% | Goals: {gf}:{ga} | 95% CI: [{ci[0]*100:.2f}%, {ci[1]*100:.2f}%]", flush=True)
    return summary_dict


if __name__ == "__main__":
    run_dir = setup_run("research03")
    ckpt_sparse = train_arm(
        run_dir,
        arm_name="sparse_goal_control",
        potential_weights=[0.0, 0.0, 0.0, 0.0, 0.0],
        total_steps=393216,
        warmup_iters=12,
        actor_lr=1.5e-5,
        anchor_coef=0.05,
        seed=371001,
    )
    check_divergence(run_dir, ckpt_sparse, "sparse_goal_control")

    ckpt_attack = train_arm(
        run_dir,
        arm_name="attack_velocity_pbrs",
        potential_weights=[0.30, 0.15, 0.40, 0.15, 0.25],
        total_steps=393216,
        warmup_iters=12,
        actor_lr=1.5e-5,
        anchor_coef=0.05,
        seed=371001,
    )
    check_divergence(run_dir, ckpt_attack, "attack_velocity_pbrs")

    res_sparse = evaluate_direct_h2h(run_dir, ckpt_sparse, "sparse_goal_control", pairs=50, seconds=100.0, seed=610000000)
    res_attack = evaluate_direct_h2h(run_dir, ckpt_attack, "attack_velocity_pbrs", pairs=50, seconds=100.0, seed=610000000)

    (run_dir / "experiment03_summary.json").write_text(json.dumps({"sparse_goal_control": res_sparse, "attack_velocity_pbrs": res_attack}, indent=2))
    print("\nEXPERIMENT 03 SUMMARY SAVED:", run_dir / "experiment03_summary.json", flush=True)
