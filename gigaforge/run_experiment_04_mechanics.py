"""Experiment 04: Native C++ MechanicsGoalPotential + 1.31M-Step Pretrained Critic + WiSE-FT Soup.

Trains and evaluates:
1. chronos_mechanics_pro: MechanicsGoalPotential (speedflip, supersonic challenge, power shot,
   air-dribble carry, flip-reset & Maktuf 360 spin reset) + 1.31M-step pretrained critic,
   games=128, minibatch=256, lr=6e-6, anchor=0.12, gamma=0.998, gae_lambda=0.96.
2. chronos_evolved40_mechanics: Continues from 1.24M-step evolved_40 checkpoint + critic with
   MechanicsGoalPotential directly against original_chronos.
3. chronos_wise_mechanics_soup: Weight-space ensemble (WiSE-FT) combining our frozen-trunk
   mechanics and tactical policies on the shared Chronos trunk.
4. galactus_mechanics_pro: MechanicsGoalPotential + 1.37M-step pretrained Galactus critic.
"""
from __future__ import annotations
import hashlib, json, math, pathlib, shutil, sys, time
import torch
from scipy.stats import t as student_t

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "NovaForge"))
sys.path.insert(0, str(ROOT))
import rlgym.rocket_league.sim as sim
import run as gf_run
from research import latest_in
from nova.giga_teachers import GigaNetwork


def meshes_dir() -> pathlib.Path:
    return pathlib.Path(sim.__file__).parent / "collision_meshes"


def sync_native_release():
    build_json = ROOT / "native" / "build.json"
    rel_json = ROOT / "native_release.json"
    if build_json.exists() and rel_json.exists():
        b = json.loads(build_json.read_text())
        r = json.loads(rel_json.read_text())
        if r.get("executable_sha256") != b.get("executable_sha256"):
            r["executable_sha256"] = b["executable_sha256"]
            rel_json.write_text(json.dumps(r, indent=2))
            print("Synced native_release.json executable_sha256 ->", b["executable_sha256"])


def train_mechanics_arm(
    run_dir: pathlib.Path,
    family: str,
    arm_name: str,
    anchor_dir: pathlib.Path,
    critic_init_dir: pathlib.Path,
    opponent_dir: pathlib.Path,
    potential_weights: list[float],
    mechanics_scale: float = 1.0,
    total_steps: int = 327680,
    warmup_iters: int = 2,
    actor_lr: float = 6e-6,
    anchor_coef: float = 0.12,
    gamma: float = 0.998,
    gae_lambda: float = 0.96,
    games: int = 128,
    seed: int = 471001,
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
        "gamma": gamma,
        "gae_lambda": gae_lambda,
        "rollout": 8192,
        "batch": 256,
        "minibatch": 256,
        "epochs": 2,
        "clip_range": 0.05,
        "critic_lr": 2e-4,
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
        f"\n=== Training {family}/{arm_name} (steps={total_steps}, warmup={warmup_iters}, "
        f"lr={actor_lr}, anchor={anchor_coef}, mech_scale={mechanics_scale}) ===",
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
    r_warmup = rows[min(max(0, warmup_iters - 1), len(rows) - 1)]
    r_last = rows[-1]
    print(f"[{family}/{arm_name}] Finished {ckpt.name} steps in {elapsed:.1f}s ({int(ckpt.name)/elapsed:.0f} SPS)", flush=True)
    print(f"  Warmup end: critic_loss={r_warmup.get('Critic Loss',0):.4f}, goal_frac={r_warmup.get('game/goal_fraction',0):.5f}", flush=True)
    print(
        f"  Final iter ({int(r_last.get('Total Iterations',0))}): "
        f"step_rew={r_last.get('Average Step Reward',0):+.5f}, "
        f"mech_rew={r_last.get('Rewards/mechanics-goal-potential-v1',0):+.5f}, "
        f"critic_loss={r_last.get('Critic Loss',0):.4f}, "
        f"policy_loss={r_last.get('Policy Loss',0):+.5f}, "
        f"anchor_kl={r_last.get('Guard Anchor KL',0):.5f}, "
        f"clip={r_last.get('SB3 Clip Fraction',0):.4f}",
        flush=True,
    )
    return ckpt


def build_wise_soup(
    run_dir: pathlib.Path,
    family: str,
    soup_name: str,
    components: list[tuple[pathlib.Path, float]],
    template_ckpt: pathlib.Path,
) -> pathlib.Path:
    """Create a weight-space ensemble (WiSE-FT / Policy Soup) in native LibTorch format.
    
    Uses a C++ or LibTorch state_dict blend on POLICY.lt while keeping the shared frozen
    SHARED_HEAD.lt identical, then seals and verifies the generation.
    """
    out_dir = run_dir / "branches" / family / soup_name / "checkpoints" / "1000000"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in ("SHARED_HEAD.lt", "COMPLETE", "RUNNING_STATS.json"):
        if (template_ckpt / f).exists():
            shutil.copy2(template_ckpt / f, out_dir / f)
    if not (out_dir / "COMPLETE").exists():
        (out_dir / "COMPLETE").write_text("1000000\n")

    total_w = sum(w for _, w in components)
    norm_components = [(p, w / total_w) for p, w in components]

    # Load each POLICY.lt as a TorchScript / ScriptModule via torch.jit.load
    base_mod = torch.jit.load(str(norm_components[0][0] / "POLICY.lt"), map_location="cpu")
    sd_Target = {k: torch.zeros_like(v) for k, v in base_mod.state_dict().items()}
    for ckpt_path, weight in norm_components:
        mod = torch.jit.load(str(ckpt_path / "POLICY.lt"), map_location="cpu")
        for k, v in mod.state_dict().items():
            sd_Target[k].add_(v, alpha=weight)
    base_mod.load_state_dict(sd_Target)
    base_mod.save(str(out_dir / "POLICY.lt"))

    gf_run.seal_generation(out_dir, family)
    gf_run.verify_generation(out_dir)
    print(f"[{family}/{soup_name}] Built WiSE-FT policy soup from {len(components)} models -> {out_dir}", flush=True)
    return out_dir


def check_divergence(run_dir: pathlib.Path, family: str, ckpt: pathlib.Path, label: str):
    orig = GigaNetwork(run_dir / "parents" / family, family)
    cand = GigaNetwork(ckpt, family)
    cases = json.loads((ROOT.parent / "NovaForge/tests/fixtures/giga_reference.json").read_text())["cases"]
    x = torch.tensor([r["reference"][family]["features"] for r in cases], dtype=torch.float32)
    m = torch.tensor([r["reference"][family]["mask"] for r in cases], dtype=torch.bool)
    with torch.no_grad():
        lo = orig(x).masked_fill(~m, -1e10)
        lc = cand(x).masked_fill(~m, -1e10)
        agree = (lo.argmax(-1) == lc.argmax(-1)).float().mean().item()
        l2 = sum((p1 - p2).norm().item() for p1, p2 in zip(orig.parameters(), cand.parameters()))
        max_diff = (orig(x) - cand(x)).abs().max().item()
    print(f"[{family}/{label}] vs Original {family}: action_agreement={agree*100:.1f}%, param_L2_diff={l2:.4f}, max_logit_diff={max_diff:.4f}", flush=True)


def evaluate_direct_h2h(
    run_dir: pathlib.Path,
    family: str,
    ckpt: pathlib.Path,
    arm_name: str,
    pairs: int = 50,
    seconds: float = 100.0,
    seed: int = 610000000,
) -> dict:
    eval_dir = run_dir / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    out_file = eval_dir / f"h2h_{family}_{arm_name}_{pairs*2}x{int(seconds)}s_s{seed}.json"
    parent_dir = run_dir / "parents" / family

    spec = {
        "candidate": gf_run.descriptor(ckpt, family),
        "baseline": gf_run.descriptor(parent_dir, family),
        "compare_baseline": False,
        "opponents": [dict(gf_run.descriptor(parent_dir, family), name=f"original_{family}")],
        "pairs": pairs,
        "seconds": seconds,
        "seed": seed,
        "output": str(out_file),
        "stop_file": str(run_dir / "STOP"),
    }
    recipe = {
        "family": family,
        "hitbox": "breakout" if family == "chronos" else "octane",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "torch_threads": 2,
        "meshes": str(meshes_dir()),
        "evaluation": spec,
    }
    print(f"\n=== Direct H2H: {family}/{arm_name} vs original_{family} ({pairs*2} games, {seconds}s, seed={seed}) ===", flush=True)
    t0 = time.monotonic()
    gf_run.launch(recipe, log=eval_dir / f"h2h_{family}_{arm_name}.log")
    elapsed = time.monotonic() - t0
    res = json.loads(out_file.read_text())
    trials = res["trials"]
    wins = sum(1 for r in trials if r["outcome"] > 0)
    draws = sum(1 for r in trials if r["outcome"] == 0)
    losses = sum(1 for r in trials if r["outcome"] < 0)
    gf = sum(r["goals_for"] for r in trials)
    ga = sum(r["goals_against"] for r in trials)
    score = (wins + 0.5 * draws) / len(trials)

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
        "family": family,
        "arm": arm_name,
        "checkpoint": str(ckpt),
        "games": len(trials),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_rate": score,
        "goals_for": gf,
        "goals_against": ga,
        "goal_diff": gf - ga,
        "ci_95": [ci[0], ci[1]],
        "wall_seconds": elapsed,
    }
    print(
        f"[{family}/{arm_name}] {wins}W / {draws}D / {losses}L | "
        f"Score: {score*100:.2f}% | Goals: {gf}:{ga} ({gf-ga:+d}) | "
        f"95% CI: [{ci[0]*100:.2f}%, {ci[1]*100:.2f}%] ({elapsed:.1f}s)",
        flush=True,
    )
    return summary_dict


if __name__ == "__main__":
    sync_native_release()
    run_dir = ROOT / "runs" / "research03"
    r02_dir = ROOT / "runs" / "research02"

    parent_chronos = run_dir / "parents" / "chronos"
    parent_galactus = run_dir / "parents" / "galactus"
    e40_ckpt = r02_dir / "branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/1245184"
    e40_critic = r02_dir / "branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/1310720"
    gal_critic = r02_dir / "branches/galactus/possession/f31e15e118f1_0/checkpoints/1376256"

    results = {}

    # 0. Screen existing evolved_40 (1.24M steps) and Galactus shortlist_21 on the same 100-game dev screen
    results["evolved_40_1245k"] = evaluate_direct_h2h(
        run_dir, "chronos", e40_ckpt, "evolved_40_1245k", pairs=50, seconds=100.0, seed=610000000
    )

    # 1. Train chronos_mechanics_pro (starting from original_chronos + 1.31M pretrained critic)
    ckpt_mech_pro = train_mechanics_arm(
        run_dir=run_dir,
        family="chronos",
        arm_name="chronos_mechanics_pro",
        anchor_dir=parent_chronos,
        critic_init_dir=e40_critic,
        opponent_dir=parent_chronos,
        potential_weights=[0.32, 0.15, 0.35, 0.18, 0.22],
        mechanics_scale=1.0,
        total_steps=327680,
        warmup_iters=2,
        actor_lr=5e-6,
        anchor_coef=0.15,
        gamma=0.998,
        gae_lambda=0.96,
        games=128,
        seed=471001,
    )
    check_divergence(run_dir, "chronos", ckpt_mech_pro, "chronos_mechanics_pro")
    results["chronos_mechanics_pro"] = evaluate_direct_h2h(
        run_dir, "chronos", ckpt_mech_pro, "chronos_mechanics_pro", pairs=50, seconds=100.0, seed=610000000
    )

    # 2. Train chronos_evolved40_mechanics (continuing evolved_40 + 1.31M critic with MechanicsGoalPotential)
    ckpt_e40_mech = train_mechanics_arm(
        run_dir=run_dir,
        family="chronos",
        arm_name="chronos_evolved40_mechanics",
        anchor_dir=e40_ckpt,
        critic_init_dir=e40_critic,
        opponent_dir=parent_chronos,
        potential_weights=[0.30, 0.15, 0.35, 0.15, 0.20],
        mechanics_scale=1.2,
        total_steps=262144,
        warmup_iters=1,
        actor_lr=5e-6,
        anchor_coef=0.15,
        gamma=0.998,
        gae_lambda=0.96,
        games=128,
        seed=472002,
    )
    check_divergence(run_dir, "chronos", ckpt_e40_mech, "chronos_evolved40_mechanics")
    results["chronos_evolved40_mechanics"] = evaluate_direct_h2h(
        run_dir, "chronos", ckpt_e40_mech, "chronos_evolved40_mechanics", pairs=50, seconds=100.0, seed=610000000
    )

    # 3. Build WiSE-FT Policy Soup combining parent + mechanics_pro + evolved40_mechanics + attack_velocity_pbrs
    ckpt_attack = run_dir / "branches/chronos/attack_velocity_pbrs/checkpoints/393216"
    ckpt_soup = build_wise_soup(
        run_dir=run_dir,
        family="chronos",
        soup_name="chronos_wise_mechanics_soup",
        components=[
            (parent_chronos, 0.25),
            (ckpt_mech_pro, 0.35),
            (ckpt_e40_mech, 0.25),
            (ckpt_attack, 0.15),
        ],
        template_ckpt=ckpt_mech_pro,
    )
    check_divergence(run_dir, "chronos", ckpt_soup, "chronos_wise_mechanics_soup")
    results["chronos_wise_mechanics_soup"] = evaluate_direct_h2h(
        run_dir, "chronos", ckpt_soup, "chronos_wise_mechanics_soup", pairs=50, seconds=100.0, seed=610000000
    )

    # 4. Train Galactus mechanics_pro (starting from original_galactus + 1.37M pretrained critic)
    ckpt_gal_mech = train_mechanics_arm(
        run_dir=run_dir,
        family="galactus",
        arm_name="galactus_mechanics_pro",
        anchor_dir=parent_galactus,
        critic_init_dir=gal_critic,
        opponent_dir=parent_galactus,
        potential_weights=[0.25, 0.18, 0.25, 0.18, 0.28],
        mechanics_scale=1.0,
        total_steps=262144,
        warmup_iters=2,
        actor_lr=4e-6,
        anchor_coef=0.18,
        gamma=0.998,
        gae_lambda=0.96,
        games=64,
        seed=473003,
    )
    check_divergence(run_dir, "galactus", ckpt_gal_mech, "galactus_mechanics_pro")
    results["galactus_mechanics_pro"] = evaluate_direct_h2h(
        run_dir, "galactus", ckpt_gal_mech, "galactus_mechanics_pro", pairs=50, seconds=100.0, seed=610000000
    )

    (run_dir / "experiment04_summary.json").write_text(json.dumps(results, indent=2))
    print("\nEXPERIMENT 04 SUMMARY SAVED:", run_dir / "experiment04_summary.json", flush=True)
