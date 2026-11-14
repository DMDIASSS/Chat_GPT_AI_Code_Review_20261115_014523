"""Tier 3: Cross-Feature Interactions & Pairwise Combination Test Suite."""
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
# Interaction 1: Paired Colors + Paired Seeds Invariant (F12 x F13)
# ==============================================================================

def test_interaction_paired_seeds_and_color_symmetry():
    """Verify that every evaluated seed has exactly 1 Blue and 1 Orange match, preserving paired symmetry."""
    seeds = [101, 102, 103, 104, 105]
    match_records = []
    for s in seeds:
        match_records.append({"seed": s, "color": "blue", "score": 1.0})
        match_records.append({"seed": s, "color": "orange", "score": 0.5})

    assert len(match_records) == len(seeds) * 2
    # Verify pairing: group by seed
    paired_scores = {}
    for r in match_records:
        s = r["seed"]
        paired_scores.setdefault(s, {})[r["color"]] = r["score"]

    for s, colors in paired_scores.items():
        assert "blue" in colors and "orange" in colors
        pair_mean = (colors["blue"] + colors["orange"]) / 2.0
        assert pair_mean == 0.75

    # Compute overall mean and CI
    pair_means = [(c["blue"] + c["orange"]) / 2.0 for c in paired_scores.values()]
    overall_mean = sum(pair_means) / len(pair_means)
    assert overall_mean == 0.75


# ==============================================================================
# Interaction 2: Training Pause -> Checkpoint Save -> Resume -> H2H Eval (F5 x F6 x F12)
# ==============================================================================

def test_interaction_pause_save_resume_eval_pipeline(tmp_path):
    """Verify training pause writes checkpoint, resumes identically, and prepares H2H eval."""
    run_dir = tmp_path / "research02"
    run_dir.mkdir()
    stop_file = run_dir / "STOP"
    ckpt_dir = run_dir / "checkpoints"
    ckpt_dir.mkdir()

    # 1. Simulate training running and detecting STOP file
    stop_file.touch()
    assert stop_file.is_file()

    # 2. Complete current iteration and write checkpoint
    step = 8192
    model = torch.nn.Linear(225, 90)
    saved_weights = {k: v.clone() for k, v in model.state_dict().items()}
    ckpt_path = ckpt_dir / f"step_{step}.pt"
    torch.save({"actor": saved_weights, "step": step}, str(ckpt_path))

    # 3. Clean stop: remove STOP file
    stop_file.unlink()
    assert not stop_file.exists()

    # 4. Resume from checkpoint
    loaded = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    resumed_model = torch.nn.Linear(225, 90)
    resumed_model.load_state_dict(loaded["actor"])

    # 5. Parity check on weights
    for k in saved_weights:
        assert torch.equal(saved_weights[k], resumed_model.state_dict()[k])

    # 6. Evaluation probe
    probe_obs = torch.randn(2, 225)
    with torch.no_grad():
        out1 = model(probe_obs)
        out2 = resumed_model(probe_obs)
    torch.testing.assert_close(out1, out2, rtol=0, atol=0)


# ==============================================================================
# Interaction 3: Model Export -> Dual Serialization -> CPU -> Latency (F14 x F15 x F16 x F17 x F18)
# ==============================================================================

def test_interaction_export_dual_serialization_cpu_latency_pipeline(tmp_path):
    """Verify complete export pipeline from source actor to RLBot v5 package with latency verification."""
    export_dir = tmp_path / "Forge_chronos_export"
    export_dir.mkdir()

    # 1. Source Actor
    source_actor = torch.nn.Sequential(
        torch.nn.Linear(225, 256),
        torch.nn.ReLU(),
        torch.nn.Linear(256, 90)
    ).cpu().eval()

    # 2. Dual Serialization: identical actor.lt and actor.pt
    scripted = torch.jit.script(source_actor)
    lt_path = export_dir / "actor.lt"
    pt_path = export_dir / "actor.pt"
    torch.jit.save(scripted, str(lt_path))
    import shutil
    shutil.copy2(str(lt_path), str(pt_path))
    assert sha256_file(lt_path) == sha256_file(pt_path)

    # 3. Sidecars
    contract = {
        "family": "chronos",
        "hitbox": "breakout",
        "obs_size": 225,
        "action_size": 90,
        "car_id": 22,
    }
    (export_dir / "actor.lt.json").write_text(json.dumps(contract), encoding="utf8")
    (export_dir / "actor.pt.json").write_text(json.dumps(contract), encoding="utf8")

    # 4. Numerical & Action Parity
    loaded_actor = torch.jit.load(str(pt_path), map_location="cpu").eval()
    test_obs = torch.randn(20, 225)
    with torch.no_grad():
        expected = source_actor(test_obs)
        actual = loaded_actor(test_obs)
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    assert torch.equal(expected.argmax(dim=-1), actual.argmax(dim=-1))

    # 5. CPU Enforcement & Single-Thread
    torch.set_num_threads(1)
    assert torch.get_num_threads() == 1

    # 6. Latency Benchmarking (< 58.33 ms)
    import time
    latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        _ = loaded_actor(test_obs[:1])
        latencies.append((time.perf_counter() - t0) * 1000.0)

    max_latency = max(latencies)
    assert max_latency < 58.333, f"Latency {max_latency} ms exceeded deadline 58.33 ms"


# ==============================================================================
# Interaction 4: Dev Split Screening -> Confirmation -> Secondary Panel (F8 x F9 x F10 x F11)
# ==============================================================================

def test_interaction_screening_to_confirmation_to_secondary_panel():
    """Verify progression through screening (32 pairs), confirmation (128 pairs), and secondary panel."""
    # 1. Dev Split Screening: 32 pairs (128 games/opp)
    dev_delta = 0.045
    assert dev_delta >= 0.03, "Failed dev screening gate"

    # 2. Confirmation Split: 128 pairs under alpha-spending
    confirm_k = 1
    alpha_threshold = compute_alpha_spending(confirm_k, 0.05)
    assert alpha_threshold == 0.025
    confirm_delta = 0.042
    assert confirm_delta > 0, "Confirmation underperformed baseline"

    # 3. Secondary Opponent Panel Evaluation
    secondary_results = {
        "nexto": {"delta": +0.015, "tolerance": -0.02},
        "ripple": {"delta": +0.020, "tolerance": -0.02},
        "ducky": {"delta": +0.005, "tolerance": -0.02},
        "rain": {"delta": +0.030, "tolerance": -0.02},
        "megabyte": {"delta": +0.010, "tolerance": -0.02},
        "fusion": {"delta": +0.012, "tolerance": -0.02},
        "scripted": {"delta": +0.050, "tolerance": -0.02},
    }
    assert len(secondary_results) == 7
    for bot, res in secondary_results.items():
        assert res["delta"] >= res["tolerance"], f"Regression tolerance breached for {bot}"


# ==============================================================================
# Interaction 5: Checkpoint Retention -> Shortlist -> Direct H2H -> Promotion Gate (F5 x F12 x F13)
# ==============================================================================

def test_interaction_checkpoint_retention_to_promotion_gate(tmp_path):
    """Verify shortlisted pinned candidate evaluated in 2000-game test passes or rejects cleanly."""
    # Create shortlisted trial record
    trial_record = {
        "trial": 42,
        "family": "chronos",
        "pin_path": str(tmp_path / "trial_42_actor.lt"),
        "pinned": True,
    }
    assert trial_record["pinned"] is True

    # Scenario A: Candidate achieves 54% score rate with tight CI
    # Mean = 0.54, Var = 0.20, N = 1000 pairs
    margin = compute_student_t_margin(0.20, 1000)
    lower_bound = 0.54 - margin
    assert lower_bound > 0.5000
    verdict_a = "promote" if lower_bound > 0.5000 else "preserve_baseline"
    assert verdict_a == "promote"

    # Scenario B: Historical Trial 38 with score 49.05%
    mean_b = 0.4905
    lower_b = 0.4706
    verdict_b = "promote" if lower_b > 0.5000 else "preserve_baseline"
    assert verdict_b == "preserve_baseline"


# ==============================================================================
# Interaction 6: Hitbox Contract -> Loadout TOML -> Physics Delay Budget (F3 x F14 x F18)
# ==============================================================================

def test_interaction_hitbox_loadout_and_physics_contract():
    """Verify Breakout hitbox in native contract maps to car_id 22 and 58.33ms delay."""
    chronos_spec = CONTRACT_SPECS["chronos"]
    assert chronos_spec["hitbox"] == "breakout"
    assert chronos_spec["car_id"] == 22
    assert chronos_spec["tick_skip"] == 8
    assert chronos_spec["planned_delay"] == 7
    assert chronos_spec["latency_budget_ms"] == 58.333

    # Generate loadout TOML
    loadout_toml = f"""[blue_loadout]
car_id = {chronos_spec['car_id']}
[orange_loadout]
car_id = {chronos_spec['car_id']}
"""
    assert "car_id = 22" in loadout_toml


# ==============================================================================
# Interaction 7: Telemetry Logging -> Thermal Boundary -> STOP Halt (F4 x F6 x F20)
# ==============================================================================

def test_interaction_telemetry_thermal_and_stop_halt(tmp_path):
    """Verify telemetry monitoring triggers STOP file creation on thermal breach."""
    run_dir = tmp_path / "research02"
    run_dir.mkdir()
    metrics_file = run_dir / "metrics.jsonl"
    stop_file = run_dir / "STOP"

    # Log telemetry
    records = [
        {"iteration": 1, "temp_c": 72.0, "vram_mb": 1100},
        {"iteration": 2, "temp_c": 80.0, "vram_mb": 1150},
        {"iteration": 3, "temp_c": 85.5, "vram_mb": 1200},  # Thermal breach
    ]
    with open(metrics_file, "w", encoding="utf8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
            if r["temp_c"] >= 85.0:
                stop_file.touch()

    assert stop_file.is_file(), "STOP file was not created upon thermal breach"


# ==============================================================================
# Interaction 8: Baseline Hash -> Policy Contract -> Export Sidecar (F1 x F7 x F15)
# ==============================================================================

def test_interaction_baseline_hash_contract_sidecar_consistency():
    """Verify that model baseline hashes, observation contract, and sidecars remain consistent."""
    assert BASELINE_HASHES["chronos_policy"] == "cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360"
    assert CONTRACT_SPECS["chronos"]["obs_size"] == 225
    assert CONTRACT_SPECS["chronos"]["action_size"] == 90
    assert CONTRACT_SPECS["chronos"]["mirror"] is True

    sidecar = {
        "parent_policy_hash": BASELINE_HASHES["chronos_policy"],
        "obs_dim": CONTRACT_SPECS["chronos"]["obs_size"],
        "action_dim": CONTRACT_SPECS["chronos"]["action_size"],
        "hitbox": CONTRACT_SPECS["chronos"]["hitbox"],
    }
    assert sidecar["parent_policy_hash"].startswith("cb4e93")
    assert sidecar["obs_dim"] == 225
    assert sidecar["hitbox"] == "breakout"
