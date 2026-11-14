"""1,500-Game Head-to-Head Evaluation of chronos_winrate_dominance_v1 vs original_chronos.

Parameters:
- Candidate: runs/research06/branches/chronos/chronos_winrate_dominance_v1/checkpoints/786432
- Opponent: original_chronos (runs/research06/parents/chronos)
- Total Games: 1,500 games (750 pairs, equal Blue and Orange)
- Match Duration: 135.0 seconds
- Base Seed: 2200000000 (disjoint from all prior experiments)
- Batch Size: 75 pairs (150 games) per batch x 10 batches
- Exact paired-seed Student-t 95% Confidence Interval
- Full telemetry: Goals, GF/GA, Saves, Failed Challenges, Unreachable Dives, Color Split
"""
from __future__ import annotations
import hashlib, json, math, os, pathlib, sys, time
import numpy as np
from scipy.stats import t

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run as gf_run


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def meshes_dir() -> pathlib.Path:
    import rlgym.rocket_league.sim as sim
    return pathlib.Path(sim.__file__).parent / "collision_meshes"


def compute_paired_summary(trials: list[dict]) -> dict:
    n = len(trials)
    if n == 0:
        return {}
    wins = sum(1 for r in trials if r["outcome"] > 0)
    draws = sum(1 for r in trials if r["outcome"] == 0)
    losses = sum(1 for r in trials if r["outcome"] < 0)
    score_rate = (wins + 0.5 * draws) / n

    gf = sum(r.get("goals_for", 0) for r in trials)
    ga = sum(r.get("goals_against", 0) for r in trials)

    # Paired-seed Student-t confidence interval
    blocks = {}
    for r in trials:
        blocks.setdefault(r["seed"], []).append((r["outcome"] + 1) / 2)
    paired = [sum(v) / 2 for v in blocks.values() if len(v) == 2]

    lower, upper, se, margin = None, None, None, None
    if len(paired) >= 2:
        mean = sum(paired) / len(paired)
        variance = sum((v - mean) ** 2 for v in paired) / (len(paired) - 1)
        se = math.sqrt(variance / len(paired))
        t_crit = float(t.ppf(0.975, len(paired) - 1))
        margin = t_crit * se if variance > 0 else math.sqrt(math.log(40) / (2 * len(paired)))
        lower = max(0.0, mean - margin)
        upper = min(1.0, mean + margin)

    # Color breakdown
    blue_trials = [r for r in trials if r.get("side") == 0]
    orange_trials = [r for r in trials if r.get("side") == 1]
    b_score = (sum(1 for r in blue_trials if r["outcome"] > 0) + 0.5 * sum(1 for r in blue_trials if r["outcome"] == 0)) / max(1, len(blue_trials))
    o_score = (sum(1 for r in orange_trials if r["outcome"] > 0) + 0.5 * sum(1 for r in orange_trials if r["outcome"] == 0)) / max(1, len(orange_trials))

    # Defensive and challenge forensics
    fc = sum(r.get("failed_challenges", 0) for r in trials)
    sc = sum(r.get("saves_and_clears", 0) for r in trials)
    atk = sum(r.get("attacking_shots", 0) for r in trials)
    c_dive = sum(r.get("concede_unreachable_dive", 0) for r in trials)
    c_over = sum(r.get("concede_overcommit_behind_ball", 0) for r in trials)

    return {
        "games": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_rate": score_rate,
        "score_interval_95": [lower, upper],
        "margin_95": margin,
        "paired_blocks": len(paired),
        "goals_for": gf,
        "goals_against": ga,
        "goal_diff": gf - ga,
        "gf_per_game": gf / n,
        "ga_per_game": ga / n,
        "color_split": {
            "blue_games": len(blue_trials),
            "blue_score_rate": b_score,
            "orange_games": len(orange_trials),
            "orange_score_rate": o_score,
            "orange_delta_pp": (o_score - b_score) * 100,
        },
        "telemetry_per_game": {
            "saves_per_game": sc / n,
            "failed_challenges_per_game": fc / n,
            "attacking_shots_per_game": atk / n,
        },
        "concession_forensics": {
            "total_conceded": ga,
            "unreachable_dive": c_dive,
            "unreachable_dive_pct": (c_dive / ga) if ga > 0 else 0.0,
            "overcommit": c_over,
            "overcommit_pct": (c_over / ga) if ga > 0 else 0.0,
        },
    }


def main() -> None:
    cand_ckpt = ROOT / "runs" / "research06" / "branches" / "chronos" / "chronos_winrate_dominance_v1" / "checkpoints" / "786432"
    orig_ckpt = ROOT / "runs" / "research06" / "parents" / "chronos"

    assert cand_ckpt.exists(), f"Candidate checkpoint not found: {cand_ckpt}"
    assert orig_ckpt.exists(), f"Original Chronos checkpoint not found: {orig_ckpt}"

    out_dir = ROOT / "runs" / "research06" / "evaluations" / "eval_1500_vs_original_chronos"
    out_dir.mkdir(parents=True, exist_ok=True)

    cand_sha = sha256_file(cand_ckpt / "POLICY.lt")
    orig_sha = sha256_file(orig_ckpt / "POLICY.lt")

    print("==================================================================", flush=True)
    print(" 1,500-Game Benchmark: chronos_winrate_dominance_v1 vs original_chronos", flush=True)
    print("==================================================================", flush=True)
    print(f"Candidate POLICY.lt SHA256: {cand_sha}", flush=True)
    print(f"Opponent  POLICY.lt SHA256: {orig_sha}", flush=True)
    print(f"Evaluation Target: 1,500 games (750 pairs, 135s each, base seed 2200000000)", flush=True)

    total_pairs = 750
    batch_pairs = 75
    base_seed = 2200000000
    seconds = 135.0

    all_trials = []
    num_batches = math.ceil(total_pairs / batch_pairs)

    t_all_start = time.monotonic()

    for b in range(num_batches):
        cur_offset = b * batch_pairs
        cur_pairs = min(batch_pairs, total_pairs - cur_offset)
        cur_seed = base_seed + cur_offset
        batch_file = out_dir / f"batch_{b:02d}.json"

        if batch_file.exists():
            try:
                cached = json.loads(batch_file.read_text(encoding="utf8"))
                b_trials = cached.get("trials", [])
                if len(b_trials) == cur_pairs * 2:
                    all_trials.extend(b_trials)
                    s = compute_paired_summary(all_trials)
                    ci_str = f"[{s['score_interval_95'][0]*100:.2f}%, {s['score_interval_95'][1]*100:.2f}%]" if s['score_interval_95'][0] else "N/A"
                    print(
                        f"[Batch {b+1:02d}/{num_batches:02d} | REUSED] "
                        f"Cumulative: {s['games']}/{total_pairs*2} games | "
                        f"{s['wins']}W/{s['draws']}D/{s['losses']}L ({s['score_rate']*100:.2f}%, CI {ci_str}) | "
                        f"Goals {s['goals_for']}:{s['goals_against']} ({s['goal_diff']:+d})",
                        flush=True,
                    )
                    continue
            except Exception:
                pass

        spec = {
            "candidate": gf_run.descriptor(cand_ckpt, "chronos"),
            "compare_baseline": False,
            "scenario_mode": "kickoff",
            "opponents": [dict(gf_run.descriptor(orig_ckpt, "chronos"), name="original_chronos")],
            "pairs": cur_pairs,
            "seconds": seconds,
            "seed": cur_seed,
            "output": str(batch_file),
        }
        recipe = {
            "evaluation": spec,
            "torch_threads": 2,
            "meshes": str(meshes_dir()),
        }
        recipe_file = out_dir / f"batch_{b:02d}_recipe.json"
        recipe_file.write_text(json.dumps(recipe, indent=2), encoding="utf8")

        t0 = time.monotonic()
        gf_run.launch(recipe, log=out_dir / f"batch_{b:02d}.log")
        dt = time.monotonic() - t0

        raw = json.loads(batch_file.read_text(encoding="utf8"))
        b_trials = raw.get("trials", [])
        all_trials.extend(b_trials)

        s = compute_paired_summary(all_trials)
        ci_str = f"[{s['score_interval_95'][0]*100:.2f}%, {s['score_interval_95'][1]*100:.2f}%]" if s['score_interval_95'][0] else "N/A"
        print(
            f"[Batch {b+1:02d}/{num_batches:02d} in {dt:.1f}s] "
            f"Cumulative: {s['games']}/{total_pairs*2} games | "
            f"{s['wins']}W/{s['draws']}D/{s['losses']}L ({s['score_rate']*100:.2f}%, CI {ci_str}) | "
            f"Goals {s['goals_for']}:{s['goals_against']} ({s['goal_diff']:+d})",
            flush=True,
        )

    total_time = time.monotonic() - t_all_start
    final_summary = compute_paired_summary(all_trials)
    final_summary["total_wall_seconds"] = total_time
    final_summary["model_identities"] = {
        "candidate": {
            "label": "chronos_winrate_dominance_v1",
            "checkpoint": str(cand_ckpt),
            "POLICY_sha256": cand_sha,
            "SHARED_HEAD_sha256": sha256_file(cand_ckpt / "SHARED_HEAD.lt"),
        },
        "opponent": {
            "label": "original_chronos",
            "checkpoint": str(orig_ckpt),
            "POLICY_sha256": orig_sha,
            "SHARED_HEAD_sha256": sha256_file(orig_ckpt / "SHARED_HEAD.lt"),
        },
    }
    final_summary["configuration"] = {
        "total_games": total_pairs * 2,
        "pairs": total_pairs,
        "seconds_per_game": seconds,
        "base_seed": base_seed,
        "batch_size_pairs": batch_pairs,
    }

    summary_file = out_dir / "summary_1500g.json"
    summary_file.write_text(json.dumps(final_summary, indent=2), encoding="utf8")
    print(f"\n==================================================================", flush=True)
    print(f" [COMPLETE] 1,500 Games Finished in {total_time:.1f}s", flush=True)
    print(f" Summary written to {summary_file}", flush=True)
    print(f" Final Score Rate: {final_summary['score_rate']*100:.2f}% (CI [{final_summary['score_interval_95'][0]*100:.2f}%, {final_summary['score_interval_95'][1]*100:.2f}%])", flush=True)
    print(f" Final Goals: {final_summary['goals_for']} scored : {final_summary['goals_against']} conceded ({final_summary['goal_diff']:+d})", flush=True)
    print(f"==================================================================", flush=True)


if __name__ == "__main__":
    main()
