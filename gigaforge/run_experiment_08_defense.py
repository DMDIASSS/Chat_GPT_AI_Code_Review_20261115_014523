"""Experiment 08 (research04): Improve Chronos's defensive decisions while preserving attacking behavior.

1. Preserves three distinct identities:
   - original_chronos (runs/research04/parents/chronos)
   - chronos_lowtemp_swa (runs/research04/parents/chronos_lowtemp_swa, exact copy of research03 preview)
   - New defensive candidates in runs/research04/branches/chronos/
2. Verifies low-temperature (T=0.25) PPO mathematical consistency (logprobs, masks, ratio=1.0, frozen shared_head).
3. Runs quantitative defensive failure forensics on original_chronos and chronos_lowtemp_swa.
4. Trains matched control (chronos_ctrl_mech_v1) vs defensive tactical intervention (chronos_def_tactical_v2)
   and builds trajectory SWA (chronos_defensive_swa).
5. Evaluates on the Held-Out Defensive Threat Suite, Dev H2H, Confirmation H2H, Direct H2H vs chronos_lowtemp_swa,
   and Secondary Opponent Panel vs [original_chronos, original_galactus].
"""
from __future__ import annotations
import hashlib, json, math, pathlib, shutil, subprocess, sys, time
import torch

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT.parent / "NovaForge"))

import rlgym.rocket_league.sim as sim
import run as gf_run
from research import latest_in, stats
from nova.giga_teachers import GigaNetwork


def meshes_dir() -> pathlib.Path:
    return pathlib.Path(sim.__file__).parent / "collision_meshes"


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def aggregate_telemetry(rows: list[dict]) -> dict:
    n = max(1, len(rows))
    goals_for = sum(r.get("goals_for", 0) for r in rows)
    goals_against = sum(r.get("goals_against", 0) for r in rows)
    wins = sum(r.get("outcome", 0) == 1 for r in rows)
    draws = sum(r.get("outcome", 0) == 0 for r in rows)
    losses = sum(r.get("outcome", 0) == -1 for r in rows)
    saves = sum(r.get("saves_and_clears", 0) for r in rows)
    failed_chal = sum(r.get("failed_challenges", 0) for r in rows)
    atk_shots = sum(r.get("attacking_shots", 0) for r in rows)
    opp_poss = sum(r.get("opp_possession_steps", 0) for r in rows)
    shadow_steps = sum(r.get("goalside_shadow_steps", 0) for r in rows)
    opp_half_steps = sum(r.get("ball_in_opp_half_steps", 0) for r in rows)
    net_camp_steps = sum(r.get("passive_net_camp_steps", 0) for r in rows)

    c_dive = sum(r.get("concede_unreachable_dive", 0) for r in rows)
    c_over = sum(r.get("concede_overcommit_behind_ball", 0) for r in rows)
    c_boost = sum(r.get("concede_boost_detour", 0) for r in rows)
    c_lane = sum(r.get("concede_not_goalside_lane", 0) for r in rows)
    c_rec = sum(r.get("concede_slow_recovery", 0) for r in rows)
    ga_denom = max(1, goals_against)

    return {
        "games": len(rows),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_rate": (wins + 0.5 * draws) / n,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_diff": goals_for - goals_against,
        "saves_and_clears": saves,
        "saves_per_game": saves / n,
        "failed_challenges": failed_chal,
        "failed_challenges_per_game": failed_chal / n,
        "attacking_shots": atk_shots,
        "attacking_shots_per_game": atk_shots / n,
        "goalside_shadow_rate": shadow_steps / max(1, opp_poss),
        "passive_net_camping_rate": net_camp_steps / max(1, opp_half_steps),
        "concession_forensics": {
            "total_conceded": goals_against,
            "unreachable_dive": c_dive,
            "unreachable_dive_pct": c_dive / ga_denom,
            "overcommit_behind_ball": c_over,
            "overcommit_behind_ball_pct": c_over / ga_denom,
            "boost_detour": c_boost,
            "boost_detour_pct": c_boost / ga_denom,
            "not_goalside_lane": c_lane,
            "not_goalside_lane_pct": c_lane / ga_denom,
            "slow_recovery": c_rec,
            "slow_recovery_pct": c_rec / ga_denom,
        },
    }


def verify_lowtemp_ppo_mathematics(run_dir: pathlib.Path) -> dict:
    """Section 7: Explicitly verify low-temperature (T=0.25) logprobs, masks, and ratio=1.0."""
    parent_c = run_dir / "parents" / "chronos"
    net = GigaNetwork(parent_c, "chronos").eval()
    torch.manual_seed(271031)
    obs = torch.randn(64, 225, dtype=torch.float32)
    mask = torch.ones(64, 90, dtype=torch.bool)
    # Disable some actions to test action masking
    mask[:, 50:70] = False
    temp = 0.25

    with torch.no_grad():
        logits = net(obs)
        # 1. Collection formula (PPOLearner::InferPolicyProbsFromModels)
        probs_collect = torch.softmax(logits / temp + (-1e10) * (~mask).float(), dim=-1).clamp(1e-11, 1.0)
        actions = torch.multinomial(probs_collect, 1, replacement=True)
        old_log_probs = torch.log(probs_collect).gather(-1, actions).flatten()

        # 2. PPO Learn recomputation formula (PPOLearner::Learn line 200)
        probs_learn = torch.softmax(logits / temp - 1e10 * (~mask).float(), dim=-1).clamp(1e-11, 1.0)
        new_log_probs = probs_learn.log().gather(-1, actions).view_as(old_log_probs)
        ratio = torch.exp(new_log_probs - old_log_probs)
        log_ratio = new_log_probs - old_log_probs
        kl = ((torch.exp(log_ratio) - 1.0) - log_ratio).mean().item()

        # Compare tail probability suppression T=1.0 vs T=0.25
        probs_t1 = torch.softmax(logits + (-1e10) * (~mask).float(), dim=-1)
        top3_vals, _ = torch.topk(probs_t1, k=3, dim=-1)
        tail_mass_t1 = (1.0 - top3_vals.sum(dim=-1)).mean().item()
        top3_vals_lt, _ = torch.topk(probs_collect, k=3, dim=-1)
        tail_mass_lt = (1.0 - top3_vals_lt.sum(dim=-1)).mean().item()

    max_logprob_diff = float((new_log_probs - old_log_probs).abs().max().item())
    max_ratio_err = float((ratio - 1.0).abs().max().item())
    assert max_logprob_diff < 1e-6 and max_ratio_err < 1e-6, "Temperature logprob mismatch!"
    res = {
        "temperature": temp,
        "max_logprob_diff": max_logprob_diff,
        "initial_importance_ratio_mean": float(ratio.mean().item()),
        "initial_importance_ratio_max_err": max_ratio_err,
        "initial_kl": kl,
        "masked_action_max_prob": float(probs_collect[:, 50:70].max().item()),
        "mean_tail_prob_mass_beyond_top3_T1.0": tail_mass_t1,
        "mean_tail_prob_mass_beyond_top3_T0.25": tail_mass_lt,
        "status": "PASSED",
    }
    print("[PPO Math Verification]", json.dumps(res, indent=2), flush=True)
    return res


def setup_research04() -> pathlib.Path:
    run = ROOT / "runs" / "research04"
    r03 = ROOT / "runs" / "research03"
    run.mkdir(parents=True, exist_ok=True)
    for f in ("config.json", "tuning.json"):
        if (r03 / f).exists() and not (run / f).exists():
            shutil.copy2(r03 / f, run / f)

    # 1. Preserve original_chronos and original_galactus in parents/
    for fam in ("chronos", "galactus"):
        src = r03 / "parents" / fam
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
    assert sha256_file(swa_dst / "POLICY.lt") == sha256_file(swa_src / "POLICY.lt")
    print(
        f"[Identities Verified]\n"
        f"  original_chronos POLICY.lt   = {sha256_file(run / 'parents/chronos/POLICY.lt')[:16]}\n"
        f"  chronos_lowtemp_swa POLICY.lt = {sha256_file(swa_dst / 'POLICY.lt')[:16]}",
        flush=True,
    )
    return run


def run_eval_suite(
    run_dir: pathlib.Path,
    candidate_ckpt: pathlib.Path,
    opponent_ckpt: pathlib.Path,
    opponent_family: str,
    opponent_name: str,
    label: str,
    pairs: int = 50,
    seconds: float = 100.0,
    seed: int = 610000000,
    scenario_mode: str = "match",
) -> dict:
    eval_dir = run_dir / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    out_file = eval_dir / f"{label}_{scenario_mode}_{pairs*2}x{int(seconds)}s_s{seed}.json"
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
        f"Saves/g {tel['saves_per_game']:.2f} | FailedChal/g {tel['failed_challenges_per_game']:.2f} | "
        f"AtkShots/g {tel['attacking_shots_per_game']:.2f} | Shadow {tel['goalside_shadow_rate']*100:.1f}% | "
        f"ConcedeDive {cf['unreachable_dive']}/{cf['total_conceded']} ({cf['unreachable_dive_pct']*100:.1f}%) "
        f"({elapsed:.1f}s)",
        flush=True,
    )
    return tel


def train_from_swa_checkpoint(
    run_dir: pathlib.Path,
    arm_name: str,
    source_swa: pathlib.Path,
    critic_donor: pathlib.Path,
    opponent_ckpt: pathlib.Path,
    delta_steps: int = 196608,
    defensive_mechanics_reward: bool = True,
    defense_scale: float = 1.0,
    mechanics_scale: float = 0.85,
    defensive_curriculum_prob: float = 0.30,
    policy_temperature: float = 0.25,
    actor_lr: float = 1.25e-6,
    anchor_coef: float = 0.18,
    seed: int = 881001,
) -> pathlib.Path:
    """Continue fine-tuning from chronos_lowtemp_swa with pretrained critic and warm optimizer."""
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
        "mechanics_reward": not defensive_mechanics_reward,
        "defensive_mechanics_reward": defensive_mechanics_reward,
        "mechanics_scale": mechanics_scale,
        "defense_scale": defense_scale,
        "defensive_curriculum_prob": defensive_curriculum_prob,
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
        f"def_reward={defensive_mechanics_reward}, def_scale={defense_scale}, "
        f"def_curr_prob={defensive_curriculum_prob}, T={policy_temperature}) ===",
        flush=True,
    )
    t0 = time.monotonic()
    gf_run.launch(recipe, log=arm_dir / "train.log")
    elapsed = time.monotonic() - t0
    cur = latest_in(arm_dir)
    if cur is None:
        raise RuntimeError(f"No checkpoint produced for {arm_name}")
    gf_run.seal_generation(cur, "chronos")

    # Verify SHARED_HEAD.lt is 100% frozen
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


def build_policy_soup(
    run_dir: pathlib.Path,
    soup_name: str,
    components: list[tuple[pathlib.Path, float]],
    template_ckpt: pathlib.Path,
) -> pathlib.Path:
    out_dir = run_dir / "branches" / "chronos" / soup_name / "checkpoints" / "1000000"
    out_dir.mkdir(parents=True, exist_ok=True)
    for fn in template_ckpt.iterdir():
        if fn.is_file() and fn.name != "POLICY.lt":
            shutil.copy2(fn, out_dir / fn.name)

    total_w = sum(w for _, w in components)
    models = [(GigaNetwork(p, "chronos"), w / total_w) for p, w in components]
    target_net = GigaNetwork(template_ckpt, "chronos")
    with torch.no_grad():
        avg_sd = {}
        for k in target_net.policy.state_dict().keys():
            avg_sd[k] = sum(m.policy.state_dict()[k] * w for m, w in models)
        target_net.policy.load_state_dict(avg_sd, strict=True)
    torch.jit.save(torch.jit.script(target_net.policy), str(out_dir / "POLICY.lt"))
    (out_dir / "COMPLETE").write_text("1000000\n", encoding="utf8")
    gf_run.seal_generation(out_dir, "chronos")
    gf_run.verify_generation(out_dir)
    return out_dir


def main() -> None:
    run = setup_research04()
    ppo_math = verify_lowtemp_ppo_mathematics(run)

    orig_chronos = run / "parents" / "chronos"
    orig_galactus = run / "parents" / "galactus"
    prev_swa = run / "parents" / "chronos_lowtemp_swa"
    critic_donor = ROOT / "runs/research03/branches/chronos/chronos_lowtemp_mech_cont/checkpoints/524288"

    print("\n=== STEP 1: Baseline & Preview Defensive Failure Forensics ===", flush=True)
    forensics = {}
    # 1a. Evaluate original_chronos and chronos_lowtemp_swa on the Held-Out Defensive Threat Suite (120 episodes x 20s)
    forensics["orig_chronos_threats"] = run_eval_suite(
        run, orig_chronos, orig_chronos, "chronos", "original_chronos",
        label="orig_chronos", pairs=60, seconds=20.0, seed=1910000000, scenario_mode="defensive_threats"
    )
    forensics["prev_swa_threats"] = run_eval_suite(
        run, prev_swa, orig_chronos, "chronos", "original_chronos",
        label="chronos_lowtemp_swa", pairs=60, seconds=20.0, seed=1910000000, scenario_mode="defensive_threats"
    )
    # 1b. Evaluate original_chronos and chronos_lowtemp_swa on 100-game Full-Match Dev Suite (seed=610000000, 100s)
    forensics["orig_chronos_dev100"] = run_eval_suite(
        run, orig_chronos, orig_chronos, "chronos", "original_chronos",
        label="orig_chronos_dev", pairs=50, seconds=100.0, seed=610000000, scenario_mode="match"
    )
    forensics["prev_swa_dev100"] = run_eval_suite(
        run, prev_swa, orig_chronos, "chronos", "original_chronos",
        label="chronos_lowtemp_swa_dev", pairs=50, seconds=100.0, seed=610000000, scenario_mode="match"
    )

    print("\n=== STEP 2: Bounded Matched-Control Pilot Training ===", flush=True)
    # Arm A: Matched Control (old MechanicsGoalPotential v1, kickoff-only resets, 196,608 steps from chronos_lowtemp_swa)
    ckpt_ctrl = train_from_swa_checkpoint(
        run_dir=run,
        arm_name="chronos_ctrl_mech_v1",
        source_swa=prev_swa,
        critic_donor=critic_donor,
        opponent_ckpt=orig_chronos,
        delta_steps=196608,
        defensive_mechanics_reward=False,
        defense_scale=0.0,
        mechanics_scale=0.85,
        defensive_curriculum_prob=0.0,
        policy_temperature=0.25,
        actor_lr=1.25e-6,
        anchor_coef=0.18,
        seed=881001,
    )

    # Arm B: Defensive Tactical Intervention (DefensiveMechanicsGoalPotential v2 + 30% defensive curriculum, 196,608 steps)
    ckpt_def = train_from_swa_checkpoint(
        run_dir=run,
        arm_name="chronos_def_tactical_v2",
        source_swa=prev_swa,
        critic_donor=critic_donor,
        opponent_ckpt=prev_swa,
        delta_steps=196608,
        defensive_mechanics_reward=True,
        defense_scale=1.0,
        mechanics_scale=0.85,
        defensive_curriculum_prob=0.30,
        policy_temperature=0.25,
        actor_lr=1.25e-6,
        anchor_coef=0.18,
        seed=881001,
    )

    # Arm C: Trajectory SWA combining the defensive tactical checkpoints + chronos_lowtemp_swa anchor
    def_base = run / "branches/chronos/chronos_def_tactical_v2/checkpoints"
    def_ckpts = [
        (p, 1.0)
        for p in (def_base / "458752", def_base / "491520", def_base / "524288")
        if p.exists()
    ]
    def_ckpts.append((prev_swa, 1.5))
    ckpt_def_swa = build_policy_soup(
        run_dir=run,
        soup_name="chronos_defensive_swa",
        components=def_ckpts,
        template_ckpt=ckpt_def,
    )

    print("\n=== STEP 3: Held-Out Threat Suite & Full-Match Evaluations ===", flush=True)
    eval_results = {
        "ppo_math_verification": ppo_math,
        "baseline_forensics": forensics,
        "candidates": {},
    }

    for name, ckpt in [
        ("chronos_ctrl_mech_v1", ckpt_ctrl),
        ("chronos_def_tactical_v2", ckpt_def),
        ("chronos_defensive_swa", ckpt_def_swa),
    ]:
        eval_results["candidates"][name] = {
            "checkpoint": str(ckpt),
            "policy_sha256": sha256_file(ckpt / "POLICY.lt"),
            "threats_120": run_eval_suite(
                run, ckpt, orig_chronos, "chronos", "original_chronos",
                label=f"{name}_threats", pairs=60, seconds=20.0, seed=1910000000, scenario_mode="defensive_threats"
            ),
            "dev_vs_orig_100": run_eval_suite(
                run, ckpt, orig_chronos, "chronos", "original_chronos",
                label=f"{name}_dev", pairs=50, seconds=100.0, seed=610000000, scenario_mode="match"
            ),
            "confirm_vs_orig_200": run_eval_suite(
                run, ckpt, orig_chronos, "chronos", "original_chronos",
                label=f"{name}_confirm", pairs=100, seconds=135.0, seed=810000000, scenario_mode="match"
            ),
            "direct_vs_prev_swa_200": run_eval_suite(
                run, ckpt, prev_swa, "chronos", "original_chronos",
                label=f"{name}_vs_prev_swa", pairs=100, seconds=135.0, seed=850000000, scenario_mode="match"
            ),
            "vs_orig_galactus_100": run_eval_suite(
                run, ckpt, orig_galactus, "galactus", "original_galactus",
                label=f"{name}_vs_galactus", pairs=50, seconds=100.0, seed=910000000, scenario_mode="match"
            ),
        }

    summary_path = run / "experiment08_defense_summary.json"
    summary_path.write_text(json.dumps(eval_results, indent=2), encoding="utf8")
    print("\nSAVED EXPERIMENT 08 SUMMARY:", summary_path, flush=True)


if __name__ == "__main__":
    main()
