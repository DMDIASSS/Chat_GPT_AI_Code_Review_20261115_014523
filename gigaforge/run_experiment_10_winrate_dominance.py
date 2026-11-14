"""Research06: Win-Rate Dominance Target RL Training against original_chronos.

Core Philosophy:
1. Target: Score scoreboard dominance (>50% win rate) against original_chronos.
2. Dynamic Rolling Win-Rate Reward (WinRateDominanceGoalPotential):
   - Centered at 50% (0.50).
   - Win rate > 50% up to 100%: amplified goal rewards (+10.0 to +20.0).
   - Win rate < 50% down to 0%: reduced goal rewards (+2.0 to +10.0) and amplified concession penalties (-10.0 to -20.0).
3. Suppress Touch Farming: Dense potential weights reduced by ~70% ([0.12, 0.05, 0.10, 0.08, 0.08]).
4. Relaxed Anchor: anchor_coef = 0.04 (gives the policy freedom to learn counter-strategies against original Chronos).
5. Starting Donor: chronos_ctrl_mech_v1 (524,288 steps), which already scored 52.00% vs Chronos and 57.50% vs Galactus.
6. Training Budget: 524,288 -> 786,432 steps (262,144 steps, 32 PPO iterations).
7. Evaluation Panel: Tested against original_chronos (200g, 135s), original_galactus (100g, 100s), and the 4-bot panel (chronos, galactus, ripple, ducky).
"""
from __future__ import annotations
import copy, hashlib, json, math, os, pathlib, shutil, subprocess, sys, time
import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parent
NOVA = ROOT.parent / "NovaForge"
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(NOVA))

import run as gf_run
from nova.giga_teachers import GigaNetwork
from nova.forge_models import DirectActor, save_actor, check_actor
from nova.forge_export import export_actor_bundle


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def meshes_dir() -> pathlib.Path:
    import rlgym.rocket_league.sim as sim
    return pathlib.Path(sim.__file__).parent / "collision_meshes"


def latest_in(branch_dir: pathlib.Path) -> pathlib.Path | None:
    ckpt_dir = branch_dir / "checkpoints"
    if not ckpt_dir.exists():
        return None
    ckpts = [p for p in ckpt_dir.iterdir() if p.is_dir() and p.name.isdigit() and (p / "COMPLETE").exists()]
    return max(ckpts, key=lambda p: int(p.name)) if ckpts else None


def setup_research06() -> pathlib.Path:
    run = ROOT / "runs" / "research06"
    run.mkdir(parents=True, exist_ok=True)
    parents_dir = run / "parents"
    parents_dir.mkdir(parents=True, exist_ok=True)

    # 1. Original Chronos champion
    orig_chronos = parents_dir / "chronos"
    if not (orig_chronos / "POLICY.lt").exists():
        orig_chronos.mkdir(parents=True, exist_ok=True)
        r05_orig = ROOT / "runs" / "research05" / "parents" / "chronos"
        for fn in ("POLICY.lt", "SHARED_HEAD.lt"):
            shutil.copy2(r05_orig / fn, orig_chronos / fn)

    # 2. Original Galactus champion
    orig_galactus = parents_dir / "galactus"
    if not (orig_galactus / "POLICY.lt").exists():
        orig_galactus.mkdir(parents=True, exist_ok=True)
        r05_gal = ROOT / "runs" / "research05" / "parents" / "galactus"
        for fn in ("POLICY.lt", "SHARED_HEAD.lt"):
            shutil.copy2(r05_gal / fn, orig_galactus / fn)

    print("[Identities Verified for Research06]", flush=True)
    print(f"  original_chronos POLICY.lt = {sha256_file(orig_chronos / 'POLICY.lt')}", flush=True)
    print(f"  original_galactus POLICY.lt = {sha256_file(orig_galactus / 'POLICY.lt')}", flush=True)
    return run


def aggregate_telemetry(trials: list[dict]) -> dict:
    n = len(trials)
    if n == 0:
        return {}
    wins = sum(1 for t in trials if t["outcome"] > 0)
    draws = sum(1 for t in trials if t["outcome"] == 0)
    losses = sum(1 for t in trials if t["outcome"] < 0)
    gf = sum(t.get("goals_for", 0) for t in trials)
    ga = sum(t.get("goals_against", 0) for t in trials)
    fc = sum(t.get("failed_challenges", 0) for t in trials)
    sc = sum(t.get("saves_and_clears", 0) for t in trials)
    atk = sum(t.get("attacking_shots", 0) for t in trials)
    opp_poss = sum(t.get("opp_possession_steps", 0) for t in trials)
    g_shad = sum(t.get("goalside_shadow_steps", 0) for t in trials)
    c_dive = sum(t.get("concede_unreachable_dive", 0) for t in trials)
    c_over = sum(t.get("concede_overcommit_behind_ball", 0) for t in trials)

    score_rate = (wins + 0.5 * draws) / n
    return {
        "games": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_rate": score_rate,
        "goals_for": gf,
        "goals_against": ga,
        "goal_diff": gf - ga,
        "gf_per_game": gf / n,
        "ga_per_game": ga / n,
        "failed_challenges_per_game": fc / n,
        "saves_per_game": sc / n,
        "attacking_shots_per_game": atk / n,
        "goalside_shadow_rate": (g_shad / opp_poss) if opp_poss > 0 else 0.0,
        "concession_forensics": {
            "total_conceded": ga,
            "unreachable_dive": c_dive,
            "overcommit": c_over,
        },
    }


def run_eval_suite(
    run_dir: pathlib.Path,
    candidate_ckpt: pathlib.Path,
    opponent_ckpt: pathlib.Path,
    opponent_family: str,
    opponent_name: str,
    label: str,
    pairs: int = 100,
    seconds: float = 135.0,
    seed: int = 1970000000,
) -> dict:
    eval_dir = run_dir / "evaluations" / label
    eval_dir.mkdir(parents=True, exist_ok=True)
    summary_file = eval_dir / "summary.json"
    if summary_file.exists():
        cached = json.loads(summary_file.read_text(encoding="utf8"))
        print(
            f"[{label} | match (REUSED)] {cached['wins']}W/{cached['draws']}D/{cached['losses']}L "
            f"({cached['score_rate']*100:.2f}%, CI [{cached['ci_95'][0]*100:.2f}%, {cached['ci_95'][1]*100:.2f}%]) | "
            f"Goals {cached['goals_for']}:{cached['goals_against']} ({cached['goal_diff']:+d}) | "
            f"GF/g {cached['gf_per_game']:.2f} | GA/g {cached['ga_per_game']:.2f}",
            flush=True,
        )
        return cached

    spec = {
        "candidate": gf_run.descriptor(candidate_ckpt, "chronos"),
        "compare_baseline": False,
        "scenario_mode": "kickoff",
        "opponents": [dict(gf_run.descriptor(opponent_ckpt, opponent_family), name=opponent_name)],
        "pairs": pairs,
        "seconds": seconds,
        "seed": seed,
        "output": str(eval_dir / "matches.json"),
    }
    eval_recipe = {
        "evaluation": spec,
        "torch_threads": 2,
        "meshes": str(meshes_dir()),
    }
    (eval_dir / "recipe.json").write_text(json.dumps(eval_recipe, indent=2), encoding="utf8")

    t0 = time.monotonic()
    gf_run.launch(eval_recipe, log=eval_dir / "eval.log")
    elapsed = time.monotonic() - t0

    raw = json.loads((eval_dir / "matches.json").read_text(encoding="utf8"))
    records = raw.get("trials", [])
    agg = aggregate_telemetry(records)

    n = agg["games"]
    p = agg["score_rate"]
    se = math.sqrt(max(0.0, p * (1.0 - p) / n))
    ci95 = [float(p - 1.96 * se), float(p + 1.96 * se)]

    agg["ci_95"] = ci95
    agg["wall_seconds"] = elapsed
    agg["candidate_sha256"] = sha256_file(candidate_ckpt / "POLICY.lt")
    agg["opponent_name"] = opponent_name

    summary_file.write_text(json.dumps(agg, indent=2), encoding="utf8")
    print(
        f"[{label} | match] {agg['wins']}W/{agg['draws']}D/{agg['losses']}L "
        f"({agg['score_rate']*100:.2f}%, CI [{ci95[0]*100:.2f}%, {ci95[1]*100:.2f}%]) | "
        f"Goals {agg['goals_for']}:{agg['goals_against']} ({agg['goal_diff']:+d}) | "
        f"GF/g {agg['gf_per_game']:.2f} | GA/g {agg['ga_per_game']:.2f} ({elapsed:.1f}s)",
        flush=True,
    )
    return agg


def run_cross_bot_panel(
    run_dir: pathlib.Path,
    candidate_ckpt: pathlib.Path,
    orig_chronos: pathlib.Path,
    pairs: int = 10,
    seconds: float = 45.0,
    seed: int = 771001,
) -> dict:
    out_file = run_dir / "evaluations" / f"multi_opponent_panel_{pairs*2}x{int(seconds)}s.json"
    if out_file.exists():
        print(f"\n[Multi-Opponent Panel (REUSED)] Loading existing results from {out_file}", flush=True)
        return json.loads(out_file.read_text(encoding="utf8"))

    from nova.chronos import ChronosEnv
    from nova.training import load_config

    print("\n=== Running Multi-Opponent Evaluation Panel (RocketSim) ===", flush=True)
    cfg = load_config(NOVA / "configs/chronos.json")
    cfg["curriculum"]["adaptive"] = False
    cfg["env"].update(episode_seconds=seconds, no_touch_seconds=seconds + 1)

    cand_net = GigaNetwork(candidate_ckpt, "chronos")
    orig_net = GigaNetwork(orig_chronos, "chronos")

    def select_action(net: GigaNetwork, obs: np.ndarray) -> int:
        with torch.inference_mode():
            logits = net(torch.from_numpy(obs[:225])[None, :])[0].numpy()
        return int(np.where(obs[225:] > 0, logits, -np.inf).argmax())

    opponents = ["chronos", "galactus", "ripple", "ducky"]
    panel_results = {"candidate": {}, "original_chronos": {}}

    for opp_name in opponents:
        print(f"  Testing vs {opp_name} ({pairs * 2} games, {seconds}s)...", flush=True)
        for label, net in [("candidate", cand_net), ("original_chronos", orig_net)]:
            wins, draws, losses = 0, 0, 0
            for pair in range(pairs):
                for side in (0, 1):
                    env = ChronosEnv(cfg, opponent=opp_name, scenario="kickoff", side=side)
                    try:
                        obs, _ = env.reset(seed=seed + pair * 100 + side * 10)
                        while True:
                            act_idx = select_action(net, obs)
                            obs, _, terminated, truncated, info = env.step(act_idx)
                            if terminated or truncated:
                                outc = info.get("outcome", 0)
                                if outc > 0:
                                    wins += 1
                                elif outc < 0:
                                    losses += 1
                                else:
                                    draws += 1
                                break
                    finally:
                        env.close()
            total = pairs * 2
            score = (wins + 0.5 * draws) / total
            panel_results[label][opp_name] = {
                "games": total,
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "score": score,
            }
            print(f"    [{label} vs {opp_name}] {wins}W/{draws}D/{losses}L ({score*100:.1f}%)", flush=True)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(panel_results, indent=2), encoding="utf8")
    return panel_results


def create_export_and_watch_scripts(
    run_dir: pathlib.Path,
    candidate_ckpt: pathlib.Path,
    label: str = "chronos_winrate_dominance_v1",
) -> dict:
    export_dir = ROOT / "exports" / "research06"
    export_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build DirectActor and pin candidate
    actor = DirectActor("chronos")
    net = GigaNetwork(candidate_ckpt, "chronos")
    actor.core.load_state_dict(net.state_dict(), strict=True)
    pin_dir = run_dir / "watch_pins" / "chronos" / label
    pin_dir.mkdir(parents=True, exist_ok=True)
    actor_file = pin_dir / "actor.lt"
    save_actor(actor, actor_file, family="chronos", hitbox="breakout")
    for fn in ("POLICY.lt", "SHARED_HEAD.lt"):
        shutil.copy2(candidate_ckpt / fn, pin_dir / fn)

    # 2. Export RLBot v5 bundle
    bundle_path = export_actor_bundle(actor_file, export_dir, label=label)
    print(f"\n[Export Ready] Exported candidate bundle to: {bundle_path}", flush=True)

    # 3. Create watch batch files
    watch_scripts = [
        ("32_WATCH_WINRATE_DOMINANCE_VS_ORIGINAL.bat", "original_chronos"),
        ("33_WATCH_WINRATE_DOMINANCE_VS_GALACTUS.bat", "original_galactus"),
        ("34_WATCH_WINRATE_DOMINANCE_VS_RIPPLE.bat", "ripple"),
        ("35_WATCH_WINRATE_DOMINANCE_VS_DUCKY.bat", "ducky"),
    ]
    for bat_name, opp in watch_scripts:
        bat_path = ROOT / bat_name
        bat_content = (
            f"@echo off\r\n"
            f"setlocal\r\n"
            f"cd /d %~dp0\r\n"
            f".venv_native\\Scripts\\python.exe watch_custom.py --actor \"{actor_file}\" --opponent {opp} --profile match\r\n"
            f"pause\r\n"
        )
        bat_path.write_text(bat_content, encoding="utf8")
        print(f"Created watch script: {bat_name} (vs {opp})", flush=True)

    return {
        "bundle_path": str(bundle_path),
        "pin_dir": str(pin_dir),
        "actor_sha256": sha256_file(actor_file),
    }


def train_winrate_dominance(
    run_dir: pathlib.Path,
    source_donor: pathlib.Path,
    opponent_ckpt: pathlib.Path,
    start_steps: int = 524288,
    delta_steps: int = 262144,
    seed: int = 991001,
) -> pathlib.Path:
    arm_name = "chronos_winrate_dominance_v1"
    arm_dir = run_dir / "branches" / "chronos" / arm_name
    ckpt_dir = arm_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    stop_file = run_dir / "STOP"
    stop_file.unlink(missing_ok=True)
    metrics_file = arm_dir / "metrics.jsonl"

    target_steps = start_steps + delta_steps
    seed_ckpt = ckpt_dir / str(start_steps)
    if not (seed_ckpt / "COMPLETE").exists():
        seed_ckpt.mkdir(parents=True, exist_ok=True)
        for fn in ("POLICY.lt", "POLICY_OPTIM.lt", "SHARED_HEAD.lt", "SHARED_HEAD_OPTIM.lt", "CRITIC.lt", "CRITIC_OPTIM.lt", "RUNNING_STATS.json"):
            if (source_donor / fn).exists():
                shutil.copy2(source_donor / fn, seed_ckpt / fn)
        rs_path = seed_ckpt / "RUNNING_STATS.json"
        rs = json.loads(rs_path.read_text(encoding="utf8"))
        rs["total_timesteps"] = start_steps
        rs["total_iterations"] = start_steps // 8192
        rs_path.write_text(json.dumps(rs, indent=2), encoding="utf8")
        (seed_ckpt / "COMPLETE").write_text(f"{start_steps}\n", encoding="utf8")
        gf_run.seal_generation(seed_ckpt, "chronos")

    recipe = {
        "family": "chronos",
        "hitbox": "breakout",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "games": 64,
        "simulation_threads": 4,
        "torch_threads": 2,
        "seed": seed,
        "gamma": 0.999,
        "gae_lambda": 0.97,
        "clip_range": 0.04,
        "epochs": 2,
        "rollout": 8192,
        "batch": 256,
        "minibatch": 64,
        "critic_lr": 1.5e-4,
        "actor_lr": 2.5e-6,
        "policy_temperature": 0.25,
        "warmup_iterations": 0,
        "freeze_shared": True,
        "anchor_coef": 0.04,  # Relaxed anchor to allow learning winning moves!
        "potential_weights": [0.12, 0.05, 0.10, 0.08, 0.08],  # Suppress touch farming
        "winrate_dominance_reward": True,
        "win_scale": 2.0,
        "mechanics_reward": False,
        "defensive_mechanics_reward": False,
        "validated_antidive_reward": False,
        "defensive_curriculum_prob": 0.0,
        "trajectory_seconds": 60.0,
        "meshes": str(meshes_dir()),
        "anchor": str(source_donor),
        "checkpoints": str(ckpt_dir),
        "stop_file": str(stop_file),
        "metrics_file": str(metrics_file),
        "stop_at": target_steps,
        "fixed_rollout": True,
        "opponent": gf_run.descriptor(opponent_ckpt, "chronos"),
    }
    (arm_dir / "recipe.json").write_text(json.dumps(recipe, indent=2), encoding="utf8")

    cur = latest_in(arm_dir)
    if cur is not None and int(cur.name) >= target_steps:
        print(f"[{arm_name}] Reusing existing checkpoint {cur.name}", flush=True)
        gf_run.seal_generation(cur, "chronos")
        return cur

    print(
        f"\n=== Training {arm_name} ({start_steps} -> {target_steps}, "
        f"winrate_dominance=True, anchor_coef=0.04, vs original_chronos) ===",
        flush=True,
    )
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0
    cur = latest_in(arm_dir)
    if cur is None:
        raise RuntimeError(f"No checkpoint produced for {arm_name}")
    gf_run.seal_generation(cur, "chronos")

    print(f"[{arm_name}] Training finished in {elapsed:.1f}s -> Checkpoint {cur.name}", flush=True)
    return cur


def main() -> None:
    run = setup_research06()
    orig_chronos = run / "parents" / "chronos"
    orig_galactus = run / "parents" / "galactus"

    # Best existing donor: chronos_ctrl_mech_v1 (524288) which scored 52.00% vs Chronos, 57.50% vs Galactus
    ctrl_donor = ROOT / "runs" / "research04" / "branches" / "chronos" / "chronos_ctrl_mech_v1" / "checkpoints" / "524288"

    # 1. Train candidate with Win-Rate Dominance Target
    treatment_ckpt = train_winrate_dominance(
        run,
        source_donor=ctrl_donor,
        opponent_ckpt=orig_chronos,
        start_steps=524288,
        delta_steps=262144,
        seed=991001,
    )

    # 2. Evaluation Suite vs original_chronos (200 games, 135s, seed 1970000000)
    print("\n--- Evaluating Promotion Match vs original_chronos (200 games, 135s) ---", flush=True)
    dev_res = run_eval_suite(
        run, treatment_ckpt, orig_chronos, "chronos", "original_chronos",
        label="chronos_winrate_dominance_vs_original_chronos", pairs=100, seconds=135.0, seed=1970000000
    )

    # 3. Evaluation Suite vs original_galactus (100 games, 100s, seed 1990000000)
    print("\n--- Evaluating Secondary Panel vs original_galactus (100 games, 100s) ---", flush=True)
    gal_res = run_eval_suite(
        run, treatment_ckpt, orig_galactus, "galactus", "original_galactus",
        label="chronos_winrate_dominance_vs_galactus", pairs=50, seconds=100.0, seed=1990000000
    )

    # 4. Multi-Opponent Panel in RocketSim (chronos, galactus, ripple, ducky)
    panel_res = run_cross_bot_panel(run, treatment_ckpt, orig_chronos, pairs=10, seconds=45.0, seed=771001)

    # 5. Export and watch scripts
    export_info = create_export_and_watch_scripts(run, treatment_ckpt)

    # 6. Summary Report
    summary = {
        "status": "COMPLETED",
        "experiment": "research06_winrate_dominance",
        "objective": "Target >50% win rate against original_chronos with dynamic winrate-scaled rewards",
        "model_identities": {
            "original_chronos": {
                "POLICY_sha256": sha256_file(orig_chronos / "POLICY.lt"),
                "SHARED_HEAD_sha256": sha256_file(orig_chronos / "SHARED_HEAD.lt"),
            },
            "candidate": {
                "checkpoint": str(treatment_ckpt),
                "POLICY_sha256": sha256_file(treatment_ckpt / "POLICY.lt"),
                "SHARED_HEAD_sha256": sha256_file(treatment_ckpt / "SHARED_HEAD.lt"),
            },
        },
        "evaluation_vs_original_chronos_200g_135s": dev_res,
        "evaluation_vs_galactus_100g_100s": gal_res,
        "multi_opponent_panel": panel_res,
        "export_info": export_info,
    }
    report_file = run / "research06_summary.json"
    report_file.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(f"\n[RESEARCH06 COMPLETE] Final report written to {report_file}", flush=True)


if __name__ == "__main__":
    main()
