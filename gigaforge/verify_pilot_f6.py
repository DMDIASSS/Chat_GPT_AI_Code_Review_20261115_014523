"""Automated Verification for Milestone 2 Feature 6: Bounded Pilot & Pause/Resume Protocol."""
from pathlib import Path
import json, os, shutil, subprocess, sys, time
import torch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import importlib.util
spec = importlib.util.spec_from_file_location("gigaforge_run", ROOT / "run.py")
giga_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(giga_run)

nova_dir = ROOT.parent / "NovaForge"
if nova_dir.exists():
    sys.path.insert(0, str(nova_dir))

from nova.giga_teachers import GigaNetwork

PILOT_NAME = "pilot_chronos"
RUN_DIR = ROOT / "runs" / PILOT_NAME
STOP_FILE = RUN_DIR / "STOP"
CHRONOS_ANCHOR = ROOT / "runs" / "research02" / "parents" / "chronos"

def clean_pilot():
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True)
    (RUN_DIR / "parents" / "chronos").mkdir(parents=True)
    for f in ("POLICY.lt", "SHARED_HEAD.lt"):
        shutil.copy2(CHRONOS_ANCHOR / f, RUN_DIR / "parents" / "chronos" / f)
    giga_run.seal_generation(RUN_DIR / "parents" / "chronos", "chronos")

def build_recipe(stop_at=16384):
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
        "anchor": str(RUN_DIR / "parents" / "chronos"),
        "checkpoints": str(RUN_DIR / "checkpoints"),
        "metrics_file": str(RUN_DIR / "metrics.jsonl"),
        "stop_file": str(STOP_FILE),
        "stop_at": stop_at,
        "fixed_rollout": True
    }

def step1_launch_and_pause_via_stop_file():
    print("=== Step 1: Launch Pilot & Pause via STOP File ===")
    clean_pilot()
    recipe = build_recipe(stop_at=32768)  # Set higher limit to verify STOP file triggers early
    
    # Save recipe to disk
    recipe_path = RUN_DIR / "recipe.json"
    giga_run.write(recipe_path, recipe)
    
    cmd = [str(giga_run.binary()), str(recipe_path)]
    env = giga_run.environment(4)
    
    # Launch subprocess
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    
    # Touch STOP file during iteration 1 rollout collection
    print("Awaiting iteration 1 execution...")
    time.sleep(0.5)
    print(f"Touching STOP file during iteration 1: {STOP_FILE}")
    STOP_FILE.touch()
    
    start_wait = time.monotonic()
    while proc.poll() is None:
        time.sleep(0.2)
        if time.monotonic() - start_wait > 60:
            proc.terminate()
            raise TimeoutError("Pilot run exceeded 60 seconds without completing iteration 1")
    
    proc.wait()
    assert proc.returncode == 0, f"Process failed with exit code {proc.returncode}"
    print(f"PASS: Process exited cleanly with code {proc.returncode}")

def step2_verify_checkpoint_integrity():
    print("=== Step 2: Verify Checkpoint Integrity ===")
    ckpt_dirs = [p for p in (RUN_DIR / "checkpoints").glob("*") if p.is_dir() and p.name.isdigit()]
    assert len(ckpt_dirs) > 0, "No checkpoint directory created on pause!"
    latest_ckpt = max(ckpt_dirs, key=lambda p: int(p.name))
    print(f"Found latest checkpoint: {latest_ckpt.name} timesteps")
    assert latest_ckpt.name == "8192", f"Expected checkpoint 8192, got {latest_ckpt.name}"
    
    # Verify all essential files exist
    required_files = [
        "COMPLETE", "RUNNING_STATS.json",
        "POLICY.lt", "POLICY_OPTIM.lt",
        "SHARED_HEAD.lt", "SHARED_HEAD_OPTIM.lt",
        "CRITIC.lt", "CRITIC_OPTIM.lt"
    ]
    for rf in required_files:
        p = latest_ckpt / rf
        assert p.is_file(), f"Missing required checkpoint file: {rf}"
        assert p.stat().st_size > 0, f"Empty checkpoint file: {rf}"
    
    # Verify stats
    stats = json.loads((latest_ckpt / "RUNNING_STATS.json").read_text())
    assert stats["total_timesteps"] == int(latest_ckpt.name)
    assert stats["total_iterations"] == 1
    
    # Verify model forward pass on probe
    giga_run.seal_generation(latest_ckpt, "chronos")
    giga_run.verify_generation(latest_ckpt)
    print("PASS: Checkpoint structure and forward pass verified.")
    return latest_ckpt

def step3_resume_and_verify_parity(paused_ckpt):
    print("=== Step 3: Resume Training & Verify Parity ===")
    STOP_FILE.unlink(missing_ok=True)
    
    # Save weight state before resumption for parity check
    actor_paused = GigaNetwork(paused_ckpt, "chronos")
    paused_state = {k: v.clone() for k, v in actor_paused.state_dict().items()}
    
    # Probe input for bitwise check
    probe = torch.linspace(-1, 1, 4 * 225).reshape(4, 225)
    with torch.inference_mode():
        paused_probe_logits = actor_paused(probe).clone()
    
    # Determine next target (run exactly 1 more iteration)
    paused_ts = int(paused_ckpt.name)
    next_target = paused_ts + 8192
    
    recipe = build_recipe(stop_at=next_target)
    recipe_path = RUN_DIR / "recipe_resume.json"
    giga_run.write(recipe_path, recipe)
    
    cmd = [str(giga_run.binary()), str(recipe_path)]
    env = giga_run.environment(4)
    
    print(f"Resuming from {paused_ts} to {next_target}...")
    res = subprocess.run(cmd, cwd=ROOT, env=env, timeout=60)
    assert res.returncode == 0, f"Resumption failed with return code {res.returncode}"
    
    # Check new checkpoint
    new_ckpt = RUN_DIR / "checkpoints" / str(next_target)
    assert new_ckpt.is_dir(), f"Resumed checkpoint {next_target} was not saved!"
    assert (new_ckpt / "COMPLETE").is_file()
    
    # Verify all checkpoint files exist in new checkpoint
    for rf in ("COMPLETE", "RUNNING_STATS.json", "POLICY.lt", "POLICY_OPTIM.lt", "SHARED_HEAD.lt", "SHARED_HEAD_OPTIM.lt", "CRITIC.lt", "CRITIC_OPTIM.lt"):
        p = new_ckpt / rf
        assert p.is_file(), f"Missing required checkpoint file in resumed checkpoint: {rf}"
        assert p.stat().st_size > 0, f"Empty checkpoint file: {rf}"
    
    # Verify metrics rows
    lines = [json.loads(l) for l in (RUN_DIR / "metrics.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 2, f"Expected 2 metrics rows, got {len(lines)}"
    assert lines[0]["Total Timesteps"] == paused_ts
    assert lines[0]["Total Iterations"] == 1
    assert lines[1]["Total Timesteps"] == next_target
    assert lines[1]["Total Iterations"] == 2
    
    # Verify that paused checkpoint was not corrupted
    actor_recheck = GigaNetwork(paused_ckpt, "chronos")
    for k, v in actor_recheck.state_dict().items():
        torch.testing.assert_close(v, paused_state[k], rtol=0, atol=0)
    with torch.inference_mode():
        torch.testing.assert_close(actor_recheck(probe), paused_probe_logits, rtol=0, atol=0)
    
    print(f"PASS: Resumption reached {next_target} timesteps cleanly with verified parity.")

if __name__ == "__main__":
    step1_launch_and_pause_via_stop_file()
    ckpt = step2_verify_checkpoint_integrity()
    step3_resume_and_verify_parity(ckpt)
    print("\nALL FEATURE 6 PILOT & PAUSE/RESUME CHECKS PASSED PERFECTLY!")
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
        print("PASS: Cleaned up temporary runs/pilot_chronos/ directory.")
