"""Shared pytest fixtures, constants, and helper functions for E2E tests."""
import os
import sys
import json
import math
import hashlib
import subprocess
from pathlib import Path
import pytest
import torch

# Authoritative Root Directories
E2E_DIR = Path(__file__).resolve().parent
REPO_ROOT = E2E_DIR.parents[1]
GIGAFORGE_DIR = REPO_ROOT / "gigaforge"
NOVAFORGE_DIR = REPO_ROOT / "NovaForge"
NATIVE_EXE = GIGAFORGE_DIR / "native" / "GigaForge.exe"
VENV_PYTHON = GIGAFORGE_DIR / ".venv_native" / "Scripts" / "python.exe"

# Authoritative Baseline Hashes
BASELINE_HASHES = {
    "chronos_policy": "cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360",
    "chronos_shared": "e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640",
    "galactus_policy": "f31e15e118f14713ffc5d4af84ab0d8018c04f1451805f50a2e2df9d396603ed",
    "galactus_shared": "a38be9da0a57141d0bf8e38bd51944f77aa04912f7912e9c4bc49f93db7285a4",
}

BASELINE_SIZES = {
    "chronos_policy": 10726925,
    "chronos_shared": 4580995,
    "galactus_policy": 17210253,
    "galactus_shared": 5283203,
}

CONTRACT_SPECS = {
    "chronos": {
        "family": "chronos",
        "hitbox": "breakout",
        "car_id": 22,
        "obs_size": 225,
        "action_size": 90,
        "mirror": True,
        "tick_skip": 8,
        "planned_delay": 7,
        "latency_budget_ms": 58.333,
    },
    "galactus": {
        "family": "galactus",
        "hitbox": "octane",
        "car_id": 23,
        "obs_size": 258,
        "action_size": 90,
        "mirror": False,
        "tick_skip": 8,
        "planned_delay": 7,
        "latency_budget_ms": 58.333,
    },
}

SECONDARY_PANEL = [
    "nexto",
    "ripple",
    "ducky",
    "rain",
    "megabyte",
    "fusion",
    "scripted",
]


def sha256_file(path: Path) -> str:
    """Computes SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_student_t_margin(sample_var: float, n_pairs: int, confidence: float = 0.95) -> float:
    """Computes paired Student-t margin of error matching gigaforge/head_to_head.py."""
    if n_pairs <= 1:
        return 0.5
    if math.isnan(sample_var) or sample_var <= 0:
        return math.sqrt(math.log(40.0) / (2.0 * n_pairs))
    # Approximation of t_0.975 for degrees of freedom n_pairs - 1
    # For large n (>100), t approaches 1.96; for moderate n, use Cornish-Fisher / standard critical t
    df = n_pairs - 1
    # Robust critical t value approximation
    if df >= 1000:
        t_crit = 1.962
    elif df >= 100:
        t_crit = 1.984
    elif df >= 30:
        t_crit = 2.042
    else:
        t_crit = 2.228
    return t_crit * math.sqrt(sample_var / n_pairs)


def compute_alpha_spending(k: int, alpha_0: float = 0.05) -> float:
    """Computes sequential alpha spending allocation for confirmation step k."""
    if k < 1:
        raise ValueError("k must be >= 1")
    return alpha_0 / (k * (k + 1))


@pytest.fixture(scope="session")
def native_env():
    """Provides environment variables with PyTorch LibTorch DLL paths for GigaForge.exe."""
    env = dict(os.environ)
    torch_lib = Path(torch.__file__).parent / "lib"
    env["PATH"] = str(torch_lib) + os.pathsep + str(Path(sys.base_prefix)) + os.pathsep + env.get("PATH", "")
    env["GIGAFORGE_TORCH_LIB"] = str(torch_lib)
    env["GIGAFORGE_SIM_THREADS"] = "4"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    return env


@pytest.fixture
def sample_chronos_obs():
    """Generates a valid Float32 observation tensor for Chronos policy (B=1, 225)."""
    torch.manual_seed(42)
    return torch.randn(1, 225, dtype=torch.float32).clamp(-5.0, 5.0)


@pytest.fixture
def sample_galactus_obs():
    """Generates a valid Float32 observation tensor for Galactus policy (B=1, 258)."""
    torch.manual_seed(42)
    return torch.randn(1, 258, dtype=torch.float32).clamp(-5.0, 5.0)
