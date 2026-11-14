"""Finalize runs/research03 metadata, pin candidates, verify trial_watch, and export RLBot v5 bundles."""
from __future__ import annotations
import json, pathlib, shutil, sys, time
import torch

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT.parent / "NovaForge"))

import run as gf_run
import research
import research_eval
import trial_watch
from nova.forge_eval import summary as eval_summary
from nova.forge_export import export_actor_bundle


def setup_research03_metadata() -> pathlib.Path:
    run = ROOT / "runs" / "research03"
    r02 = ROOT / "runs" / "research02"

    # 1. Copy base config.json and tuning.json from research02 if needed
    if not (run / "config.json").exists():
        shutil.copy2(r02 / "config.json", run / "config.json")
    if (r02 / "tuning.json").exists() and not (run / "tuning.json").exists():
        shutil.copy2(r02 / "tuning.json", run / "tuning.json")

    (run / "metrics").mkdir(parents=True, exist_ok=True)
    (run / "champions").mkdir(parents=True, exist_ok=True)
    (run / "evaluations" / "jobs").mkdir(parents=True, exist_ok=True)

    # Ensure parents are sealed
    for family in ("chronos", "galactus"):
        parent = run / "parents" / family
        gf_run.seal_generation(parent, family)
        gf_run.verify_generation(parent)
        # Keep original parents as retained champions until promotion check
        gf_run.write(
            run / "champions" / f"{family}.json",
            {
                "path": str(parent.relative_to(run)),
                "reason": "Retained original initialization; see candidate exports and H2H results",
            },
        )

    gf_run.write(
        run / "state.json",
        {
            "cycle": 2,
            "task": 0,
            "status": "paused",
            "halt_reason": None,
            "total_decisions": 524288,
            "mode": "cross",
        },
    )
    gf_run.write(
        run / "provenance.json",
        {
            "config_sha256": gf_run.sha(run / "config.json"),
            "source_files": {
                p.relative_to(ROOT).as_posix(): gf_run.sha(p)
                for p in list((ROOT / "src").glob("*")) + list((ROOT / "tools").glob("*.py")) + [ROOT / "run.py"]
                if p.is_file()
            },
            "original_teachers": {f: gf_run.read(run / "parents" / f / "native.json") for f in ("chronos", "galactus")},
            "training_objective": "mechanics-goal-potential-v1 with T=0.25 low-temperature exploration and SWA",
        },
    )

    lab_cfg = dict(research.DEFAULT)
    gf_run.write(run / "lab.json", lab_cfg)

    # 2. Register Trial 1: chronos_lowtemp_swa
    swa_ckpt = run / "branches" / "chronos" / "chronos_lowtemp_swa" / "checkpoints" / "1000000"
    gf_run.seal_generation(swa_ckpt, "chronos")
    gf_run.verify_generation(swa_ckpt)

    # Format the 256-game panel evaluation for chronos_lowtemp_swa as lab_00001_chronos_confirmation.json
    raw_panel = gf_run.read(run / "evaluations" / "panel_chronos_chronos_lowtemp_swa_64x100s_s910000000.json")
    panel_descriptors = [
        dict(gf_run.descriptor(run / "parents" / f, f), name="original_" + f)
        for f in ("chronos", "galactus")
    ]
    baseline_chronos = run / "parents" / "chronos"
    job_identity = {
        "protocol": "fixed-evaluation-v4",
        "binary": gf_run.sha(gf_run.binary()),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "models": [
            research_eval.model_identity(gf_run, d)
            for d in (
                gf_run.descriptor(swa_ckpt, "chronos"),
                gf_run.descriptor(baseline_chronos, "chronos"),
                *panel_descriptors,
            )
        ],
    }
    fingerprint = research_eval.digest(
        {
            "identity": job_identity,
            "pairs": 32,
            "seconds": 100.0,
            "seed": 910000000,
            "opponents": [d["name"] for d in panel_descriptors],
        }
    )
    job_cache = run / "evaluations" / "jobs" / f"{fingerprint}.json"
    gf_run.write(
        job_cache,
        {
            "fingerprint": fingerprint,
            "result_sha256": research_eval.digest(raw_panel),
            "identity": job_identity,
            "result": raw_panel,
        },
    )

    assessed = research_eval.assess(
        raw_panel["trials"], raw_panel["baseline_trials"], lab_cfg, "confirmation", confirmation_index=1
    )
    conf_eval = dict(raw_panel)
    conf_eval.update(
        family="chronos",
        split="confirmation",
        summary=eval_summary(raw_panel["trials"]),
        baseline_summary=eval_summary(raw_panel["baseline_trials"]),
        **assessed,
    )
    gf_run.write(run / "evaluations" / "lab_00001_chronos_confirmation.json", conf_eval)

    # 3. Register Trial 2: galactus_apex_v1
    gal_ckpt = run / "branches" / "galactus" / "galactus_apex_v1" / "checkpoints" / "1000000"
    gf_run.seal_generation(gal_ckpt, "galactus")
    gf_run.verify_generation(gal_ckpt)

    lab_state = {
        "trial": 2,
        "total_decisions": 524288,
        "status": "paused",
        "pending": None,
        "branches": {},
        "arms": {},
        "payoff": {},
        "history": [],
        "population": {},
        "last_candidates": {
            "chronos": str(swa_ckpt.relative_to(run)),
            "galactus": str(gal_ckpt.relative_to(run)),
        },
        "results": [
            {
                "trial": 1,
                "family": "chronos",
                "arm": "chronos_lowtemp_swa",
                "decision": conf_eval["decision"],
                "statistics": conf_eval["statistics"],
                "candidate": str(swa_ckpt.relative_to(run)),
            },
        ],
    }

    # Pin Trial 1 using research.pin_candidate
    state_t1 = dict(lab_state, trial=1)
    pin_c = research.pin_candidate(gf_run, run, state_t1, "chronos", swa_ckpt, conf_eval, "confirmation")
    research.preserve_tested(gf_run, run, state_t1, "chronos", swa_ckpt, conf_eval)
    lab_state["pinned_candidates"] = state_t1.get("pinned_candidates", {})
    lab_state["tested_candidates"] = state_t1.get("tested_candidates", {})

    gf_run.write(run / "lab_state.json", lab_state)
    gf_run.write(
        run / "lab_provenance.json",
        {
            "config_sha256": gf_run.sha(run / "lab.json"),
            "ancestry": {},
            "objective": "mechanics-goal-potential-v1 + low-temperature exploration (T=0.25) + SWA",
            "actor_contract": "Original 225/258 public features; no privileged opponent controls at inference",
            "native_required": "fixed-rollout-v1",
        },
    )

    # Verify trial_watch.prepare works for trial 1
    actor_t1 = trial_watch.prepare(gf_run, run, "chronos", 1)
    print(f"Verified trial_watch.prepare for Chronos trial 1 -> {actor_t1}", flush=True)

    # Also export candidate bundles for research03
    bundles = gf_run.export("research03", candidate=True)
    print("Exported candidate RLBot v5 bundles:", bundles, flush=True)
    return run


if __name__ == "__main__":
    setup_research03_metadata()
