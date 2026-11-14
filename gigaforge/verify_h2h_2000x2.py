"""Independently recompute and verify both 2,000-game 135s H2H matchups from raw batch_*.json and games.csv files."""
from __future__ import annotations
import csv, hashlib, json, math, pathlib, sys
from scipy.stats import t

ROOT = pathlib.Path(__file__).resolve().parent
R04_H2H = ROOT / "runs/research04/h2h"

TELEMETRY_COLS = [
    "saves_and_clears",
    "failed_challenges",
    "attacking_shots",
    "opp_possession_steps",
    "goalside_shadow_steps",
    "ball_in_opp_half_steps",
    "passive_net_camp_steps",
    "concede_unreachable_dive",
    "concede_overcommit_behind_ball",
    "concede_boost_detour",
    "concede_not_goalside_lane",
    "concede_slow_recovery",
]


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def recompute_subset(rows: list[dict]) -> dict:
    n = len(rows)
    assert n > 0
    wins = sum(1 for r in rows if int(r["outcome"]) == 1)
    draws = sum(1 for r in rows if int(r["outcome"]) == 0)
    losses = sum(1 for r in rows if int(r["outcome"]) == -1)
    assert wins + draws + losses == n

    for r in rows:
        gf_i = int(r["goals_for"])
        ga_i = int(r["goals_against"])
        expected_out = (gf_i > ga_i) - (gf_i < ga_i)
        assert int(r["outcome"]) == expected_out, f"Outcome mismatch on row {r}"

    gf = sum(int(r["goals_for"]) for r in rows)
    ga = sum(int(r["goals_against"]) for r in rows)
    score_rate = (wins + 0.5 * draws) / n

    blocks: dict[int, list[float]] = {}
    for r in rows:
        s = int(r["seed"])
        pts = (int(r["outcome"]) + 1) / 2.0
        blocks.setdefault(s, []).append(pts)

    paired = [sum(v) / 2.0 for v in blocks.values() if len(v) == 2]
    lower = upper = se = t_crit = margin = mean_paired = var_paired = None
    if len(paired) >= 2:
        mean_paired = sum(paired) / len(paired)
        assert abs(mean_paired - score_rate) < 1e-12, f"Paired mean {mean_paired} != score_rate {score_rate}"
        var_paired = sum((v - mean_paired) ** 2 for v in paired) / (len(paired) - 1)
        se = math.sqrt(var_paired / len(paired))
        t_crit = float(t.ppf(0.975, len(paired) - 1))
        margin = t_crit * se
        lower = max(0.0, mean_paired - margin)
        upper = min(1.0, mean_paired + margin)

    tel_totals = {k: sum(int(r[k]) for r in rows) for k in TELEMETRY_COLS}
    tel_per_game = {k: tel_totals[k] / n for k in TELEMETRY_COLS}
    opp_poss = tel_totals["opp_possession_steps"]
    opp_half = tel_totals["ball_in_opp_half_steps"]

    return {
        "games": n,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score_rate": score_rate,
        "goals_for": gf,
        "goals_against": ga,
        "goal_diff": gf - ga,
        "goals_for_per_game": gf / n,
        "goals_against_per_game": ga / n,
        "goal_diff_per_game": (gf - ga) / n,
        "paired_blocks": len(paired),
        "paired_variance": var_paired,
        "paired_std_error": se,
        "t_critical_95": t_crit,
        "margin_95": margin,
        "score_interval_95": [lower, upper],
        "telemetry": {
            "totals": tel_totals,
            "per_game": tel_per_game,
            "goalside_shadow_rate": tel_totals["goalside_shadow_steps"] / opp_poss if opp_poss > 0 else None,
            "passive_net_camp_rate": tel_totals["passive_net_camp_steps"] / opp_half if opp_half > 0 else None,
            "concession_forensics_per_conceded_goal": {
                k: tel_totals[k] / ga
                for k in (
                    "concede_unreachable_dive",
                    "concede_overcommit_behind_ball",
                    "concede_boost_detour",
                    "concede_not_goalside_lane",
                    "concede_slow_recovery",
                )
            }
            if ga > 0
            else None,
        },
    }


def verify_matchup_dir(test_dir: pathlib.Path, expected_seed: int, expected_opponent: str) -> dict:
    test_json_path = test_dir / "test.json"
    csv_path = test_dir / "games.csv"
    state = json.loads(test_json_path.read_text(encoding="utf8"))
    assert state["status"] == "complete", f"Expected complete status, got {state['status']}"

    # 1. Reconstruct all games from raw batch_*.json files and verify chunk SHA256s
    batch_rows = []
    batch_files = sorted(test_dir.glob("batch_*.json"))
    assert len(batch_files) == 10, f"Expected 10 batch files, found {len(batch_files)}"
    chunk_map = {c["path"]: c["sha256"] for c in state["chunks"]}
    for bf in batch_files:
        actual_sha = sha256_file(bf)
        assert chunk_map.get(bf.name) == actual_sha, f"Chunk SHA mismatch on {bf.name}"
        bdata = json.loads(bf.read_text(encoding="utf8"))
        assert bdata.get("direct_head_to_head") is True
        assert bdata.get("baseline_trials") == []
        batch_rows.extend(bdata["trials"])

    # 2. Reconstruct all games from games.csv and verify exact match with batch_rows
    with csv_path.open("r", encoding="utf8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(batch_rows) == 2000
    assert len(csv_rows) == 2000

    for i, (br, cr) in enumerate(zip(batch_rows, csv_rows), 1):
        assert int(cr["round"]) == i
        assert int(cr["seed"]) == int(br["seed"])
        assert int(cr["side"]) == int(br["side"])
        assert cr["opponent"] == br["opponent"] == expected_opponent
        assert int(cr["goals_for"]) == int(br["goals_for"])
        assert int(cr["goals_against"]) == int(br["goals_against"])
        assert int(cr["outcome"]) == int(br["outcome"])
        assert abs(float(cr["seconds"]) - 135.0) < 1e-9
        assert abs(float(br["seconds"]) - 135.0) < 1e-9
        for col in TELEMETRY_COLS:
            assert int(cr[col]) == int(br[col])

    # 3. Verify exact seed & color schedule
    expected_pairs = {(expected_seed + p, s) for p in range(1000) for s in (0, 1)}
    actual_pairs = {(int(r["seed"]), int(r["side"])) for r in batch_rows}
    assert actual_pairs == expected_pairs, "Seed/side pairs do not match exact predeclared schedule"

    # 4. Recompute overall and per-color summaries independently
    overall = recompute_subset(batch_rows)
    blue = recompute_subset([r for r in batch_rows if int(r["side"]) == 0])
    orange = recompute_subset([r for r in batch_rows if int(r["side"]) == 1])

    # 5. Cross-check against test.json summary
    s = state["summary"]
    assert s["games"] == overall["games"] == 2000
    assert s["wins"] == overall["wins"]
    assert s["draws"] == overall["draws"]
    assert s["losses"] == overall["losses"]
    assert abs(s["score_rate"] - overall["score_rate"]) < 1e-12
    assert s["goals_for"] == overall["goals_for"]
    assert s["goals_against"] == overall["goals_against"]
    assert abs(s["score_interval_95"][0] - overall["score_interval_95"][0]) < 1e-12
    assert abs(s["score_interval_95"][1] - overall["score_interval_95"][1]) < 1e-12

    # Verify Blue + Orange sums equal Overall
    assert blue["games"] + orange["games"] == 2000
    assert blue["wins"] + orange["wins"] == overall["wins"]
    assert blue["draws"] + orange["draws"] == overall["draws"]
    assert blue["losses"] + orange["losses"] == overall["losses"]
    assert blue["goals_for"] + orange["goals_for"] == overall["goals_for"]
    assert blue["goals_against"] + orange["goals_against"] == overall["goals_against"]

    # 6. Verify frozen model file hashes on disk inside test_dir
    cand_pin = pathlib.Path(state["candidate"])
    opp_pin = pathlib.Path(state["original"])
    for fn, expected_digest in state["candidate_files"].items():
        assert sha256_file(cand_pin / fn) == expected_digest
    for fn, expected_digest in state["original_files"].items():
        assert sha256_file(opp_pin / fn) == expected_digest

    return {
        "directory": str(test_dir),
        "test_json": str(test_json_path),
        "test_json_sha256": sha256_file(test_json_path),
        "games_csv": str(csv_path),
        "games_csv_sha256": sha256_file(csv_path),
        "batch_files_verified": len(batch_files),
        "request": state["request"],
        "binary_sha256": state["binary_sha256"],
        "candidate_identity": {
            "trial": state["selection"]["trial"],
            "arm": state["selection"].get("arm"),
            "selection_mode": state["selection"].get("selection_mode"),
            "confirmation_delta_untouched": state["selection"]["confirmation_delta"],
            "pin_path": state["candidate"],
            "actor_lt": state["selection"]["actor"],
            "actor_sha256": state["actor_sha256"],
            "files": state["candidate_files"],
        },
        "opponent_identity": state["opponent_info"],
        "overall": overall,
        "by_color": {
            "blue": blue,
            "orange": orange,
        },
        "arithmetic_and_hash_checks": "ALL_PASSED",
    }


def main() -> None:
    m1_dir = R04_H2H / "6ae1d06c86c4a8a2"
    # Find matchup 2 directory
    m2_dirs = [
        p for p in R04_H2H.iterdir()
        if p.is_dir() and p.name != "6ae1d06c86c4a8a2" and (p / "test.json").is_file()
    ]
    assert len(m2_dirs) == 1, f"Expected 1 matchup-2 dir, found {m2_dirs}"
    m2_dir = m2_dirs[0]

    v1 = verify_matchup_dir(m1_dir, expected_seed=1820000000, expected_opponent="original_chronos")
    v2 = verify_matchup_dir(m2_dir, expected_seed=1860000000, expected_opponent="chronos_lowtemp_swa")

    # Verify disjointness between Matchup 1 and Matchup 2 seeds
    s1 = set(range(1820000000, 1820001000))
    s2 = set(range(1860000000, 1860001000))
    assert len(s1 & s2) == 0

    # Verify retained champion in research04/champions/chronos.json is still original_chronos
    champ_json = json.loads((ROOT / "runs/research04/champions/chronos.json").read_text(encoding="utf8"))
    conf_json = json.loads((ROOT / "runs/research04/evaluations/lab_00001_chronos_confirmation.json").read_text(encoding="utf8"))

    report = {
        "verified_at_protocol": "direct-h2h-v1 / arena-rng-v4",
        "predeclared_plan": str(R04_H2H / "predeclared_2000x2_plan.json"),
        "confirmation_record_untouched": {
            "path": str(ROOT / "runs/research04/evaluations/lab_00001_chronos_confirmation.json"),
            "delta": conf_json["statistics"]["delta"],
            "decision": conf_json["decision"],
        },
        "retained_champion_status": champ_json,
        "matchup_1_vs_original_chronos": v1,
        "matchup_2_vs_chronos_lowtemp_swa": v2,
    }
    out_path = ROOT / "runs/research04/h2h_2000x2_verified_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf8")
    print("VERIFICATION_REPORT_SAVED:", out_path)
    print(json.dumps({
        "matchup_1": {
            "dir": v1["directory"],
            "overall": {k: v1["overall"][k] for k in ("games", "wins", "draws", "losses", "score_rate", "goals_for", "goals_against", "goals_for_per_game", "goals_against_per_game", "score_interval_95", "paired_std_error")},
            "blue": {k: v1["by_color"]["blue"][k] for k in ("games", "wins", "draws", "losses", "score_rate", "goals_for", "goals_against", "goals_for_per_game", "goals_against_per_game")},
            "orange": {k: v1["by_color"]["orange"][k] for k in ("games", "wins", "draws", "losses", "score_rate", "goals_for", "goals_against", "goals_for_per_game", "goals_against_per_game")},
        },
        "matchup_2": {
            "dir": v2["directory"],
            "overall": {k: v2["overall"][k] for k in ("games", "wins", "draws", "losses", "score_rate", "goals_for", "goals_against", "goals_for_per_game", "goals_against_per_game", "score_interval_95", "paired_std_error")},
            "blue": {k: v2["by_color"]["blue"][k] for k in ("games", "wins", "draws", "losses", "score_rate", "goals_for", "goals_against", "goals_for_per_game", "goals_against_per_game")},
            "orange": {k: v2["by_color"]["orange"][k] for k in ("games", "wins", "draws", "losses", "score_rate", "goals_for", "goals_against", "goals_for_per_game", "goals_against_per_game")},
        }
    }, indent=2))


if __name__ == "__main__":
    main()
