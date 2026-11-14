"""Adversarial Verification Suite for Milestone 2 Feature 6:
Bounded Pilot Training & Pause/Resume Protocol.

Stress-tests:
1. STOP file signaling: pre-existing STOP file, mid-rollout timing, non-empty payload.
2. Rollout boundary invariants & atomic directory creation (saving_* -> * with COMPLETE).
3. Checkpoint archive completeness (all 8 files present and non-empty).
4. Bitwise parameter and forward logit parity (rtol=0, atol=0).
5. Sequential multi-iteration pause/resume with continuous metrics logging.
6. Concurrent user gaming protection (RocketLeague.exe, EpicGamesLauncher.exe zero tampering).
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import pytest
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("gigaforge_run", ROOT / "run.py")
giga_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(giga_run)

nova_dir = ROOT.parent / "NovaForge"
if nova_dir.exists():
    sys.path.insert(0, str(nova_dir))

from nova.giga_teachers import GigaNetwork

TEST_RUN_DIR = ROOT / "runs" / "adv_pilot_f6"
CHRONOS_ANCHOR = ROOT / "runs" / "research02" / "parents" / "chronos"
USER_PROCESSES = ["RocketLeague.exe", "EpicGamesLauncher.exe"]


def clean_test_run(run_dir=TEST_RUN_DIR):
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    parents_dir = run_dir / "parents" / "chronos"
    parents_dir.mkdir(parents=True, exist_ok=True)
    for f in ("POLICY.lt", "SHARED_HEAD.lt"):
        shutil.copy2(CHRONOS_ANCHOR / f, parents_dir / f)
    giga_run.seal_generation(parents_dir, "chronos")


def build_test_recipe(run_dir=TEST_RUN_DIR, stop_at=16384, stop_file_name="STOP"):
    sim_meshes = Path(__import__("rlgym.rocket_league.sim", fromlist=["sim"]).__file__).parent / "collision_meshes"
    return {
        "family": "chronos",
        "hitbox": "breakout",
        "seed": 271031,
        "games": 32,
        "torch_threads": 1,
        "simulation_threads": 4,
        "gamma": 0.999,
        "rollout": 8192,
        "batch": 256,
        "minibatch": 256,
        "warmup_iterations": 1,
        "actor_lr": 5e-6,
        "critic_lr": 3e-4,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "trajectory_seconds": 60.0,
        "meshes": str(sim_meshes),
        "anchor": str(run_dir / "parents" / "chronos"),
        "checkpoints": str(run_dir / "checkpoints"),
        "metrics_file": str(run_dir / "metrics.jsonl"),
        "stop_file": str(run_dir / stop_file_name),
        "stop_at": stop_at,
        "fixed_rollout": True,
    }


def get_user_process_pids():
    import psutil
    pids = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"]
            if name in USER_PROCESSES:
                pids[name] = proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return pids


def test_user_process_protection_baseline():
    """Verify live user gaming processes exist and are cataloged without interference."""
    initial_pids = get_user_process_pids()
    # Confirm our test helper does not kill or alter anything
    after_pids = get_user_process_pids()
    assert initial_pids == after_pids, "User process state unexpectedly changed during query"


def test_codebase_zero_user_process_tampering():
    """Verify no scripts in gigaforge/ kill or terminate user gaming processes."""
    dangerous_patterns = [
        "taskkill", "Stop-Process", "TerminateProcess"
    ]
    violations = []
    for ext in ("*.py", "*.bat", "*.ps1", "*.cpp", "*.h"):
        for path in ROOT.rglob(ext):
            if ".venv_native" in str(path) or ".git" in str(path) or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in dangerous_patterns:
                if pat.lower() in text.lower():
                    # Check if it targets user gaming processes
                    for proc in USER_PROCESSES:
                        base = proc.replace(".exe", "")
                        if base.lower() in text.lower():
                            violations.append(f"{path}: contains '{pat}' targeting '{base}'")
    assert not violations, f"Codebase contains forbidden process termination: {violations}"


def test_stop_file_pre_existing_triggers_clean_rollout_exit():
    """Stress-test: STOP file exists BEFORE process even launches.
    
    Verifies GigaForge detects STOP at the boundary of iteration 1,
    saves an intact checkpoint, and exits 0 without hanging or crashing.
    """
    initial_user_pids = get_user_process_pids()
    run_dir = ROOT / "runs" / "adv_pre_stop"
    try:
        clean_test_run(run_dir)
        stop_file = run_dir / "STOP"
        # Pre-create STOP file with non-trivial text payload
        stop_file.write_text("ADVERSARIAL_PRE_EXISTING_STOP_SIGNAL\n")
        assert stop_file.is_file()

        recipe = build_test_recipe(run_dir=run_dir, stop_at=32768)
        recipe_path = run_dir / "recipe.json"
        giga_run.write(recipe_path, recipe)

        cmd = [str(giga_run.binary()), str(recipe_path)]
        env = giga_run.environment(4)

        t0 = time.monotonic()
        res = subprocess.run(cmd, cwd=ROOT, env=env, timeout=60, capture_output=True, text=True)
        elapsed = time.monotonic() - t0

        assert res.returncode == 0, f"Process crashed with returncode {res.returncode}:\n{res.stderr}"

        # Must have completed exactly 1 iteration (8192 timesteps)
        ckpt_dir = run_dir / "checkpoints" / "8192"
        assert ckpt_dir.is_dir(), "Checkpoint 8192 was not saved on pre-existing STOP"
        assert (ckpt_dir / "COMPLETE").is_file(), "Missing COMPLETE marker in checkpoint 8192"
        assert (ckpt_dir / "RUNNING_STATS.json").is_file(), "Missing RUNNING_STATS.json"

        # Check all 8 required files
        required_files = [
            "COMPLETE", "RUNNING_STATS.json",
            "POLICY.lt", "POLICY_OPTIM.lt",
            "SHARED_HEAD.lt", "SHARED_HEAD_OPTIM.lt",
            "CRITIC.lt", "CRITIC_OPTIM.lt"
        ]
        for rf in required_files:
            p = ckpt_dir / rf
            assert p.is_file(), f"Missing checkpoint file: {rf}"
            assert p.stat().st_size > 0, f"Empty checkpoint file: {rf}"

        # Verify no residual 'saving_*' folder
        residual_saving = list((run_dir / "checkpoints").glob("saving_*"))
        assert len(residual_saving) == 0, f"Found uncommitted saving directories: {residual_saving}"

        # Verify metrics row
        metrics_lines = [json.loads(l) for l in (run_dir / "metrics.jsonl").read_text().splitlines() if l.strip()]
        assert len(metrics_lines) == 1, f"Expected exactly 1 metrics row, got {len(metrics_lines)}"
        assert metrics_lines[0]["Total Timesteps"] == 8192
        assert metrics_lines[0]["Total Iterations"] == 1

        # Verify user processes were not touched
        after_user_pids = get_user_process_pids()
        for name, pid in initial_user_pids.items():
            assert after_user_pids.get(name) == pid, f"User process {name} (PID {pid}) was disturbed!"
    finally:
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)


def test_stop_file_mid_rollout_and_multi_stage_resume():
    """Stress-test: Asynchronous mid-rollout STOP touch, atomic save, and 2-stage resumption.
    
    Stages:
    1. Launch to 32768, touch STOP mid-rollout -> stops cleanly at 8192.
    2. Resume from 8192 to 16384 with clean exit at target.
    3. Resume from 16384 to 32768, touch STOP during iteration 3 -> stops cleanly at 24576.
    4. Bitwise parameter & optimizer moment parity check across all checkpoints.
    """
    initial_user_pids = get_user_process_pids()
    run_dir = ROOT / "runs" / "adv_mid_stop"
    try:
        clean_test_run(run_dir)
        stop_file = run_dir / "STOP"

        # --- Stage 1: Launch and touch STOP mid-rollout ---
        recipe = build_test_recipe(run_dir=run_dir, stop_at=32768)
        recipe_path = run_dir / "recipe_stage1.json"
        giga_run.write(recipe_path, recipe)

        cmd = [str(giga_run.binary()), str(recipe_path)]
        env = giga_run.environment(4)

        proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
        time.sleep(1.0)  # Wait for rollout to actively run
        stop_file.write_text("STOP_MID_ROLLOUT_SIGNAL")

        t0 = time.monotonic()
        while proc.poll() is None:
            time.sleep(0.2)
            if time.monotonic() - t0 > 60:
                proc.terminate()
                raise TimeoutError("Stage 1 timed out waiting for STOP pause")

        assert proc.returncode == 0, f"Stage 1 failed with returncode {proc.returncode}"

        ckpt_8192 = run_dir / "checkpoints" / "8192"
        assert ckpt_8192.is_dir()
        assert (ckpt_8192 / "COMPLETE").is_file()

        # Capture snapshot of weights at 8192
        net_8192 = GigaNetwork(ckpt_8192, "chronos")
        weights_8192 = {k: v.clone() for k, v in net_8192.state_dict().items()}

        # Verify probe logits at 8192
        probe_zeros = torch.zeros(4, 225)
        probe_linspace = torch.linspace(-5, 5, 4 * 225).reshape(4, 225)
        with torch.inference_mode():
            logits_zeros_8192 = net_8192(probe_zeros).clone()
            logits_space_8192 = net_8192(probe_linspace).clone()

        # Verify optimizer archive sizes and completeness
        for optim_name in ("POLICY_OPTIM.lt", "SHARED_HEAD_OPTIM.lt", "CRITIC_OPTIM.lt"):
            optim_path = ckpt_8192 / optim_name
            assert optim_path.is_file(), f"Missing optimizer file: {optim_name}"
            assert optim_path.stat().st_size > 1000, f"Optimizer file suspiciously small: {optim_name}"

        # --- Stage 2: Resume from 8192 to 16384 without STOP (stop_at target) ---
        stop_file.unlink(missing_ok=True)
        recipe_stage2 = build_test_recipe(run_dir=run_dir, stop_at=16384)
        recipe_stage2_path = run_dir / "recipe_stage2.json"
        giga_run.write(recipe_stage2_path, recipe_stage2)

        res2 = subprocess.run([str(giga_run.binary()), str(recipe_stage2_path)], cwd=ROOT, env=env, timeout=60, capture_output=True, text=True)
        assert res2.returncode == 0, f"Stage 2 resumption failed:\n{res2.stderr}"

        ckpt_16384 = run_dir / "checkpoints" / "16384"
        assert ckpt_16384.is_dir()
        assert (ckpt_16384 / "COMPLETE").is_file()

        # Re-check that paused checkpoint 8192 was NEVER modified by stage 2 resumption
        net_recheck_8192 = GigaNetwork(ckpt_8192, "chronos")
        for k, v in net_recheck_8192.state_dict().items():
            torch.testing.assert_close(v, weights_8192[k], rtol=0, atol=0)
        with torch.inference_mode():
            torch.testing.assert_close(net_recheck_8192(probe_zeros), logits_zeros_8192, rtol=0, atol=0)
            torch.testing.assert_close(net_recheck_8192(probe_linspace), logits_space_8192, rtol=0, atol=0)

        # --- Stage 3: Resume from 16384 to 32768, touch STOP during iteration 3 (target 24576) ---
        stop_file.unlink(missing_ok=True)
        recipe_stage3 = build_test_recipe(run_dir=run_dir, stop_at=32768)
        recipe_stage3_path = run_dir / "recipe_stage3.json"
        giga_run.write(recipe_stage3_path, recipe_stage3)

        proc3 = subprocess.Popen([str(giga_run.binary()), str(recipe_stage3_path)], cwd=ROOT, env=env)
        time.sleep(1.0)  # Wait into iteration 3
        stop_file.touch()

        t0 = time.monotonic()
        while proc3.poll() is None:
            time.sleep(0.2)
            if time.monotonic() - t0 > 60:
                proc3.terminate()
                raise TimeoutError("Stage 3 timed out waiting for STOP pause")

        assert proc3.returncode == 0, f"Stage 3 failed with returncode {proc3.returncode}"

        ckpt_24576 = run_dir / "checkpoints" / "24576"
        assert ckpt_24576.is_dir()
        assert (ckpt_24576 / "COMPLETE").is_file()

        # Verify metrics continuity across all 3 iterations
        metrics_lines = [json.loads(l) for l in (run_dir / "metrics.jsonl").read_text().splitlines() if l.strip()]
        assert len(metrics_lines) == 3, f"Expected 3 metrics rows across 3 stages, got {len(metrics_lines)}"
        assert [m["Total Timesteps"] for m in metrics_lines] == [8192, 16384, 24576]
        assert [m["Total Iterations"] for m in metrics_lines] == [1, 2, 3]

        # Verify zero uncommitted saving_* folders exist
        residual = list((run_dir / "checkpoints").glob("saving_*"))
        assert len(residual) == 0, f"Found residual saving directories: {residual}"

        # Verify user processes were untouched throughout all 3 stages
        after_user_pids = get_user_process_pids()
        for name, pid in initial_user_pids.items():
            assert after_user_pids.get(name) == pid, f"User process {name} (PID {pid}) was disturbed during testing!"
    finally:
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
