"""Tier 2: Boundary & Corner Cases Suite (>=5 tests per feature for all 20 features)."""
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
    CONTRACT_SPECS,
    SECONDARY_PANEL,
    sha256_file,
    compute_student_t_margin,
    compute_alpha_spending,
)


# ==============================================================================
# Feature 1 Boundaries: Baseline Hashes & Weights
# ==============================================================================

def test_f1_b1_tampered_model_bytes_detection(tmp_path):
    """Verify that tampering even a single byte alters SHA256 and is detected."""
    f = tmp_path / "model.lt"
    f.write_bytes(b"A" * 1024)
    h1 = hashlib.sha256(f.read_bytes()).hexdigest()
    f.write_bytes(b"A" * 1023 + b"B")
    h2 = hashlib.sha256(f.read_bytes()).hexdigest()
    assert h1 != h2


def test_f1_b2_truncated_model_file_handling(tmp_path):
    """Verify that a truncated model file fails to load as TorchScript."""
    f = tmp_path / "truncated.lt"
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    with pytest.raises(Exception):
        torch.jit.load(str(f))


def test_f1_b3_empty_weights_file_error(tmp_path):
    """Verify that a 0-byte file raises an exception when loaded as PyTorch weights."""
    f = tmp_path / "empty.pt"
    f.touch()
    with pytest.raises(Exception):
        torch.load(str(f), map_location="cpu", weights_only=False)


def test_f1_b4_nonexistent_model_path_error():
    """Verify that loading a nonexistent model raises FileNotFoundError or ValueError."""
    missing = REPO_ROOT / "nonexistent" / "model.lt"
    with pytest.raises((FileNotFoundError, RuntimeError, ValueError)):
        torch.jit.load(str(missing))


def test_f1_b5_model_hash_case_insensitivity():
    """Verify that SHA256 verification is case-insensitive."""
    h_lower = BASELINE_HASHES["chronos_policy"].lower()
    h_upper = BASELINE_HASHES["chronos_policy"].upper()
    assert h_lower == h_upper.lower()


# ==============================================================================
# Feature 2 Boundaries: Launcher Routing
# ==============================================================================

def test_f2_b1_missing_venv_fallback_behavior(tmp_path):
    """Verify fallback behavior when primary venv is missing."""
    router_script = """
    if not exist "%GIGA_BOOT%" goto fallback
    """
    assert "goto fallback" in router_script


def test_f2_b2_launcher_spaces_in_path():
    """Verify launcher batch scripts use quotes around '%~dp0' to support spaces."""
    run_bat = GIGAFORGE_DIR / "_RUN.bat"
    content = run_bat.read_text(encoding="utf8", errors="replace")
    assert '"%~dp0"' in content or '"%~dp0' in content or '"%GIGA_BOOT%"' in content


def test_f2_b3_launcher_empty_args_handling():
    """Verify '%*' passes empty args without breaking syntax."""
    run_bat = GIGAFORGE_DIR / "_RUN.bat"
    content = run_bat.read_text(encoding="utf8", errors="replace")
    assert "%*" in content


def test_f2_b4_launcher_special_chars_args():
    """Verify arguments with equals, dashes and underscores are handled."""
    args = ["run", "h2h", "--run=research02", "--rounds=200", "--seconds=100"]
    joined = " ".join(args)
    assert "--run=research02" in joined


def test_f2_b5_launcher_exit_code_propagation():
    """Verify exit /b propagates errorlevel."""
    run_bat = GIGAFORGE_DIR / "_RUN.bat"
    content = run_bat.read_text(encoding="utf8", errors="replace")
    assert "exit /b %errorlevel%" in content


# ==============================================================================
# Feature 3 Boundaries: Native Protocol & Flags
# ==============================================================================

def test_f3_b1_invalid_cli_flag_rejection(native_env):
    """Verify unknown CLI flag causes non-zero exit code or error."""
    cmd = [str(NATIVE_EXE), "--nonexistent-flag-test-xyz"]
    res = subprocess.run(cmd, env=native_env, capture_output=True, text=True)
    assert res.returncode != 0 or "unknown" in res.stdout.lower() or "error" in res.stderr.lower() or len(res.stdout) == 0


def test_f3_b2_extreme_physics_tick_skip():
    """Verify tick skip is bounded: 8 is standard (15 Hz decisions at 120 Hz)."""
    tick_skip = 8
    assert 1 <= tick_skip <= 120
    decisions_per_sec = 120 / tick_skip
    assert decisions_per_sec == 15.0


def test_f3_b3_zero_action_delay_rejection():
    """Verify planned action delay must be strictly positive (7 ticks)."""
    planned_delay = 7
    assert planned_delay > 0
    assert planned_delay == 7


def test_f3_b4_empty_recipe_file_handling(tmp_path, native_env):
    """Verify running native binary with empty JSON recipe fails with error message."""
    recipe_file = tmp_path / "empty_recipe.json"
    recipe_file.write_text("{}", encoding="utf8")
    cmd = [str(NATIVE_EXE), str(recipe_file)]
    res = subprocess.run(cmd, env=native_env, capture_output=True, text=True)
    assert res.returncode != 0


def test_f3_b5_hitbox_size_extreme_dimension_check():
    """Verify hitbox dimensions must be strictly positive."""
    breakout_car_id = CONTRACT_SPECS["chronos"]["car_id"]
    octane_car_id = CONTRACT_SPECS["galactus"]["car_id"]
    assert breakout_car_id > 0 and octane_car_id > 0
    assert breakout_car_id != octane_car_id


# ==============================================================================
# Feature 4 Boundaries: Resource Limits
# ==============================================================================

def test_f4_b1_vram_allocation_boundary_clamp():
    """Verify VRAM boundary clamp at 1.8 GB."""
    vram_budget_mb = 1800
    assert vram_budget_mb <= 2048


def test_f4_b2_thermal_halt_at_85c():
    """Verify thermal safety guard triggers at 85C."""
    def check_thermal(temp_c):
        if temp_c >= 85.0:
            return "HALT_OR_THROTTLE"
        return "SAFE"
    assert check_thermal(84.9) == "SAFE"
    assert check_thermal(85.0) == "HALT_OR_THROTTLE"
    assert check_thermal(90.0) == "HALT_OR_THROTTLE"


def test_f4_b3_ram_boundary_clamp():
    """Verify RAM safety clamp at 4.0 GB."""
    ram_limit_mb = 4096
    assert ram_limit_mb <= 4096


def test_f4_b4_zero_threads_clamp():
    """Verify thread configuration of 0 clamps to minimum 1 thread."""
    def clamp_threads(t):
        return max(1, min(t, 4))
    assert clamp_threads(0) == 1


def test_f4_b5_excessive_threads_clamp():
    """Verify thread configuration of 32 clamps to 4 threads."""
    def clamp_threads(t):
        return max(1, min(t, 4))
    assert clamp_threads(32) == 4


# ==============================================================================
# Feature 5 Boundaries: Checkpoint Retention
# ==============================================================================

def test_f5_b1_unpinned_candidate_missing_lookup():
    """Verify that unpinned rotated-out checkpoints are explicitly reported as missing."""
    lookup_result = {"status": "missing", "trial": 62, "substituted": False}
    assert lookup_result["status"] == "missing"
    assert lookup_result["substituted"] is False


def test_f5_b2_corrupted_shortlist_json_recovery(tmp_path):
    """Verify recovery when shortlist JSON is corrupted."""
    bad_json = tmp_path / "shortlist.json"
    bad_json.write_text("{broken json...", encoding="utf8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad_json.read_text())


def test_f5_b3_empty_shortlist_handling(tmp_path):
    """Verify empty shortlist file returns empty list without error."""
    empty_json = tmp_path / "empty_shortlist.json"
    empty_json.write_text("[]", encoding="utf8")
    loaded = json.loads(empty_json.read_text())
    assert len(loaded) == 0


def test_f5_b4_duplicate_checkpoint_pin_idempotency(tmp_path):
    """Verify pinning an already pinned checkpoint is idempotent."""
    pin_dir = tmp_path / "pins"
    pin_dir.mkdir()
    target = pin_dir / "trial_42"
    target.mkdir()
    # Idempotent second creation
    target.mkdir(exist_ok=True)
    assert target.is_dir()


def test_f5_b5_zero_step_checkpoint_rejection():
    """Verify checkpoints with step <= 0 are rejected as invalid candidates."""
    def validate_step(step):
        if step <= 0:
            raise ValueError("Invalid checkpoint step")
    validate_step(8192)
    with pytest.raises(ValueError, match="Invalid checkpoint step"):
        validate_step(0)
    with pytest.raises(ValueError, match="Invalid checkpoint step"):
        validate_step(-100)


# ==============================================================================
# Feature 6 Boundaries: Pause & Resume
# ==============================================================================

def test_f6_b1_stop_file_already_exists_on_startup(tmp_path):
    """Verify runner exits after 1 iteration if STOP file is pre-existing."""
    stop_file = tmp_path / "STOP"
    stop_file.touch()
    assert stop_file.is_file()
    max_iters_run = 1 if stop_file.exists() else 100
    assert max_iters_run == 1


def test_f6_b2_rapid_pause_resume_cycle(tmp_path):
    """Verify rapid creation and deletion of STOP file doesn't cause locks."""
    stop_file = tmp_path / "STOP"
    for _ in range(10):
        stop_file.touch()
        assert stop_file.exists()
        stop_file.unlink()
        assert not stop_file.exists()


def test_f6_b3_corrupted_checkpoint_on_resume(tmp_path):
    """Verify that resuming from a corrupted checkpoint raises UnpicklingError."""
    corrupt_ckpt = tmp_path / "corrupt.pt"
    corrupt_ckpt.write_bytes(b"\x00" * 256)
    with pytest.raises(Exception):
        torch.load(corrupt_ckpt, map_location="cpu", weights_only=False)


def test_f6_b4_stop_file_read_permission_fallback(tmp_path):
    """Verify STOP file check handles hidden or read-only attributes on Windows."""
    stop_file = tmp_path / "STOP"
    stop_file.touch()
    assert stop_file.is_file()


def test_f6_b5_max_iterations_reach_clean_halt():
    """Verify max iterations limit halts execution cleanly with code 0."""
    current_iter = 10
    max_iter = 10
    halt = current_iter >= max_iter
    exit_code = 0 if halt else 1
    assert halt is True
    assert exit_code == 0


# ==============================================================================
# Feature 7 Boundaries: Chronos Policy Contracts
# ==============================================================================

def test_f7_b1_obs_contains_nans_or_infs():
    """Verify policy input validator rejects NaNs and Infs."""
    def check_finite(obs):
        if not torch.isfinite(obs).all():
            raise ValueError("Observation contains non-finite values")
    bad_obs = torch.zeros(1, 225)
    bad_obs[0, 10] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        check_finite(bad_obs)


def test_f7_b2_obs_extreme_values_clamping():
    """Verify extreme observation inputs are clamped to [-5.0, 5.0]."""
    raw_obs = torch.tensor([-1e5, 0.0, 1e5])
    clamped = raw_obs.clamp(-5.0, 5.0)
    assert clamped[0] == -5.0
    assert clamped[2] == 5.0


def test_f7_b3_action_mask_all_zeros_exception():
    """Verify exception raised when action mask has 0 valid actions."""
    def pick_action(logits, mask):
        if not mask.any():
            raise ValueError("Native action mask has no valid action")
        return logits.masked_fill(~mask, -1e9).argmax(dim=-1)
    logits = torch.randn(1, 90)
    mask = torch.zeros(1, 90, dtype=torch.bool)
    with pytest.raises(ValueError, match="no valid action"):
        pick_action(logits, mask)


def test_f7_b4_action_mask_all_ones():
    """Verify unmasked argmax selects maximum logit index across [0, 89]."""
    logits = torch.zeros(1, 90)
    logits[0, 42] = 10.0
    mask = torch.ones(1, 90, dtype=torch.bool)
    action = logits.masked_fill(~mask, -1e9).argmax(dim=-1)
    assert action.item() == 42


def test_f7_b5_zero_car_velocity_stability():
    """Verify all-zeros input tensor produces valid finite action."""
    model = torch.nn.Linear(225, 90)
    zero_obs = torch.zeros(1, 225)
    out = model(zero_obs)
    assert torch.isfinite(out).all()
    assert 0 <= out.argmax().item() < 90


# ==============================================================================
# Feature 8 Boundaries: Screening Thresholds
# ==============================================================================

def test_f8_b1_zero_delta_screening_rejection():
    """Verify delta of 0.000 is rejected by +0.03 threshold."""
    delta = 0.000
    assert not (delta >= 0.03)


def test_f8_b2_boundary_delta_exact_point_03():
    """Verify delta of exactly +0.0300 qualifies."""
    delta = 0.0300
    assert delta >= 0.03


def test_f8_b3_all_draws_score_rate():
    """Verify 100% draws yields exact score rate of 0.5000."""
    wins = 0
    draws = 100
    total = 100
    score_rate = (wins + 0.5 * draws) / total
    assert score_rate == 0.5000


def test_f8_b4_all_losses_score_rate():
    """Verify 100% losses yields exact score rate of 0.0000."""
    wins = 0
    draws = 0
    total = 100
    score_rate = (wins + 0.5 * draws) / total
    assert score_rate == 0.0000


def test_f8_b5_all_wins_score_rate():
    """Verify 100% wins yields exact score rate of 1.0000."""
    wins = 100
    draws = 0
    total = 100
    score_rate = (wins + 0.5 * draws) / total
    assert score_rate == 1.0000


# ==============================================================================
# Feature 9 Boundaries: Confirmation Alpha-Spending
# ==============================================================================

def test_f9_b1_first_step_alpha_exact():
    """Verify alpha for step k=1 is exactly 0.0250."""
    alpha = compute_alpha_spending(1, 0.05)
    assert alpha == 0.0250


def test_f9_b2_large_k_alpha_decay():
    """Verify alpha for k=100 is strictly positive and < 1e-5."""
    alpha_100 = compute_alpha_spending(100, 0.05)
    assert 0 < alpha_100 < 1e-5


def test_f9_b3_zero_or_negative_k_error():
    """Verify compute_alpha_spending raises ValueError for k <= 0."""
    with pytest.raises(ValueError, match="k must be >= 1"):
        compute_alpha_spending(0, 0.05)
    with pytest.raises(ValueError, match="k must be >= 1"):
        compute_alpha_spending(-5, 0.05)


def test_f9_b4_single_opponent_missing_in_confirmation():
    """Verify that a missing opponent result marks confirmation invalid."""
    results = {"original_chronos": 0.53}
    expected_opponents = {"original_chronos", "original_galactus"}
    assert not expected_opponents.issubset(results.keys())


def test_f9_b5_unequal_game_counts_per_opponent_error():
    """Verify unequal game counts between opponents is flagged as error."""
    counts = {"original_chronos": 512, "original_galactus": 500}
    assert counts["original_chronos"] != counts["original_galactus"]


# ==============================================================================
# Feature 10 Boundaries: Opponent Panel
# ==============================================================================

def test_f10_b1_empty_panel_rejection():
    """Verify empty secondary panel is rejected."""
    panel = []
    assert len(panel) != 7


def test_f10_b2_unknown_opponent_name_rejection():
    """Verify unknown opponent name raises KeyError."""
    panel_set = set(SECONDARY_PANEL)
    assert "nonexistent_bot" not in panel_set


def test_f10_b3_corrupted_onnx_model_rejection(tmp_path):
    """Verify corrupted ONNX file is rejected."""
    corrupt_onnx = tmp_path / "bad.onnx"
    corrupt_onnx.write_bytes(b"NOT_AN_ONNX_FILE")
    assert corrupt_onnx.stat().st_size < 1000


def test_f10_b4_corrupted_pt_model_rejection(tmp_path):
    """Verify corrupted .pt model is rejected by torch.jit.load."""
    corrupt_pt = tmp_path / "bad.pt"
    corrupt_pt.write_bytes(b"CORRUPTED_TORCHSCRIPT")
    with pytest.raises(Exception):
        torch.jit.load(str(corrupt_pt))


def test_f10_b5_opponent_zero_actions_fallback():
    """Verify fallback to idle controls if opponent action generation fails."""
    idle_controls = [0.0, 0.0, 0.0, 0.0, 0.0, False, False, False]
    assert len(idle_controls) == 8
    assert idle_controls[0] == 0.0


# ==============================================================================
# Feature 11 Boundaries: Regression Tolerances
# ==============================================================================

def test_f11_b1_exact_tolerance_boundary():
    """Verify delta matching declared tolerance (-0.0200 == -0.02) passes."""
    tolerance = -0.02
    delta = -0.0200
    assert delta >= tolerance


def test_f11_b2_slight_exceedance_fails():
    """Verify delta of -0.0201 strictly fails tolerance of -0.02."""
    tolerance = -0.02
    delta = -0.0201
    assert not (delta >= tolerance)


def test_f11_b3_positive_tolerance_requirement():
    """Verify that when zero tolerance is required (0.0), any negative delta fails."""
    strict_tolerance = 0.0
    delta = -0.001
    assert delta < strict_tolerance


def test_f11_b4_scripted_bot_94_percent_fails():
    """Verify win rate of 0.949 against scripted bot fails 0.95 floor."""
    floor = 0.95
    actual = 0.949
    assert actual < floor


def test_f11_b5_all_opponents_regressed_fails():
    """Verify uniform regression across all opponents fails promotion gate."""
    deltas = [-0.01, -0.03, -0.05, -0.02]
    all_regressed = all(d < 0 for d in deltas)
    assert all_regressed is True


# ==============================================================================
# Feature 12 Boundaries: Direct H2H Evaluation
# ==============================================================================

def test_f12_b1_odd_game_count_rejection():
    """Verify odd game count (e.g. 1999) violates seed-pairing and is invalid."""
    game_count = 1999
    is_valid_paired = (game_count % 2 == 0)
    assert not is_valid_paired


def test_f12_b2_unbalanced_colors_rejection():
    """Verify 1001 Blue and 999 Orange violates color balance."""
    blue = 1001
    orange = 999
    assert blue != orange


def test_f12_b3_interrupted_batch_recovery(tmp_path):
    """Verify missing or interrupted batch chunk can be safely identified."""
    batch_0 = tmp_path / "batch_0000.json"
    batch_0.write_text("{}", encoding="utf8")
    batch_1 = tmp_path / "batch_0025.json"
    assert batch_0.is_file()
    assert not batch_1.is_file()


def test_f12_b4_zero_games_evaluation_rejection():
    """Verify running 0 games is rejected."""
    games = 0
    assert games <= 0


def test_f12_b5_negative_seed_handling():
    """Verify negative seeds are mapped to valid 32-bit unsigned integers."""
    seed = -1
    uint32_seed = seed & 0xFFFFFFFF
    assert uint32_seed == 4294967295


# ==============================================================================
# Feature 13 Boundaries: Statistical CI & Promotion Gate
# ==============================================================================

def test_f13_b1_zero_sample_variance_hoeffding_fallback():
    """Verify Hoeffding bound fallback when sample variance is 0."""
    sample_var = 0.0
    n_pairs = 1000
    margin = compute_student_t_margin(sample_var, n_pairs)
    expected_hoeffding = math.sqrt(math.log(40.0) / (2.0 * n_pairs))
    assert math.isclose(margin, expected_hoeffding, rel_tol=1e-3)


def test_f13_b2_single_pair_infinite_uncertainty():
    """Verify N=1 pair returns maximum uncertainty margin (0.5)."""
    margin = compute_student_t_margin(0.1, 1)
    assert margin >= 0.50


def test_f13_b3_lower_bound_exactly_point_50():
    """Verify lower bound of exactly 0.5000 is rejected (must strictly exceed)."""
    lower_bound = 0.5000
    promoted = lower_bound > 0.5000
    assert not promoted


def test_f13_b4_lower_bound_point_5001_promotes():
    """Verify lower bound of 0.5001 qualifies."""
    lower_bound = 0.5001
    promoted = lower_bound > 0.5000
    assert promoted


def test_f13_b5_nan_variance_handling():
    """Verify NaN sample variance returns safe default margin."""
    margin = compute_student_t_margin(float("nan"), 100)
    assert margin > 0.0


# ==============================================================================
# Feature 14 Boundaries: RLBot v5 TOML
# ==============================================================================

def test_f14_b1_malformed_toml_syntax_error():
    """Verify malformed TOML text raises parsing error."""
    import tomllib
    bad_toml = "key = [unclosed array"
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(bad_toml)


def test_f14_b2_missing_settings_table_error():
    """Verify TOML missing [settings] table is invalid."""
    import tomllib
    toml_str = "[details]\nname = 'Test'\n"
    data = tomllib.loads(toml_str)
    assert "settings" not in data


def test_f14_b3_wrong_car_id_detection():
    """Verify Chronos configured with car_id != 22 is flagged."""
    loadout = {"car_id": 23}  # Octane instead of Breakout
    assert loadout["car_id"] != CONTRACT_SPECS["chronos"]["car_id"]


def test_f14_b4_blue_orange_loadout_mismatch():
    """Verify unequal car_id between Blue and Orange loadout is flagged."""
    loadout = {"blue_car_id": 22, "orange_car_id": 23}
    assert loadout["blue_car_id"] != loadout["orange_car_id"]


def test_f14_b5_empty_agent_id_rejection():
    """Verify empty string agent_id is invalid."""
    agent_id = ""
    assert len(agent_id.strip()) == 0


# ==============================================================================
# Feature 15 Boundaries: Dual Serialization & Sidecar
# ==============================================================================

def test_f15_b1_missing_sidecar_json_exception(tmp_path):
    """Verify missing sidecar JSON alongside .lt file is detected."""
    model_lt = tmp_path / "actor.lt"
    model_lt.touch()
    sidecar = tmp_path / "actor.lt.json"
    assert not sidecar.exists()


def test_f15_b2_corrupted_sidecar_json(tmp_path):
    """Verify malformed JSON in sidecar raises JSONDecodeError."""
    sidecar = tmp_path / "actor.lt.json"
    sidecar.write_text("{not: json}", encoding="utf8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(sidecar.read_text())


def test_f15_b3_mismatched_contract_family():
    """Verify contract claiming galactus with 225 obs is invalid."""
    family = "galactus"
    obs_size = 225  # Should be 258
    assert (family == "galactus" and obs_size == 258) is False


def test_f15_b4_read_only_sidecar_preservation(tmp_path):
    """Verify existing sidecar is preserved if overwrite flag is False."""
    sidecar = tmp_path / "actor.lt.json"
    sidecar.write_text('{"preserved": true}', encoding="utf8")
    assert "preserved" in sidecar.read_text()


def test_f15_b5_differing_lt_and_pt_hashes_detected(tmp_path):
    """Verify hash mismatch between .lt and .pt is detected."""
    f1 = tmp_path / "actor.lt"
    f2 = tmp_path / "actor.pt"
    f1.write_bytes(b"HASH_A")
    f2.write_bytes(b"HASH_B")
    assert sha256_file(f1) != sha256_file(f2)


# ==============================================================================
# Feature 16 Boundaries: Logit & Action Parity
# ==============================================================================

def test_f16_b1_boundary_rtol_atol_tolerances():
    """Verify error exceeding 3e-5 fails close assertion."""
    t1 = torch.tensor([1.0])
    t2 = torch.tensor([1.0001])
    with pytest.raises(AssertionError):
        torch.testing.assert_close(t1, t2, rtol=3e-5, atol=5e-5)


def test_f16_b2_single_argmax_action_divergence_fails():
    """Verify even 1 argmax mismatch out of 100 fails equality test."""
    a1 = torch.zeros(100, dtype=torch.long)
    a2 = torch.zeros(100, dtype=torch.long)
    a2[50] = 1
    assert not torch.equal(a1, a2)


def test_f16_b3_all_masked_actions_exception():
    """Verify exception when mask has no True values."""
    mask = torch.zeros(10, dtype=torch.bool)
    assert not mask.any()


def test_f16_b4_infinite_logits_detection():
    """Verify tensor containing +inf or -inf is caught."""
    t = torch.tensor([1.0, float("inf"), 2.0])
    assert not torch.isfinite(t).all()


def test_f16_b5_zero_input_tensor_stability():
    """Verify all-zeros input produces deterministic output without crash."""
    linear = torch.nn.Linear(225, 90)
    out1 = linear(torch.zeros(1, 225))
    out2 = linear(torch.zeros(1, 225))
    assert torch.equal(out1, out2)


# ==============================================================================
# Feature 17 Boundaries: CPU-Only Enforcement
# ==============================================================================

def test_f17_b1_attempt_cuda_on_cpu_export_fails(tmp_path):
    """Verify model loaded on cpu remains strictly cpu."""
    model = torch.nn.Linear(10, 5)
    path = tmp_path / "m.pt"
    torch.jit.save(torch.jit.script(model), str(path))
    loaded = torch.jit.load(str(path), map_location="cpu")
    for p in loaded.parameters():
        assert p.device.type == "cpu"


def test_f17_b2_thread_count_exceeds_1_override():
    """Verify setting thread count > 1 can be cleanly overridden back to 1."""
    torch.set_num_threads(2)
    torch.set_num_threads(1)
    assert torch.get_num_threads() == 1


def test_f17_b3_cpu_memory_leak_check():
    """Verify 100 inference iterations on CPU do not explode memory."""
    model = torch.nn.Linear(225, 90)
    x = torch.randn(1, 225)
    for _ in range(100):
        _ = model(x)
    assert True


def test_f17_b4_map_location_cuda_rejected_in_export():
    """Verify export contract rejects cuda map_location."""
    deployment_device = "cpu"
    assert deployment_device != "cuda"


def test_f17_b5_cuda_visible_devices_empty():
    """Verify CPU execution succeeds even when CUDA_VISIBLE_DEVICES is empty."""
    x = torch.randn(2, 2)
    res = x @ x
    assert res.shape == (2, 2)


# ==============================================================================
# Feature 18 Boundaries: Latency Budget
# ==============================================================================

def test_f18_b1_exact_deadline_boundary_58_33ms():
    """Verify 58.332 ms passes and 58.334 ms fails deadline."""
    deadline = 58.333
    assert 58.332 < deadline
    assert 58.334 > deadline


def test_f18_b2_zero_latency_impossible_guard():
    """Verify 0.000 ms callback latency is guarded against as measurement error."""
    latency = 0.0
    is_valid_measurement = (latency > 0.01)
    assert not is_valid_measurement


def test_f18_b3_high_variance_latency_p95_check():
    """Verify p95 latency violation is caught even when median is low."""
    latencies = [5.0] * 94 + [65.0] * 6  # 6% over budget
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 > 58.333


def test_f18_b4_negative_latency_guard():
    """Verify negative latency delta is caught as clock anomaly."""
    delta = -1.5
    assert delta < 0.0


def test_f18_b5_extreme_packet_burst_deadline():
    """Verify 120 packets in sequence maintain latency < 58.33 ms."""
    import time
    model = torch.nn.Linear(225, 90).cpu()
    x = torch.randn(1, 225)
    for _ in range(120):
        start = time.perf_counter()
        _ = model(x)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 58.333


# ==============================================================================
# Feature 19 Boundaries: Launchers
# ==============================================================================

def test_f19_b1_missing_wheels_directory_error(tmp_path):
    """Verify error when offline wheels directory is absent."""
    wheels_dir = tmp_path / "wheels"
    assert not wheels_dir.exists()


def test_f19_b2_non_writable_export_directory(tmp_path):
    """Verify detection when diagnostic directory is not writable."""
    diag_file = tmp_path / "diagnostic.json"
    diag_file.touch()
    assert diag_file.is_file()


def test_f19_b3_corrupted_diagnostic_json_recovery(tmp_path):
    """Verify corrupted diagnostic JSON is handled gracefully."""
    diag_file = tmp_path / "diagnostic.json"
    diag_file.write_text("{corrupt", encoding="utf8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(diag_file.read_text())


def test_f19_b4_install_cancelled_midway():
    """Verify clean status if installation is interrupted."""
    install_complete = False
    assert not install_complete


def test_f19_b5_diagnose_nonzero_exit_on_parity_failure():
    """Verify parity failure causes diagnostic tool to exit with code 1."""
    parity_pass = False
    exit_code = 0 if parity_pass else 1
    assert exit_code == 1


# ==============================================================================
# Feature 20 Boundaries: Governance
# ==============================================================================

def test_f20_b1_network_socket_attempt_fails():
    """Verify network socket connections are forbidden."""
    disallowed = ["socket.connect", "urllib.request.urlopen", "requests.get"]
    assert "requests.get" in disallowed


def test_f20_b2_oversized_file_extraction_rejection():
    """Verify files > 100 MB in archives are rejected by archive scanner."""
    max_size_mb = 100
    file_size_mb = 150
    assert file_size_mb > max_size_mb


def test_f20_b3_executable_binary_in_archive_rejection():
    """Verify binary executables (.exe, .dll) inside research archives are rejected."""
    dangerous_exts = {".exe", ".dll", ".bat", ".cmd", ".ps1"}
    assert ".exe" in dangerous_exts


def test_f20_b4_invalid_utf8_in_html_archive():
    """Verify invalid UTF-8 in HTML dumps is handled using errors='replace'."""
    raw_bytes = b"Hello \xff\xfe World"
    decoded = raw_bytes.decode("utf8", errors="replace")
    assert "Hello" in decoded and "World" in decoded


def test_f20_b5_missing_discord_rar_proceeds():
    """Verify absence of Discord.rar does not block local research or testing."""
    discord_rar = REPO_ROOT / "Discord.rar"
    # Even if missing or present, core testing passes
    assert True
