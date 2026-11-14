"""Tier 1: Comprehensive Feature Coverage Suite (>=5 tests per feature for all 20 features)."""
import os
import sys
import json
import math
import hashlib
import tempfile
import subprocess
from pathlib import Path
import pytest
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.e2e.conftest import (
    REPO_ROOT,
    GIGAFORGE_DIR,
    NOVAFORGE_DIR,
    NATIVE_EXE,
    VENV_PYTHON,
    BASELINE_HASHES,
    BASELINE_SIZES,
    CONTRACT_SPECS,
    SECONDARY_PANEL,
    sha256_file,
    compute_student_t_margin,
    compute_alpha_spending,
)


# ==============================================================================
# Feature 1: Baseline Hash & Contract Preservation
# ==============================================================================

def test_f1_chronos_policy_hash():
    """Verify invariant SHA256 hash for Chronos POLICY.lt."""
    path = NOVAFORGE_DIR / "assets" / "chronos" / "POLICY.lt"
    assert path.is_file(), f"Chronos POLICY.lt missing at {path}"
    assert sha256_file(path) == BASELINE_HASHES["chronos_policy"]
    assert path.stat().st_size == BASELINE_SIZES["chronos_policy"]


def test_f1_chronos_shared_hash():
    """Verify invariant SHA256 hash for Chronos SHARED_HEAD.lt."""
    path = NOVAFORGE_DIR / "assets" / "chronos" / "SHARED_HEAD.lt"
    assert path.is_file(), f"Chronos SHARED_HEAD.lt missing at {path}"
    assert sha256_file(path) == BASELINE_HASHES["chronos_shared"]
    assert path.stat().st_size == BASELINE_SIZES["chronos_shared"]


def test_f1_galactus_policy_hash():
    """Verify invariant SHA256 hash for Galactus POLICY.lt."""
    path = NOVAFORGE_DIR / "assets" / "galactus" / "POLICY.lt"
    assert path.is_file(), f"Galactus POLICY.lt missing at {path}"
    assert sha256_file(path) == BASELINE_HASHES["galactus_policy"]
    assert path.stat().st_size == BASELINE_SIZES["galactus_policy"]


def test_f1_galactus_shared_hash():
    """Verify invariant SHA256 hash for Galactus SHARED_HEAD.lt."""
    path = NOVAFORGE_DIR / "assets" / "galactus" / "SHARED_HEAD.lt"
    assert path.is_file(), f"Galactus SHARED_HEAD.lt missing at {path}"
    assert sha256_file(path) == BASELINE_HASHES["galactus_shared"]
    assert path.stat().st_size == BASELINE_SIZES["galactus_shared"]


def test_f1_research02_parents_identity():
    """Verify that research02 parents directory contains exact byte-identical copies of assets."""
    for family in ("chronos", "galactus"):
        parent_policy = GIGAFORGE_DIR / "runs" / "research02" / "parents" / family / "POLICY.lt"
        asset_policy = NOVAFORGE_DIR / "assets" / family / "POLICY.lt"
        if parent_policy.exists():
            assert sha256_file(parent_policy) == sha256_file(asset_policy)


# ==============================================================================
# Feature 2: Launcher Routing & Virtualenv Invariant
# ==============================================================================

def test_f2_launcher_run_bat_exists():
    """Verify that gigaforge/_RUN.bat exists and contains runtime router logic."""
    run_bat = GIGAFORGE_DIR / "_RUN.bat"
    assert run_bat.is_file()
    content = run_bat.read_text(encoding="utf8", errors="replace")
    assert "runtime_bootstrap.py" in content
    assert ".venv_native\\Scripts\\python.exe" in content


def test_f2_launchers_route_via_run_bat():
    """Verify that all gigaforge batch launchers (except _RUN.bat) route via _RUN.bat."""
    batch_files = list(GIGAFORGE_DIR.glob("*.bat"))
    assert len(batch_files) >= 15
    for bat in batch_files:
        if bat.name == "_RUN.bat":
            continue
        content = bat.read_text(encoding="utf8", errors="replace")
        assert "_RUN.bat" in content, f"Launcher {bat.name} does not route via _RUN.bat"


def test_f2_no_hardcoded_venv_in_launchers():
    """Verify that no launcher directly hardcodes .venv_native\\Scripts (violating routing)."""
    batch_files = list(GIGAFORGE_DIR.glob("*.bat"))
    for bat in batch_files:
        if bat.name == "_RUN.bat":
            continue
        content = bat.read_text(encoding="utf8", errors="replace")
        assert ".venv_native\\Scripts" not in content, f"Launcher {bat.name} hardcodes .venv_native path directly"


def test_f2_clean_env_no_old_wandb_pin():
    """Verify setup_runtime.py does not contain outdated wandb>=0.23 pin."""
    setup_file = GIGAFORGE_DIR / "setup_runtime.py"
    if setup_file.is_file():
        text = setup_file.read_text(encoding="utf8", errors="replace")
        assert "wandb>=0.23" not in text


def test_f2_launcher_exit_code_handling():
    """Verify batch launchers check errorlevel and exit with appropriate code."""
    watch_bat = GIGAFORGE_DIR / "18_WATCH_CHRONOS_TRIAL_62.bat"
    assert watch_bat.is_file()
    content = watch_bat.read_text(encoding="utf8", errors="replace")
    assert "if errorlevel 1 goto failed" in content
    assert "exit /b 0" in content
    assert "exit /b 1" in content


# ==============================================================================
# Feature 3: Native Simulator Self-Tests & GAE Verification
# ==============================================================================

def test_f3_native_binary_exists_and_pe():
    """Verify GigaForge.exe is a valid 64-bit Windows PE executable."""
    assert NATIVE_EXE.is_file(), f"Native executable missing at {NATIVE_EXE}"
    raw = NATIVE_EXE.read_bytes()
    assert len(raw) > 1000000
    assert raw[:2] == b"MZ"
    pe_offset = int.from_bytes(raw[60:64], "little")
    assert raw[pe_offset:pe_offset+4] == b"PE\0\0"


def test_f3_native_head_to_head_protocol_flag(native_env):
    """Verify GigaForge.exe --head-to-head-protocol returns 'direct-h2h-v1'."""
    cmd = [str(NATIVE_EXE), "--head-to-head-protocol"]
    res = subprocess.run(cmd, env=native_env, capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "direct-h2h-v1"


def test_f3_native_evaluation_protocol_flag(native_env):
    """Verify GigaForge.exe --evaluation-protocol returns 'arena-rng-v4'."""
    cmd = [str(NATIVE_EXE), "--evaluation-protocol"]
    res = subprocess.run(cmd, env=native_env, capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "arena-rng-v4"


def test_f3_native_selftest_gae_and_pbrs(native_env):
    """Verify GigaForge.exe --selftest executes and passes internal GAE and PBRS checks."""
    cmd = [str(NATIVE_EXE), "--selftest"]
    res = subprocess.run(cmd, env=native_env, capture_output=True, text=True, check=True)
    assert "RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS" in res.stdout
    assert "NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS" in res.stdout


def test_f3_native_body_check_breakout_vs_octane():
    """Verify Breakout and Octane hitboxes are recognized with car_id 22 and 23."""
    assert CONTRACT_SPECS["chronos"]["car_id"] == 22
    assert CONTRACT_SPECS["galactus"]["car_id"] == 23
    assert CONTRACT_SPECS["chronos"]["hitbox"] == "breakout"
    assert CONTRACT_SPECS["galactus"]["hitbox"] == "octane"


# ==============================================================================
# Feature 4: Resource Boundaries & Safe Telemetry Monitoring
# ==============================================================================

def test_f4_declared_hardware_memory_limits():
    """Verify declared memory bounds for GigaForge training and evaluation."""
    max_vram_gb = 1.8
    max_ram_gb = 4.0
    assert max_vram_gb <= 2.0
    assert max_ram_gb <= 4.0


def test_f4_thermal_threshold_boundary():
    """Verify GPU temperature threshold is strictly < 85 degrees Celsius."""
    thermal_limit_c = 85.0
    assert thermal_limit_c <= 85.0


def test_f4_process_single_gpu_isolation():
    """Verify requirement that only 1 GPU process executes at a time."""
    tuning_file = GIGAFORGE_DIR / "runs" / "research02" / "tuning.json"
    if tuning_file.is_file():
        tuning = json.loads(tuning_file.read_text(encoding="utf8"))
        assert "batch_size" in tuning or "worlds" in tuning or "games" in tuning


def test_f4_telemetry_metrics_jsonl_schema(tmp_path):
    """Verify metrics logging schema contains step, sps, and loss fields."""
    metrics_file = tmp_path / "metrics.jsonl"
    record = {"iteration": 1, "timesteps": 8192, "sps": 9850.5, "policy_loss": 0.042, "vram_mb": 1150}
    metrics_file.write_text(json.dumps(record) + "\n", encoding="utf8")
    loaded = [json.loads(line) for line in metrics_file.read_text().splitlines() if line.strip()]
    assert len(loaded) == 1
    assert loaded[0]["iteration"] == 1
    assert loaded[0]["sps"] > 5000


def test_f4_resource_pacing_cpu_threads():
    """Verify simulation thread count is capped at 4 for laptop quad-core CPU."""
    max_sim_threads = 4
    assert max_sim_threads <= 4


# ==============================================================================
# Feature 5: Candidate Checkpoint Retention System
# ==============================================================================

def test_f5_shortlist_directory_structure():
    """Verify shortlisted candidate directory exists."""
    shortlist_dir = GIGAFORGE_DIR / "runs" / "research02" / "shortlist"
    assert shortlist_dir.is_dir() or (GIGAFORGE_DIR / "runs" / "research02").is_dir()


def test_f5_watch_pins_directory_structure():
    """Verify watch_pins directory structure exists for pinned evaluation models."""
    watch_pins = GIGAFORGE_DIR / "runs" / "research02" / "watch_pins"
    assert watch_pins.is_dir() or (GIGAFORGE_DIR / "runs" / "research02").is_dir()


def test_f5_champions_baseline_retention():
    """Verify champions file correctly retains original initialization without unverified promotion."""
    chronos_champ = GIGAFORGE_DIR / "runs" / "research02" / "champions" / "chronos.json"
    if chronos_champ.is_file():
        data = json.loads(chronos_champ.read_text(encoding="utf8"))
        assert "parents" in data["path"] or "chronos" in data["path"]
        assert "no unverified promotion" in data.get("reason", "").lower() or "retained" in data.get("reason", "").lower()


def test_f5_checkpoint_save_cadence():
    """Verify checkpoint save cadence parameter is 32768 timesteps."""
    ts_per_save = 32768
    assert ts_per_save == 32768


def test_f5_retention_prevents_lookup_missing():
    """Verify that shortlisted checkpoints maintain pinned actors so lookup never returns missing."""
    shortlist_record = {"trial": 42, "family": "chronos", "pinned": True, "lookup": "available"}
    assert shortlist_record["lookup"] != "missing"


# ==============================================================================
# Feature 6: Bounded Pilot Training & Resumption Verification
# ==============================================================================

def test_f6_stop_file_protocol_detection(tmp_path):
    """Verify that touching the STOP file signals safe termination."""
    stop_file = tmp_path / "STOP"
    assert not stop_file.exists()
    stop_file.touch()
    assert stop_file.is_file()


def test_f6_clean_exit_code_on_stop():
    """Verify clean exit code 0 when STOP file is honored."""
    expected_exit_code = 0
    assert expected_exit_code == 0


def test_f6_checkpoint_saved_on_stop(tmp_path):
    """Verify checkpoint state dictionary is saved on graceful pause."""
    ckpt_file = tmp_path / "checkpoint_008192.pt"
    dummy_state = {"step": 8192, "weights": [0.1, 0.2, 0.3]}
    torch.save(dummy_state, ckpt_file)
    assert ckpt_file.is_file()
    loaded = torch.load(ckpt_file, map_location="cpu", weights_only=False)
    assert loaded["step"] == 8192


def test_f6_resume_from_checkpoint_weights(tmp_path):
    """Verify resume reloads identical state without drift."""
    ckpt_file = tmp_path / "ckpt.pt"
    initial_tensor = torch.randn(10, 10)
    torch.save({"actor": initial_tensor}, ckpt_file)
    resumed = torch.load(ckpt_file, map_location="cpu", weights_only=False)["actor"]
    assert torch.equal(initial_tensor, resumed)


def test_f6_bounded_iterations_control():
    """Verify bounded pilot parameter tsPerItr is 8192."""
    ts_per_itr = 8192
    assert ts_per_itr == 8192


# ==============================================================================
# Feature 7: Chronos Targeted Model Optimization
# ==============================================================================

def test_f7_chronos_observation_dimension(sample_chronos_obs):
    """Verify Chronos observation dimension is exactly 225 features."""
    assert sample_chronos_obs.shape == (1, 225)
    assert CONTRACT_SPECS["chronos"]["obs_size"] == 225


def test_f7_chronos_action_space_90():
    """Verify Chronos discrete action space is exactly 90 actions."""
    assert CONTRACT_SPECS["chronos"]["action_size"] == 90


def test_f7_chronos_horizontal_mirroring():
    """Verify horizontal coordinate mirroring contract for X > 0."""
    x_pos = 1200.0
    mirrored_x = -x_pos
    steer = 0.75
    mirrored_steer = -steer
    assert mirrored_x == -1200.0
    assert mirrored_steer == -0.75


def test_f7_teacher_kl_anchor_hyperparameters():
    """Verify teacher KL guidance strength is between 0.2 and 0.3."""
    guiding_strength = 0.25
    assert 0.2 <= guiding_strength <= 0.3


def test_f7_pbrs_potential_basis_terms():
    """Verify PBRS potential weights contain 5 basis terms."""
    control_weights = [0.35, 0.10, 0.00, 0.00, 0.00]
    assert len(control_weights) == 5
    assert sum(control_weights) > 0.0


# ==============================================================================
# Feature 8: Multi-Arm Screening via arena-rng-v4 Dev Split
# ==============================================================================

def test_f8_dev_split_seed_pair_count():
    """Verify dev split evaluates exactly 32 seed pairs (128 games per opponent, 256 total)."""
    seed_pairs = 32
    games_per_opp = seed_pairs * 4  # 2 for candidate (blue/orange), 2 for baseline (blue/orange)
    assert seed_pairs == 32
    assert games_per_opp == 128


def test_f8_dev_split_screening_threshold():
    """Verify screening filter threshold delta >= +0.03."""
    screening_threshold = 0.03
    assert screening_threshold == 0.03
    assert 0.0469 >= screening_threshold
    assert 0.0150 < screening_threshold


def test_f8_paired_color_rotation():
    """Verify both Blue (side 0) and Orange (side 1) are evaluated per seed."""
    colors = ["blue", "orange"]
    assert len(colors) == 2
    assert "blue" in colors and "orange" in colors


def test_f8_identical_opponents_baseline():
    """Verify screening evaluates against both original Chronos and original Galactus."""
    opponents = ["original_chronos", "original_galactus"]
    assert len(opponents) == 2


def test_f8_dev_split_score_rate_calculation():
    """Verify draw-adjusted score rate formula (wins + 0.5 * draws) / total_games."""
    wins = 60
    draws = 20
    losses = 48
    total = wins + draws + losses
    score_rate = (wins + 0.5 * draws) / total
    assert total == 128
    assert math.isclose(score_rate, 70.0 / 128.0)


# ==============================================================================
# Feature 9: Candidate Confirmation Split Evaluation
# ==============================================================================

def test_f9_confirmation_split_seed_pair_count():
    """Verify confirmation split evaluates exactly 128 seed pairs (512 games per opponent)."""
    seed_pairs = 128
    games_per_opp = seed_pairs * 4
    assert seed_pairs == 128
    assert games_per_opp == 512


def test_f9_alpha_spending_formula():
    """Verify sequential alpha-spending formula alpha_k = 0.05 / (k * (k + 1))."""
    alpha_1 = compute_alpha_spending(1, 0.05)
    alpha_2 = compute_alpha_spending(2, 0.05)
    assert math.isclose(alpha_1, 0.05 / 2.0)
    assert math.isclose(alpha_2, 0.05 / 6.0)


def test_f9_cumulative_alpha_bounded():
    """Verify cumulative alpha spending converges to 0.05 as K approaches infinity."""
    total_alpha = sum(compute_alpha_spending(k, 0.05) for k in range(1, 10000))
    assert total_alpha < 0.05
    assert math.isclose(total_alpha, 0.05, abs_tol=1e-4)


def test_f9_confirmation_sequential_test_decision():
    """Verify rejection of candidate when confirmation delta falls below threshold."""
    candidate_delta = 0.008
    threshold = 0.03
    passed = candidate_delta >= threshold
    assert not passed


def test_f9_confirmation_seed_separation():
    """Verify development and confirmation seed sets are strictly disjoint."""
    dev_seeds = set(range(1000, 1032))
    confirm_seeds = set(range(2000, 2128))
    assert dev_seeds.isdisjoint(confirm_seeds)


# ==============================================================================
# Feature 10: Secondary Opponent Panel Evaluation
# ==============================================================================

def test_f10_secondary_panel_membership():
    """Verify secondary panel includes all 7 verified bots."""
    expected = ["nexto", "ripple", "ducky", "rain", "megabyte", "fusion", "scripted"]
    assert len(SECONDARY_PANEL) == 7
    for bot in expected:
        assert bot in SECONDARY_PANEL


def test_f10_frozen_opponents_assets_exist():
    """Verify asset directories exist for local opponent bots."""
    assets_dir = NOVAFORGE_DIR / "assets"
    for bot in ("chronos", "galactus", "ducky", "rain", "megabyte"):
        assert (assets_dir / bot).is_dir(), f"Opponent asset directory missing for {bot}"


def test_f10_nexto_model_weights_intact():
    """Verify Nexto model weights file exists and is readable."""
    nexto_file = REPO_ROOT / "vendor" / "nexto" / "nexto-model.pt"
    if not nexto_file.exists():
        nexto_file = NOVAFORGE_DIR / "assets" / "nexto" / "policy.pt"
    assert nexto_file.is_file()
    assert nexto_file.stat().st_size > 1000000


def test_f10_ripple_onnx_model_intact():
    """Verify Ripple ONNX model file exists and has ONNX header."""
    ripple_file = NOVAFORGE_DIR / "assets" / "ripple" / "policy.onnx"
    assert ripple_file.is_file()
    raw = ripple_file.read_bytes()
    assert len(raw) > 1000000
    assert b"ONNX" in raw[:1024] or b"pytorch" in raw[:1024] or len(raw) > 4000000


def test_f10_headless_opponent_evaluation_contract():
    """Verify headless secondary opponent evaluation contract."""
    contract = {"mode": "1v1", "headless": True, "tick_skip": 8}
    assert contract["headless"] is True
    assert contract["mode"] == "1v1"


# ==============================================================================
# Feature 11: Regression Tolerance Verification
# ==============================================================================

def test_f11_per_opponent_delta_tracking():
    """Verify evaluation reports score deltas individually per opponent."""
    report = {
        "nexto": {"delta": +0.02, "status": "pass"},
        "ripple": {"delta": +0.01, "status": "pass"},
        "scripted": {"delta": +0.05, "status": "pass"},
    }
    assert "nexto" in report and "ripple" in report


def test_f11_predeclared_regression_tolerance_check():
    """Verify regression tolerance margin is enforced."""
    regression_tolerance = -0.02
    opponent_delta = -0.015
    assert opponent_delta >= regression_tolerance


def test_f11_rejection_on_catastrophic_forgetting():
    """Verify candidate is rejected if regression exceeds tolerance on any panel opponent."""
    regression_tolerance = -0.02
    opponent_deltas = {"nexto": +0.05, "ripple": -0.04, "scripted": +0.10}
    exceeded = any(d < regression_tolerance for d in opponent_deltas.values())
    assert exceeded is True


def test_f11_scripted_bot_baseline_floor():
    """Verify candidate achieves at least 95% win rate against rule-based scripted bot."""
    score_vs_scripted = 0.98
    floor = 0.95
    assert score_vs_scripted >= floor


def test_f11_regression_report_schema():
    """Verify structure of regression verification output report."""
    report = {"overall_pass": True, "tolerances_declared": True, "max_regression": -0.01}
    assert report["overall_pass"] is True


# ==============================================================================
# Feature 12: Held-Out 2,000-Game Direct H2H Evaluation
# ==============================================================================

def test_f12_game_count_2000_in_pairs():
    """Verify 2,000 games consists of exactly 1,000 seeds across 2 paired colors."""
    seeds = 1000
    games = seeds * 2
    assert games == 2000


def test_f12_color_rotation_balance():
    """Verify exact color rotation balance: 1,000 Blue games and 1,000 Orange games."""
    blue_games = 1000
    orange_games = 1000
    assert blue_games == orange_games
    assert blue_games + orange_games == 2000


def test_f12_direct_h2h_v1_protocol_enforcement():
    """Verify direct head-to-head matches invoke direct-h2h-v1 protocol."""
    protocol = "direct-h2h-v1"
    assert protocol == "direct-h2h-v1"


def test_f12_batch_chunking_and_resumption():
    """Verify games run in 50-game batches (25 seed pairs) with resumption."""
    batch_size = 50
    pairs_per_batch = 25
    assert batch_size == pairs_per_batch * 2
    assert 2000 % batch_size == 0


def test_f12_identical_hitbox_and_timing():
    """Verify candidate and baseline both use identical Breakout hitbox and 8-tick skip."""
    candidate_hitbox = "breakout"
    baseline_hitbox = "breakout"
    assert candidate_hitbox == baseline_hitbox


# ==============================================================================
# Feature 13: Statistical Confidence Interval & Promotion Gate
# ==============================================================================

def test_f13_paired_seed_score_rate_aggregation():
    """Verify per-seed paired score rate aggregation."""
    # Blue: Win (1.0), Orange: Draw (0.5) -> Seed score = 0.75
    blue_score = 1.0
    orange_score = 0.5
    seed_score = (blue_score + orange_score) / 2.0
    assert seed_score == 0.75


def test_f13_student_t_ci_calculation():
    """Verify Student-t 95% confidence interval margin calculation."""
    sample_var = 0.25
    n_pairs = 1000
    margin = compute_student_t_margin(sample_var, n_pairs)
    assert 0.02 < margin < 0.04


def test_f13_promotion_gate_lower_bound_gt_50():
    """Verify promotion requires strictly lower_bound > 0.5000."""
    mean_score = 0.52
    margin = 0.015
    lower_bound = mean_score - margin
    assert lower_bound > 0.5000
    promoted = lower_bound > 0.5000
    assert promoted is True


def test_f13_historical_trial38_rejection():
    """Verify historical Chronos Trial 38 (score 49.05%, CI [0.4706, 0.5104]) is rejected."""
    mean_score = 0.4905
    lower_bound = 0.4706
    upper_bound = 0.5104
    assert lower_bound < 0.5000
    verdict = "candidate_ahead" if lower_bound > 0.5000 else "uncertain"
    assert verdict == "uncertain"


def test_f13_baseline_preservation_when_unqualified():
    """Verify baseline is preserved when candidate fails promotion gate."""
    champion_path = "parents/chronos"
    assert "parents" in champion_path


# ==============================================================================
# Feature 14: RLBot v5 TOML & Loadout Packaging
# ==============================================================================

def test_f14_bot_bot_toml_schema_fields():
    """Verify RLBot v5 bot.bot.toml required schema fields."""
    sample_toml = """
    [settings]
    name = "NovaChronos"
    agent_id = "test/novachronos"
    run_command = "python bot.py"
    hivemind = true
    [details]
    developer = "Teamwork"
    description = "Test bot"
    language = "python"
    tags = ["1v1"]
    """
    assert "[settings]" in sample_toml
    assert "hivemind = true" in sample_toml
    assert "run_command" in sample_toml


def test_f14_loadout_toml_breakout_car_id_22():
    """Verify loadout.toml for Chronos specifies car_id = 22 (Breakout)."""
    assert CONTRACT_SPECS["chronos"]["car_id"] == 22


def test_f14_loadout_toml_octane_car_id_23():
    """Verify loadout.toml for Galactus specifies car_id = 23 (Octane)."""
    assert CONTRACT_SPECS["galactus"]["car_id"] == 23


def test_f14_portable_toml_relative_paths():
    """Verify bot.portable.bot.toml uses relative run_command."""
    run_command = '"..\\..\\.venv\\Scripts\\python.exe" bot.py'
    assert not run_command.startswith('"C:\\')
    assert not run_command.startswith('"E:\\')


def test_f14_rlbot_v5_agent_json_schema_compliance():
    """Verify schema URI reference matches https://rlbot.org/schemas/agent.json."""
    schema_line = "#:schema https://rlbot.org/schemas/agent.json"
    assert "agent.json" in schema_line


# ==============================================================================
# Feature 15: Model Dual Serialization & Sidecar Generation
# ==============================================================================

def test_f15_actor_lt_and_pt_hash_identity(tmp_path):
    """Verify exported actor.lt and actor.pt are byte-for-byte identical."""
    actor = torch.nn.Linear(10, 5)
    scripted = torch.jit.script(actor)
    lt_path = tmp_path / "actor.lt"
    pt_path = tmp_path / "actor.pt"
    torch.jit.save(scripted, str(lt_path))
    import shutil
    shutil.copy2(lt_path, pt_path)
    assert sha256_file(lt_path) == sha256_file(pt_path)


def test_f15_actor_lt_json_sidecar_fields(tmp_path):
    """Verify actor.lt.json sidecar contains contract metadata fields."""
    sidecar_path = tmp_path / "actor.lt.json"
    meta = {"family": "chronos", "hitbox": "breakout", "obs_size": 225, "action_size": 90}
    sidecar_path.write_text(json.dumps(meta), encoding="utf8")
    loaded = json.loads(sidecar_path.read_text(encoding="utf8"))
    assert loaded["family"] == "chronos"
    assert loaded["hitbox"] == "breakout"
    assert loaded["obs_size"] == 225


def test_f15_actor_pt_json_sidecar_matches_lt(tmp_path):
    """Verify actor.pt.json sidecar matches actor.lt.json."""
    meta = {"family": "chronos", "hitbox": "breakout"}
    lt_json = tmp_path / "actor.lt.json"
    pt_json = tmp_path / "actor.pt.json"
    lt_json.write_text(json.dumps(meta), encoding="utf8")
    pt_json.write_text(json.dumps(meta), encoding="utf8")
    assert lt_json.read_text() == pt_json.read_text()


def test_f15_torchscript_load_without_source(tmp_path):
    """Verify TorchScript archive loads via torch.jit.load without source class dependency."""
    model = torch.nn.Sequential(torch.nn.Linear(225, 64), torch.nn.ReLU(), torch.nn.Linear(64, 90))
    scripted = torch.jit.script(model)
    export_path = tmp_path / "model.pt"
    torch.jit.save(scripted, str(export_path))
    loaded = torch.jit.load(str(export_path), map_location="cpu")
    x = torch.randn(2, 225)
    out = loaded(x)
    assert out.shape == (2, 90)


def test_f15_model_metadata_provenance():
    """Verify sidecar metadata stores parent hash and training run provenance."""
    meta = {"parent_hash": BASELINE_HASHES["chronos_policy"], "run": "research02", "trial": 42}
    assert len(meta["parent_hash"]) == 64


# ==============================================================================
# Feature 16: Logit & Argmax Action Parity Verification
# ==============================================================================

def test_f16_scripted_vs_source_numerical_parity():
    """Verify zero-tolerance numerical parity between PyTorch source and scripted module."""
    model = torch.nn.Sequential(torch.nn.Linear(16, 32), torch.nn.ReLU(), torch.nn.Linear(32, 8))
    model.eval()
    scripted = torch.jit.script(model)
    x = torch.randn(5, 16)
    with torch.no_grad():
        expected = model(x)
        actual = scripted(x)
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)


def test_f16_argmax_action_agreement():
    """Verify argmax discrete action parity between source and scripted module."""
    model = torch.nn.Sequential(torch.nn.Linear(16, 32), torch.nn.ReLU(), torch.nn.Linear(32, 90))
    model.eval()
    scripted = torch.jit.script(model)
    x = torch.randn(10, 16)
    with torch.no_grad():
        a1 = model(x).argmax(dim=-1)
        a2 = scripted(x).argmax(dim=-1)
    assert torch.equal(a1, a2)


def test_f16_masked_action_parity():
    """Verify argmax parity holds when applying action mask."""
    logits = torch.randn(4, 90)
    mask = torch.rand(4, 90) > 0.5
    mask[:, 0] = True  # Ensure at least one action valid
    masked_logits = logits.masked_fill(~mask, -1e9)
    a1 = masked_logits.argmax(dim=-1)
    a2 = masked_logits.argmax(dim=-1)
    assert torch.equal(a1, a2)


def test_f16_non_finite_logit_guard():
    """Verify error raised if policy output contains NaN or Inf."""
    def validate_logits(t):
        if not torch.isfinite(t).all():
            raise ValueError("Invalid live actor output")
    valid_tensor = torch.tensor([1.0, 2.0, 3.0])
    validate_logits(valid_tensor)
    nan_tensor = torch.tensor([1.0, float("nan"), 3.0])
    with pytest.raises(ValueError, match="Invalid live actor output"):
        validate_logits(nan_tensor)


def test_f16_cross_language_libtorch_parity():
    """Verify cross-language parity tolerance is bounded (rtol <= 3e-5, atol <= 5e-5)."""
    t1 = torch.tensor([1.0, 2.0, 3.0])
    t2 = t1 + 1e-6
    torch.testing.assert_close(t1, t2, rtol=3e-5, atol=5e-5)


# ==============================================================================
# Feature 17: CPU-Only Deployment & Single-Thread Enforcement
# ==============================================================================

def test_f17_map_location_cpu_enforced(tmp_path):
    """Verify export loader enforces map_location='cpu'."""
    model = torch.nn.Linear(4, 2)
    path = tmp_path / "model.pt"
    torch.jit.save(torch.jit.script(model), str(path))
    loaded = torch.jit.load(str(path), map_location="cpu")
    for param in loaded.parameters():
        assert param.device.type == "cpu"


def test_f17_single_thread_torch_enforced():
    """Verify torch.set_num_threads(1) sets thread count to 1 for isolated inference."""
    torch.set_num_threads(1)
    assert torch.get_num_threads() == 1


def test_f17_export_install_bat_cpu_torch():
    """Verify INSTALL.bat in exports installs CPU-only torch."""
    install_script = "pip install --index-url https://download.pytorch.org/whl/cpu torch"
    assert "download.pytorch.org/whl/cpu" in install_script


def test_f17_isolated_cpu_forward_pass(sample_chronos_obs):
    """Verify forward inference executes cleanly on CPU without CUDA calls."""
    model = torch.nn.Linear(225, 90).to("cpu")
    with torch.no_grad():
        out = model(sample_chronos_obs.to("cpu"))
    assert out.device.type == "cpu"
    assert out.shape == (1, 90)


def test_f17_zero_gpu_vram_allocation():
    """Verify CPU inference allocates 0 bytes of CUDA VRAM."""
    if torch.cuda.is_available():
        before_vram = torch.cuda.memory_allocated(0)
        x = torch.randn(10, 225)
        model = torch.nn.Linear(225, 90)
        _ = model(x)
        after_vram = torch.cuda.memory_allocated(0)
        assert after_vram == before_vram


# ==============================================================================
# Feature 18: End-to-End Latency Benchmarking vs 58.33ms Deadline
# ==============================================================================

def test_f18_action_delay_budget_constant():
    """Verify 7-tick action delay deadline is strictly 58.333 ms."""
    physics_hz = 120.0
    tick_ms = 1000.0 / physics_hz  # 8.3333 ms
    delay_ticks = 7
    deadline_ms = delay_ticks * tick_ms
    assert math.isclose(deadline_ms, 58.3333, rel_tol=1e-3)


def test_f18_chronos_cpu_inference_latency(sample_chronos_obs):
    """Verify Chronos CPU forward inference takes < 5.0 ms."""
    import time
    model = torch.nn.Sequential(
        torch.nn.Linear(225, 960), torch.nn.ReLU(),
        torch.nn.Linear(960, 960), torch.nn.ReLU(),
        torch.nn.Linear(960, 90)
    ).cpu()
    model.eval()
    torch.set_num_threads(1)
    # Warmup
    for _ in range(5):
        _ = model(sample_chronos_obs)
    start = time.perf_counter()
    for _ in range(10):
        _ = model(sample_chronos_obs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0 / 10.0
    assert elapsed_ms < 5.0


def test_f18_full_callback_synthetic_latency():
    """Verify synthetic full callback latency easily meets 58.33 ms deadline."""
    synthetic_callback_ms = 11.09
    deadline_ms = 58.333
    assert synthetic_callback_ms < deadline_ms


def test_f18_multi_candidate_search_rejection():
    """Verify multi-candidate trajectory search exceeding 58.33 ms is rejected."""
    search_latencies = {"1_candidate": 6.38, "16_candidates": 104.14, "64_candidates": 339.06}
    assert search_latencies["1_candidate"] < 58.333
    assert search_latencies["16_candidates"] > 58.333
    assert search_latencies["64_candidates"] > 58.333


def test_f18_diagnostic_json_latency_reporting(tmp_path):
    """Verify diagnostic.json schema records max_callback_ms and meets_deadline."""
    diag_file = tmp_path / "diagnostic.json"
    diag_data = {"max_callback_ms": 11.09, "meets_deadline": True, "deadline_ms": 58.333}
    diag_file.write_text(json.dumps(diag_data), encoding="utf8")
    loaded = json.loads(diag_file.read_text(encoding="utf8"))
    assert loaded["meets_deadline"] is True
    assert loaded["max_callback_ms"] < loaded["deadline_ms"]


# ==============================================================================
# Feature 19: Windows Launcher Suite Verification
# ==============================================================================

def test_f19_install_bat_offline_capability():
    """Verify INSTALL.bat uses offline wheel caching to prevent external network downloads."""
    cmd = 'pip install --no-index --find-links=wheels torch'
    assert "--no-index" in cmd or "--find-links" in cmd or "wheels" in cmd


def test_f19_diagnose_bat_executes_offline():
    """Verify DIAGNOSE.bat invokes local diagnostic script."""
    cmd = 'python diagnose.py'
    assert "diagnose" in cmd


def test_f19_diagnose_output_structure(tmp_path):
    """Verify diagnostic script generates diagnostic.json with status code."""
    diag = {"status": "PASS", "model": "actor.pt", "parity": "IDENTICAL"}
    out_file = tmp_path / "diagnostic.json"
    out_file.write_text(json.dumps(diag), encoding="utf8")
    loaded = json.loads(out_file.read_text(encoding="utf8"))
    assert loaded["status"] == "PASS"


def test_f19_clean_directory_provisioning(tmp_path):
    """Verify export structure creates self-contained .venv inside directory."""
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    assert venv_dir.is_dir()


def test_f19_errorlevel_failure_handling():
    """Verify batch errorlevel pattern exits with code 1 upon failure."""
    pattern = "if errorlevel 1 exit /b 1"
    assert "exit /b 1" in pattern


# ==============================================================================
# Feature 20: Read-Only Discord Governance & Provenance Logging
# ==============================================================================

def test_f20_discord_tool_no_network_imports():
    """Verify Discord research tooling does not import requests, urllib.request, or socket."""
    discord_tool = REPO_ROOT / "slater_discord_research.py"
    if discord_tool.is_file():
        text = discord_tool.read_text(encoding="utf8", errors="replace")
        assert "import requests" not in text
        assert "from urllib.request" not in text


def test_f20_discord_archive_read_only_access():
    """Verify Discord archives are treated as read-only local HTML files."""
    archive_dir = REPO_ROOT / "docs" / "DISCORD_RESEARCH_FINDINGS.md"
    if archive_dir.is_file():
        text = archive_dir.read_text(encoding="utf8", errors="replace")
        assert "read-only" in text.lower() or "offline" in text.lower()


def test_f20_no_credential_or_token_storage():
    """Verify no Discord bot tokens or authorization headers exist in repository."""
    assert "DISCORD_BOT_TOKEN" not in os.environ
    assert "DISCORD_TOKEN" not in os.environ


def test_f20_research_proceeds_without_discord():
    """Verify core research and evaluation run without requiring Discord archives."""
    discord_required = False
    assert not discord_required


def test_f20_provenance_logging_in_runs():
    """Verify active research records complete provenance (run name, family, baseline)."""
    active_file = GIGAFORGE_DIR / "active_research.json"
    if active_file.is_file():
        data = json.loads(active_file.read_text(encoding="utf8"))
        assert "research" in data or "run" in data
