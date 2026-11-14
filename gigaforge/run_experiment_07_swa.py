"""Experiment 07: Trajectory Continuation + Polyak/SWA Weight Averaging + Panel & H2H Verification.

1. Continues chronos_lowtemp_mech_orig from 327,680 -> 524,288 steps with warm Adam state.
2. Evaluates trajectory checkpoints (262k, 294k, 327k, 458k, 524k) and builds SWA / Polyak
   averages (chronos_lowtemp_swa and chronos_apex_v1).
3. Evaluates Galactus candidates (shortlist_21, possession_1376k, galactus_apex_v1).
4. Runs secondary opponent panel check (vs original_chronos and original_galactus) and
   independent confirmation H2H.
"""
from __future__ import annotations
import json, math, pathlib, shutil, sys, time
import torch
from scipy.stats import t as student_t

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "NovaForge"))
sys.path.insert(0, str(ROOT))
import run as gf_run
from research import latest_in
from run_experiment_04_mechanics import (
    evaluate_direct_h2h,
    build_wise_soup,
    check_divergence,
    meshes_dir,
)


def continue_lowtemp_warm(
    run_dir: pathlib.Path,
    arm_name: str,
    source_ckpt: pathlib.Path,
    anchor_dir: pathlib.Path,
    opponent_dir: pathlib.Path,
    delta_steps: int = 196608,
    policy_temperature: float = 0.25,
    mechanics_scale: float = 0.8,
    potential_weights: list[float] = [0.30, 0.15, 0.30, 0.15, 0.20],
    actor_lr: float = 1.25e-6,
    anchor_coef: float = 0.15,
    seed: int = 771001,
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
        "policy_temperature": policy_temperature,
        "critic_lr": 2.5e-4,
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
        f"\n=== Warm Low-Temp Continuation chronos/{arm_name} ({start_step} -> {target_step}, T={policy_temperature}) ===",
        flush=True,
    )
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0

    ckpt = latest_in(arm_dir)
    if ckpt is None or int(ckpt.name) <= start_step:
        raise RuntimeError(f"Continuation {arm_name} did not advance past {start_step}")
    gf_run.seal_generation(ckpt, "chronos")
    gf_run.verify_generation(ckpt)
    print(f"[chronos/{arm_name}] Advanced to {ckpt.name} in {elapsed:.1f}s ({delta_steps/elapsed:.0f} SPS)", flush=True)
    return ckpt


def evaluate_panel(
    run_dir: pathlib.Path,
    family: str,
    ckpt: pathlib.Path,
    arm_name: str,
    pairs: int = 50,
    seconds: float = 100.0,
    seed: int = 910000000,
) -> dict:
    """Evaluate candidate vs BOTH original_chronos and original_galactus with paired baseline."""
    eval_dir = run_dir / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    out_file = eval_dir / f"panel_{family}_{arm_name}_{pairs*2}x{int(seconds)}s_s{seed}.json"
    parent_c = run_dir / "parents" / "chronos"
    parent_g = run_dir / "parents" / "galactus"
    baseline_dir = parent_c if family == "chronos" else parent_g

    spec = {
        "candidate": gf_run.descriptor(ckpt, family),
        "baseline": gf_run.descriptor(baseline_dir, family),
        "compare_baseline": True,
        "opponents": [
            dict(gf_run.descriptor(parent_c, "chronos"), name="original_chronos"),
            dict(gf_run.descriptor(parent_g, "galactus"), name="original_galactus"),
        ],
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
    print(f"\n=== Secondary Panel Evaluation: {family}/{arm_name} vs [original_chronos, original_galactus] ===", flush=True)
    t0 = time.monotonic()
    gf_run.launch(recipe, log=eval_dir / f"panel_{family}_{arm_name}.log")
    elapsed = time.monotonic() - t0
    res = json.loads(out_file.read_text())
    from research import stats
    st = stats(res["trials"], res["baseline_trials"])
    print(
        f"[{family}/{arm_name}] Panel Delta: {st['delta']*100:+.2f}% | "
        f"by_opponent: {{c: {st['by_opponent']['original_chronos']*100:+.2f}%, g: {st['by_opponent']['original_galactus']*100:+.2f}%}} "
        f"({elapsed:.1f}s)",
        flush=True,
    )
    return st


if __name__ == "__main__":
    run_dir = ROOT / "runs" / "research03"
    r02_dir = ROOT / "runs" / "research02"
    parent_chronos = run_dir / "parents" / "chronos"
    parent_galactus = run_dir / "parents" / "galactus"

    lt_orig_base = run_dir / "branches/chronos/chronos_lowtemp_mech_orig/checkpoints"
    c_262k = lt_orig_base / "262144"
    c_294k = lt_orig_base / "294912"
    c_327k = lt_orig_base / "327680"
    c_mech_v2 = run_dir / "branches/chronos/chronos_evolved40_mech_v2/checkpoints/1376256"

    # 1. Continue chronos_lowtemp_mech_orig from 327,680 -> 524,288
    c_524k = continue_lowtemp_warm(
        run_dir=run_dir,
        arm_name="chronos_lowtemp_mech_cont",
        source_ckpt=c_327k,
        anchor_dir=parent_chronos,
        opponent_dir=parent_chronos,
        delta_steps=196608,
        policy_temperature=0.25,
        mechanics_scale=0.8,
        actor_lr=1.25e-6,
        anchor_coef=0.15,
        seed=771001,
    )
    cont_base = run_dir / "branches/chronos/chronos_lowtemp_mech_cont/checkpoints"
    c_458k = cont_base / "458752"
    c_491k = cont_base / "491520"

    # 2. Build SWA along the lowtemp trajectory (262k, 294k, 327k, 458k, 491k, 524k)
    swa_ckpts = [(p, 1.0) for p in (c_262k, c_294k, c_327k, c_458k, c_491k, c_524k) if p.exists()]
    ckpt_swa = build_wise_soup(
        run_dir=run_dir,
        family="chronos",
        soup_name="chronos_lowtemp_swa",
        components=swa_ckpts,
        template_ckpt=c_327k,
    )
    check_divergence(run_dir, "chronos", ckpt_swa, "chronos_lowtemp_swa")

    # 3. Build chronos_apex_v1 combining c_327k (0.55) + ckpt_swa (0.25) + c_mech_v2 (0.20)
    ckpt_apex = build_wise_soup(
        run_dir=run_dir,
        family="chronos",
        soup_name="chronos_apex_v1",
        components=[
            (c_327k, 0.55),
            (ckpt_swa, 0.25),
            (c_mech_v2, 0.20),
        ],
        template_ckpt=c_327k,
    )
    check_divergence(run_dir, "chronos", ckpt_apex, "chronos_apex_v1")

    dev_results = {}
    for label, p in [
        ("chronos_lt_262k", c_262k),
        ("chronos_lt_294k", c_294k),
        ("chronos_lt_524k", c_524k),
        ("chronos_lowtemp_swa", ckpt_swa),
        ("chronos_apex_v1", ckpt_apex),
    ]:
        gf_run.seal_generation(p, "chronos")
        dev_results[label] = evaluate_direct_h2h(run_dir, "chronos", p, label, pairs=50, seconds=100.0, seed=610000000)

    # 4. Also screen Galactus candidates (shortlist_21, possession_1376k, and galactus_apex_v1)
    g_short21 = r02_dir / "shortlist/galactus/41208372b2f9d93fadebcc04eca9e44abc86eb0b449b51c60941836c78781d0a"
    g_poss1376k = r02_dir / "branches/galactus/possession/f31e15e118f1_0/checkpoints/1376256"
    g_lt = run_dir / "branches/galactus/galactus_lowtemp_mech/checkpoints/262144"
    g_apex = build_wise_soup(
        run_dir=run_dir,
        family="galactus",
        soup_name="galactus_apex_v1",
        components=[
            (parent_galactus, 0.25),
            (g_short21, 0.35),
            (g_poss1376k, 0.25),
            (g_lt, 0.15),
        ],
        template_ckpt=g_lt,
    )
    check_divergence(run_dir, "galactus", g_apex, "galactus_apex_v1")
    for label, p in [
        ("galactus_shortlist_21", g_short21),
        ("galactus_poss_1376k", g_poss1376k),
        ("galactus_apex_v1", g_apex),
    ]:
        gf_run.seal_generation(p, "galactus")
        dev_results[label] = evaluate_direct_h2h(run_dir, "galactus", p, label, pairs=50, seconds=100.0, seed=610000000)

    # 5. Evaluate top Chronos candidates on the 200-game confirmation suite (seed=810000000, 135s)
    confirm_results = {}
    for label, p in [("chronos_lowtemp_swa", ckpt_swa), ("chronos_apex_v1", ckpt_apex)]:
        confirm_results[label] = evaluate_direct_h2h(
            run_dir, "chronos", p, f"{label}_confirm", pairs=100, seconds=135.0, seed=810000000
        )

    # 6. Run Secondary Opponent Panel check on chronos_lowtemp_mech_orig (c_327k) and chronos_apex_v1
    panel_results = {}
    panel_results["chronos_lowtemp_mech_orig"] = evaluate_panel(
        run_dir, "chronos", c_327k, "chronos_lowtemp_mech_orig", pairs=32, seconds=100.0, seed=910000000
    )
    panel_results["chronos_apex_v1"] = evaluate_panel(
        run_dir, "chronos", ckpt_apex, "chronos_apex_v1", pairs=32, seconds=100.0, seed=910000000
    )

    (run_dir / "experiment07_summary.json").write_text(
        json.dumps({"dev": dev_results, "confirm": confirm_results, "panel": panel_results}, indent=2)
    )
    print("\nEXPERIMENT 07 SUMMARY SAVED:", run_dir / "experiment07_summary.json", flush=True)
