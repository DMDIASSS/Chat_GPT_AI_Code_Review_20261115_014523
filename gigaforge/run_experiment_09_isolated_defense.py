"""Research05: Isolated Validated Anti-Dive Defensive Intervention & Multi-Opponent Evaluation Panel.

Key Constraints Enforced:
1. Re-verified starting candidate: chronos_lowtemp_swa (research03 Trial 1).
2. Single isolated intervention in mechanics reward (ValidatedAntiDiveMechanicsGoalPotential / v3):
   - b[0..4] (including distance potential b[1]) are 100% UNCHANGED.
   - 0.0% false positives on legitimate retreats and recoveries (proven in validate_saved_situations.py).
   - Upfield dive velocity toward ball away from net is clamped; true unreachable diving flips penalized.
3. 0% curriculum change: 100% full-match standard kickoffs (matching chronos_ctrl_mech_v1 control).
4. No weight averaging (no SWA) in the isolated comparison: compare raw 524,288-step checkpoint directly.
5. All evaluation seeds disjoint from all prior history (verified against native01 and research01-04).
6. Multi-opponent panel testing against:
   - original_chronos
   - original_galactus
   - ripple (ONNX policy v1.1)
   - ducky (TorchScript policy)
7. Champion remains original_chronos. All hashes and statistics read directly from artifacts.
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
from nova.core import sha256
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


def setup_research05() -> pathlib.Path:
    run = ROOT / "runs" / "research05"
    r04 = ROOT / "runs" / "research04"
    r03 = ROOT / "runs" / "research03"
    run.mkdir(parents=True, exist_ok=True)
    for f in ("config.json", "tuning.json"):
        if (r04 / f).exists() and not (run / f).exists():
            shutil.copy2(r04 / f, run / f)
        elif (r03 / f).exists() and not (run / f).exists():
            shutil.copy2(r03 / f, run / f)

    # 1. Preserve original_chronos and original_galactus in parents/
    for fam in ("chronos", "galactus"):
        src = r04 / "parents" / fam
        dst = run / "parents" / fam
        dst.mkdir(parents=True, exist_ok=True)
        for fn in ("POLICY.lt", "SHARED_HEAD.lt", "README.md", "LICENSE"):
            if (src / fn).exists() and not (dst / fn).exists():
                shutil.copy2(src / fn, dst / fn)
        gf_run.seal_generation(dst, fam)
        gf_run.verify_generation(dst)

    # 2. Preserve exact chronos_lowtemp_swa preview in parents/chronos_lowtemp_swa
    swa_src = r03 / "branches" / "chronos" / "chronos_lowtemp_swa" / "checkpoints" / "1000000"
    swa_dst = run / "parents" / "chronos_lowtemp_swa"
    swa_dst.mkdir(parents=True, exist_ok=True)
    for fn in swa_src.iterdir():
        if fn.is_file() and not (swa_dst / fn.name).exists():
            shutil.copy2(fn, swa_dst / fn.name)
    gf_run.seal_generation(swa_dst, "chronos")
    gf_run.verify_generation(swa_dst)

    # 3. Champion pointer strictly points to original_chronos
    champions = run / "champions"
    champions.mkdir(parents=True, exist_ok=True)
    (champions / "chronos.json").write_text(
        json.dumps({"path": "parents/chronos", "family": "chronos", "role": "retained champion"}, indent=2),
        encoding="utf8",
    )
    (champions / "galactus.json").write_text(
        json.dumps({"path": "parents/galactus", "family": "galactus", "role": "retained champion"}, indent=2),
        encoding="utf8",
    )

    print(
        f"[Identities Verified]\n"
        f"  original_chronos POLICY.lt   = {sha256_file(run / 'parents/chronos/POLICY.lt')}\n"
        f"  chronos_lowtemp_swa POLICY.lt = {sha256_file(swa_dst / 'POLICY.lt')}",
        flush=True,
    )
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
    c_boost = sum(t.get("concede_boost_detour", 0) for t in trials)
    c_lane = sum(t.get("concede_not_goalside_lane", 0) for t in trials)
    c_rec = sum(t.get("concede_slow_recovery", 0) for t in trials)

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
            "unreachable_dive_pct": (c_dive / ga) if ga > 0 else 0.0,
            "overcommit": c_over,
            "boost_detour": c_boost,
            "not_goalside_lane": c_lane,
            "slow_recovery": c_rec,
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
    seed: int = 1950000000,
    scenario_mode: str = "match",
) -> dict:
    eval_dir = run_dir / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    out_file = eval_dir / f"{label}_{scenario_mode}_{pairs*2}x{int(seconds)}s_s{seed}.json"
    if out_file.exists():
        try:
            raw = json.loads(out_file.read_text(encoding="utf8"))
            if len(raw.get("trials", [])) == pairs * 2:
                from head_to_head import summary as h2h_summary
                s = h2h_summary(raw["trials"])
                tel = aggregate_telemetry(raw["trials"])
                tel["ci_95"] = s["score_interval_95"]
                tel["wall_seconds"] = 0.0
                cf = tel["concession_forensics"]
                print(
                    f"[{label} | {scenario_mode} (REUSED)] {tel['wins']}W/{tel['draws']}D/{tel['losses']}L "
                    f"({tel['score_rate']*100:.2f}%, CI [{tel['ci_95'][0]*100:.2f}%, {tel['ci_95'][1]*100:.2f}%]) | "
                    f"Goals {tel['goals_for']}:{tel['goals_against']} ({tel['goal_diff']:+d}) | "
                    f"GF/g {tel['gf_per_game']:.2f} | GA/g {tel['ga_per_game']:.2f} | "
                    f"Saves/g {tel['saves_per_game']:.2f} | FailedChal/g {tel['failed_challenges_per_game']:.2f} | "
                    f"AtkShots/g {tel['attacking_shots_per_game']:.2f} | "
                    f"ConcedeDive {cf['unreachable_dive']}/{cf['total_conceded']} ({cf['unreachable_dive_pct']*100:.1f}%)",
                    flush=True,
                )
                return tel
        except Exception:
            pass
    spec = {
        "candidate": gf_run.descriptor(candidate_ckpt, "chronos"),
        "compare_baseline": False,
        "scenario_mode": scenario_mode,
        "opponents": [dict(gf_run.descriptor(opponent_ckpt, opponent_family), name=opponent_name)],
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
    t0 = time.monotonic()
    gf_run.launch(recipe, log=eval_dir / f"{label}_{scenario_mode}_s{seed}.log")
    elapsed = time.monotonic() - t0
    raw = json.loads(out_file.read_text(encoding="utf8"))
    from head_to_head import summary as h2h_summary
    s = h2h_summary(raw["trials"])
    tel = aggregate_telemetry(raw["trials"])
    tel["ci_95"] = s["score_interval_95"]
    tel["wall_seconds"] = elapsed
    cf = tel["concession_forensics"]
    print(
        f"[{label} | {scenario_mode}] {tel['wins']}W/{tel['draws']}D/{tel['losses']}L "
        f"({tel['score_rate']*100:.2f}%, CI [{tel['ci_95'][0]*100:.2f}%, {tel['ci_95'][1]*100:.2f}%]) | "
        f"Goals {tel['goals_for']}:{tel['goals_against']} ({tel['goal_diff']:+d}) | "
        f"GF/g {tel['gf_per_game']:.2f} | GA/g {tel['ga_per_game']:.2f} | "
        f"Saves/g {tel['saves_per_game']:.2f} | FailedChal/g {tel['failed_challenges_per_game']:.2f} | "
        f"AtkShots/g {tel['attacking_shots_per_game']:.2f} | "
        f"ConcedeDive {cf['unreachable_dive']}/{cf['total_conceded']} ({cf['unreachable_dive_pct']*100:.1f}%) "
        f"({elapsed:.1f}s)",
        flush=True,
    )
    return tel


def train_isolated_antidive(
    run_dir: pathlib.Path,
    source_swa: pathlib.Path,
    critic_donor: pathlib.Path,
    opponent_ckpt: pathlib.Path,
    delta_steps: int = 196608,
    mechanics_scale: float = 0.85,
    defense_scale: float = 1.0,
    policy_temperature: float = 0.25,
    actor_lr: float = 1.25e-6,
    anchor_coef: float = 0.18,
    seed: int = 881001,
) -> pathlib.Path:
    """Train isolated anti-dive intervention:
    - 0.0% curriculum change: 100% full match kickoffs
    - validated_antidive_reward = True (v3)
    - NO weight averaging (evaluating raw 524,288 checkpoint)
    """
    arm_name = "chronos_antidive_isolated_v3"
    arm_dir = run_dir / "branches" / "chronos" / arm_name
    ckpt_dir = arm_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    stop_file = run_dir / "STOP"
    stop_file.unlink(missing_ok=True)
    metrics_file = arm_dir / "metrics.jsonl"

    start_steps = 327680
    target_steps = start_steps + delta_steps
    seed_ckpt = ckpt_dir / str(start_steps)
    if not (seed_ckpt / "COMPLETE").exists():
        seed_ckpt.mkdir(parents=True, exist_ok=True)
        for fn in ("POLICY_OPTIM.lt", "SHARED_HEAD_OPTIM.lt", "CRITIC.lt", "CRITIC_OPTIM.lt", "RUNNING_STATS.json"):
            if (critic_donor / fn).exists():
                shutil.copy2(critic_donor / fn, seed_ckpt / fn)
        for fn in ("POLICY.lt", "SHARED_HEAD.lt"):
            shutil.copy2(source_swa / fn, seed_ckpt / fn)
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
        "actor_lr": actor_lr,
        "policy_temperature": policy_temperature,
        "warmup_iterations": 0,
        "freeze_shared": True,
        "anchor_coef": anchor_coef,
        "potential_weights": [0.35, 0.15, 0.30, 0.22, 0.22],
        "mechanics_reward": False,
        "defensive_mechanics_reward": False,
        "validated_antidive_reward": True,
        "mechanics_scale": mechanics_scale,
        "defense_scale": defense_scale,
        "defensive_curriculum_prob": 0.0,  # 0% curriculum change: 100% full match kickoffs!
        "trajectory_seconds": 60.0,
        "meshes": str(meshes_dir()),
        "anchor": str(source_swa),
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
        f"validated_antidive=True, def_curr_prob=0.0, T={policy_temperature}) ===",
        flush=True,
    )
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0
    cur = latest_in(arm_dir)
    if cur is None:
        raise RuntimeError(f"No checkpoint produced for {arm_name}")
    gf_run.seal_generation(cur, "chronos")

    assert sha256_file(cur / "SHARED_HEAD.lt") == sha256_file(source_swa / "SHARED_HEAD.lt"), "SHARED_HEAD changed!"
    rows = [json.loads(line) for line in metrics_file.read_text(encoding="utf8").splitlines() if line.strip()]
    last_r = rows[-1] if rows else {}
    print(
        f"[{arm_name}] Finished in {elapsed:.1f}s -> {cur.name} | "
        f"StepRew={last_r.get('Average Step Reward', 0):.5f} | "
        f"CriticLoss={last_r.get('PPO Critic Loss', 0):.5f} | "
        f"AnchorKL={last_r.get('Guard Anchor KL', 0):.5f}",
        flush=True,
    )
    return cur


def run_cross_bot_panel(
    run_dir: pathlib.Path,
    candidate_ckpt: pathlib.Path,
    orig_chronos: pathlib.Path,
    pairs: int = 10,
    seconds: float = 45.0,
    seed: int = 770001,
) -> dict:
    """Run cross-bot matches against the multi-bot panel in Python RocketSim:
    - original_chronos (Breakout)
    - original_galactus (Octane)
    - ripple (Octane, ONNX policy v1.1)
    - ducky (Octane, TorchScript policy)
    """
    out_file = run_dir / "evaluations" / f"multi_opponent_panel_{pairs*2}x{int(seconds)}s.json"
    if out_file.exists():
        print(f"\n[Multi-Opponent Panel (REUSED)] Loading existing results from {out_file}", flush=True)
        return json.loads(out_file.read_text(encoding="utf8"))

    from nova.chronos import ChronosEnv
    from nova.training import load_config
    from nova.teachers import make_opponent

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
            wins, draws, losses, gf, ga = 0, 0, 0, 0, 0
            for pair in range(pairs):
                for side in (0, 1):
                    env = ChronosEnv(cfg, opponent=opp_name, scenario="kickoff", side=side)
                    try:
                        obs, _ = env.reset(seed=seed + pair * 100 + side * 10)
                        while True:
                            act_idx = select_action(net, obs)
                            obs, _, terminated, truncated, info = env.step(act_idx)
                            if terminated or truncated:
                                outc = info["outcome"]
                                if outc > 0:
                                    wins += 1
                                elif outc < 0:
                                    losses += 1
                                else:
                                    draws += 1
                                gf += int(info.get("goals_for", 0))
                                ga += int(info.get("goals_against", 0))
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
                "goals_for": gf,
                "goals_against": ga,
                "goal_diff": gf - ga,
            }
            print(
                f"    [{label} vs {opp_name}] {wins}W/{draws}D/{losses}L ({score*100:.1f}%) | "
                f"Goals {gf}:{ga} ({gf-ga:+d})",
                flush=True,
            )

    out_file = run_dir / "evaluations" / f"multi_opponent_panel_{pairs*2}x{int(seconds)}s.json"
    out_file.write_text(json.dumps(panel_results, indent=2), encoding="utf8")
    return panel_results


def create_export_and_watch_scripts(
    run_dir: pathlib.Path,
    candidate_ckpt: pathlib.Path,
) -> dict:
    """Export the candidate to RLBot v5 bundle and generate ready-to-run watch batch files."""
    export_dir = ROOT / "exports" / "research05"
    export_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build DirectActor and pin candidate actor for watching
    actor = DirectActor("chronos")
    net = GigaNetwork(candidate_ckpt, "chronos")
    actor.core.load_state_dict(net.state_dict(), strict=True)
    pin_dir = run_dir / "watch_pins" / "chronos" / "chronos_antidive_isolated_v3"
    pin_dir.mkdir(parents=True, exist_ok=True)
    actor_file = pin_dir / "actor.lt"
    save_actor(actor, actor_file, family="chronos", hitbox="breakout")
    for fn in ("POLICY.lt", "SHARED_HEAD.lt"):
        shutil.copy2(candidate_ckpt / fn, pin_dir / fn)

    # 2. Export RLBot v5 bundle from saved actor file
    bundle_path = export_actor_bundle(actor_file, export_dir, label="chronos_antidive_isolated_v3")
    print(f"\n[Export Ready] Exported candidate bundle to: {bundle_path}", flush=True)

    # 3. Create watch batch files for all opponents (original_chronos, chronos_lowtemp_swa, galactus, ripple, ducky)
    watch_scripts = [
        ("27_WATCH_CHRONOS_ANTIDIVE_VS_ORIGINAL.bat", "original_chronos"),
        ("28_WATCH_CHRONOS_ANTIDIVE_VS_LOWTEMP_SWA.bat", "chronos_lowtemp_swa"),
        ("29_WATCH_CHRONOS_ANTIDIVE_VS_GALACTUS.bat", "original_galactus"),
        ("30_WATCH_CHRONOS_ANTIDIVE_VS_RIPPLE.bat", "ripple"),
        ("31_WATCH_CHRONOS_ANTIDIVE_VS_DUCKY.bat", "ducky"),
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


def main() -> None:
    run = setup_research05()

    orig_chronos = run / "parents" / "chronos"
    swa_chronos = run / "parents" / "chronos_lowtemp_swa"
    orig_galactus = run / "parents" / "galactus"
    r04 = ROOT / "runs" / "research04"

    # Control: chronos_ctrl_mech_v1 (raw 524288 checkpoint, identical budget, seed 881001, 0% curriculum, no SWA)
    ctrl_ckpt = r04 / "branches" / "chronos" / "chronos_ctrl_mech_v1" / "checkpoints" / "524288"
    assert ctrl_ckpt.exists(), f"Control checkpoint not found: {ctrl_ckpt}"

    critic_donor = ROOT / "runs/research03/branches/chronos/chronos_lowtemp_mech_cont/checkpoints/524288"

    # 1. Train isolated treatment: chronos_antidive_isolated_v3 (327680 -> 524288, 0% curriculum, no SWA)
    treatment_ckpt = train_isolated_antidive(
        run,
        source_swa=swa_chronos,
        critic_donor=critic_donor,
        opponent_ckpt=orig_chronos,
        delta_steps=196608,
        mechanics_scale=0.85,
        defense_scale=1.0,
        policy_temperature=0.25,
        actor_lr=1.25e-6,
        anchor_coef=0.18,
        seed=881001,
    )

    # 2. Matched Evaluation on Dev Suite vs original_chronos (100 pairs = 200 games, 135s, seed 1950000000)
    print("\n--- Evaluating Dev Suite vs original_chronos (200 games, 135s) ---", flush=True)
    dev_treat = run_eval_suite(
        run, treatment_ckpt, orig_chronos, "chronos", "original_chronos",
        label="chronos_antidive_v3_vs_original_chronos", pairs=100, seconds=135.0, seed=1950000000
    )
    dev_ctrl = run_eval_suite(
        run, ctrl_ckpt, orig_chronos, "chronos", "original_chronos",
        label="chronos_ctrl_v1_vs_original_chronos", pairs=100, seconds=135.0, seed=1950000000
    )
    dev_swa = run_eval_suite(
        run, swa_chronos, orig_chronos, "chronos", "original_chronos",
        label="chronos_lowtemp_swa_vs_original_chronos", pairs=100, seconds=135.0, seed=1950000000
    )

    # 3. Direct H2H vs chronos_lowtemp_swa preview (100 pairs = 200 games, 135s, seed 1960000000)
    print("\n--- Evaluating Direct H2H vs chronos_lowtemp_swa (200 games, 135s) ---", flush=True)
    h2h_treat = run_eval_suite(
        run, treatment_ckpt, swa_chronos, "chronos", "chronos_lowtemp_swa",
        label="chronos_antidive_v3_vs_lowtemp_swa", pairs=100, seconds=135.0, seed=1960000000
    )
    h2h_ctrl = run_eval_suite(
        run, ctrl_ckpt, swa_chronos, "chronos", "chronos_lowtemp_swa",
        label="chronos_ctrl_v1_vs_lowtemp_swa", pairs=100, seconds=135.0, seed=1960000000
    )

    # 4. Secondary Native Opponent vs original_galactus (50 pairs = 100 games, 100s, seed 1980000000)
    print("\n--- Evaluating Secondary Opponent vs original_galactus (100 games, 100s) ---", flush=True)
    gal_treat = run_eval_suite(
        run, treatment_ckpt, orig_galactus, "galactus", "original_galactus",
        label="chronos_antidive_v3_vs_galactus", pairs=50, seconds=100.0, seed=1980000000
    )
    gal_ctrl = run_eval_suite(
        run, ctrl_ckpt, orig_galactus, "galactus", "original_galactus",
        label="chronos_ctrl_v1_vs_galactus", pairs=50, seconds=100.0, seed=1980000000
    )

    # 5. Multi-Opponent Panel in RocketSim across chronos, galactus, ripple, ducky
    panel_results = run_cross_bot_panel(run, treatment_ckpt, orig_chronos, pairs=10, seconds=45.0, seed=770001)

    # 6. Export RLBot bundle and create watch batch files
    export_info = create_export_and_watch_scripts(run, treatment_ckpt)

    # 7. Compile Final Report Artifact
    final_report = {
        "status": "COMPLETED",
        "experiment": "research05_isolated_defense",
        "champion_status": "original_chronos retained unchanged",
        "intervention_summary": {
            "type": "single_isolated_reward_intervention",
            "reward_class": "ValidatedAntiDiveMechanicsGoalPotential (v3)",
            "curriculum_change": "0.0% (100% full-match standard kickoffs)",
            "weight_averaging": "None (raw 524,288-step checkpoint evaluated directly)",
            "training_budget": "327,680 -> 524,288 steps (196,608 steps, 24 PPO iterations)",
            "training_seed": 881001,
        },
        "model_identities": {
            "original_chronos": {
                "POLICY_sha256": sha256_file(orig_chronos / "POLICY.lt"),
                "SHARED_HEAD_sha256": sha256_file(orig_chronos / "SHARED_HEAD.lt"),
            },
            "chronos_lowtemp_swa": {
                "POLICY_sha256": sha256_file(swa_chronos / "POLICY.lt"),
                "SHARED_HEAD_sha256": sha256_file(swa_chronos / "SHARED_HEAD.lt"),
            },
            "chronos_ctrl_mech_v1": {
                "POLICY_sha256": sha256_file(ctrl_ckpt / "POLICY.lt"),
                "SHARED_HEAD_sha256": sha256_file(ctrl_ckpt / "SHARED_HEAD.lt"),
            },
            "chronos_antidive_isolated_v3": {
                "POLICY_sha256": sha256_file(treatment_ckpt / "POLICY.lt"),
                "SHARED_HEAD_sha256": sha256_file(treatment_ckpt / "SHARED_HEAD.lt"),
            },
        },
        "dev_evaluations_vs_original_chronos_200g_135s": {
            "chronos_antidive_isolated_v3": dev_treat,
            "chronos_ctrl_mech_v1": dev_ctrl,
            "chronos_lowtemp_swa": dev_swa,
        },
        "direct_h2h_evaluations_vs_lowtemp_swa_200g_135s": {
            "chronos_antidive_isolated_v3": h2h_treat,
            "chronos_ctrl_mech_v1": h2h_ctrl,
        },
        "secondary_panel_vs_original_galactus_100g_100s": {
            "chronos_antidive_isolated_v3": gal_treat,
            "chronos_ctrl_mech_v1": gal_ctrl,
        },
        "multi_opponent_panel": panel_results,
        "export_info": export_info,
    }

    report_path = run / "research05_summary.json"
    report_path.write_text(json.dumps(final_report, indent=2), encoding="utf8")
    print(f"\n[RESEARCH05 COMPLETE] Summary written to {report_path}", flush=True)


if __name__ == "__main__":
    main()
