"""Finalize runs/research04 metadata, pin the defensive Chronos candidate, export RLBot v5 bundle, and verify latency."""
from __future__ import annotations
import json, pathlib, shutil, subprocess, sys, time
import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parent
NOVA = ROOT.parent / "NovaForge"
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(NOVA))

import run as gf_run
import research
import research_eval
import trial_watch
from nova.forge_eval import summary as eval_summary
from nova.forge_export import LiveDriver


def finalize_research04(selected_branch: str = "chronos_defensive_swa") -> None:
    run = ROOT / "runs" / "research04"
    r03 = ROOT / "runs" / "research03"

    for f in ("config.json", "tuning.json"):
        if (r03 / f).exists() and not (run / f).exists():
            shutil.copy2(r03 / f, run / f)

    (run / "metrics").mkdir(parents=True, exist_ok=True)
    (run / "champions").mkdir(parents=True, exist_ok=True)
    (run / "evaluations" / "jobs").mkdir(parents=True, exist_ok=True)

    # Preserve original parents as official retained champions
    for family in ("chronos", "galactus"):
        parent = run / "parents" / family
        gf_run.seal_generation(parent, family)
        gf_run.verify_generation(parent)
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
            "previous_preview": gf_run.read(run / "parents" / "chronos_lowtemp_swa" / "native.json"),
            "training_objective": "mechanics-defense-v2 with reachability/shadow-intercept shaping, 30% defensive curriculum, T=0.25, and SWA",
        },
    )

    lab_cfg = dict(research.DEFAULT)
    gf_run.write(run / "lab.json", lab_cfg)

    cand_ckpt = run / "branches" / "chronos" / selected_branch / "checkpoints" / "1000000"
    gf_run.seal_generation(cand_ckpt, "chronos")
    gf_run.verify_generation(cand_ckpt)

    # Also copy galactus_apex_v1 so export("research04", candidate=True) exports both families cleanly
    gal_src = r03 / "branches" / "galactus" / "galactus_apex_v1" / "checkpoints" / "1000000"
    gal_dst = run / "branches" / "galactus" / "galactus_apex_v1" / "checkpoints" / "1000000"
    gal_dst.mkdir(parents=True, exist_ok=True)
    for fn in gal_src.iterdir():
        if fn.is_file() and not (gal_dst / fn.name).exists():
            shutil.copy2(fn, gal_dst / fn.name)
    gf_run.seal_generation(gal_dst, "galactus")
    gf_run.verify_generation(gal_dst)

    # Run a paired 64-seed panel evaluation or format confirmation evaluation for trial_watch / head_to_head
    parent_c = run / "parents" / "chronos"
    parent_g = run / "parents" / "galactus"
    panel_descriptors = [
        dict(gf_run.descriptor(parent_c, "chronos"), name="original_chronos"),
        dict(gf_run.descriptor(parent_g, "galactus"), name="original_galactus"),
    ]
    panel_out = run / "evaluations" / f"panel_chronos_{selected_branch}_64x100s_s810000000.json"
    if not panel_out.exists():
        spec = {
            "candidate": gf_run.descriptor(cand_ckpt, "chronos"),
            "baseline": gf_run.descriptor(parent_c, "chronos"),
            "compare_baseline": True,
            "opponents": panel_descriptors,
            "pairs": 32,
            "seconds": 100.0,
            "seed": 810000000,
            "output": str(panel_out),
            "stop_file": str(run / "STOP"),
        }
        recipe = {
            "family": "chronos",
            "hitbox": "breakout",
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "torch_threads": 2,
            "meshes": str(pathlib.Path(gf_run.__file__).resolve().parent),
            "evaluation": spec,
        }
        import rlgym.rocket_league.sim as sim
        recipe["meshes"] = str(pathlib.Path(sim.__file__).parent / "collision_meshes")
        gf_run.launch(recipe, log=run / "evaluations" / f"panel_{selected_branch}.log")

    raw_panel = gf_run.read(panel_out)
    job_identity = {
        "protocol": "fixed-evaluation-v4",
        "binary": gf_run.sha(gf_run.binary()),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "models": [
            research_eval.model_identity(gf_run, d)
            for d in (
                gf_run.descriptor(cand_ckpt, "chronos"),
                gf_run.descriptor(parent_c, "chronos"),
                *panel_descriptors,
            )
        ],
    }
    fingerprint = research_eval.digest(
        {
            "identity": job_identity,
            "pairs": 32,
            "seconds": 100.0,
            "seed": 810000000,
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
            "chronos": str(cand_ckpt.relative_to(run)),
            "galactus": str(gal_dst.relative_to(run)),
        },
        "results": [
            {
                "trial": 1,
                "family": "chronos",
                "arm": selected_branch,
                "decision": conf_eval["decision"],
                "statistics": conf_eval["statistics"],
                "candidate": str(cand_ckpt.relative_to(run)),
            },
        ],
    }
    state_t1 = dict(lab_state, trial=1)
    research.pin_candidate(gf_run, run, state_t1, "chronos", cand_ckpt, conf_eval, "confirmation")
    research.preserve_tested(gf_run, run, state_t1, "chronos", cand_ckpt, conf_eval)
    lab_state["pinned_candidates"] = state_t1.get("pinned_candidates", {})
    lab_state["tested_candidates"] = state_t1.get("tested_candidates", {})

    gf_run.write(run / "lab_state.json", lab_state)
    gf_run.write(
        run / "lab_provenance.json",
        {
            "config_sha256": gf_run.sha(run / "lab.json"),
            "ancestry": {
                "original_chronos": gf_run.sha(parent_c / "POLICY.lt"),
                "chronos_lowtemp_swa": gf_run.sha(run / "parents/chronos_lowtemp_swa/POLICY.lt"),
            },
            "objective": "mechanics-defense-v2 + 30% defensive curriculum + T=0.25 + SWA",
            "actor_contract": "Original 225/258 public features; no privileged opponent controls at inference",
            "native_required": "fixed-rollout-v1",
        },
    )

    actor_t1 = trial_watch.prepare(gf_run, run, "chronos", 1)
    print(f"Verified trial_watch.prepare for research04 Chronos trial 1 -> {actor_t1}", flush=True)

    bundles = gf_run.export("research04", candidate=True)
    print("Exported research04 RLBot v5 bundles:", bundles, flush=True)

    # Verify source/export logit parity and 64-tick CPU latency
    from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
    cases = json.loads((NOVA / "tests/fixtures/giga_reference.json").read_text())["cases"]
    state = deserialize_game_state(np.asarray(cases[0]["state"], np.float32))
    agent_id = next(iter(state.cars.keys()))
    rng = np.random.default_rng(271031)

    latency_report = {}
    for b in bundles:
        diag = subprocess.run([sys.executable, str(b / "run_forge.py"), "--diagnose"], cwd=str(b), capture_output=True, text=True, check=True)
        driver = LiveDriver(b / "actor.lt")
        for i in range(8):
            state.tick_count = i * 8
            driver.controls(state, agent_id, rng, 0, 100.0)
        times = []
        for i in range(64):
            state.tick_count = (i + 10) * 8
            t0 = time.perf_counter()
            driver.controls(state, agent_id, rng, 0, 100.0)
            times.append((time.perf_counter() - t0) * 1000.0)
        latency_report[b.name] = {
            "bundle": str(b),
            "diagnose_output": (diag.stdout + diag.stderr).strip(),
            "mean_ms": float(np.mean(times)),
            "p99_ms": float(np.percentile(times, 99)),
            "max_ms": float(np.max(times)),
            "deadline_ms": 58.333,
        }
        print(b.name, json.dumps(latency_report[b.name], indent=2), flush=True)
    (run / "export_latency.json").write_text(json.dumps(latency_report, indent=2), encoding="utf8")
    gf_run.report("research04")


if __name__ == "__main__":
    branch = sys.argv[1] if len(sys.argv) > 1 else "chronos_defensive_swa"
    finalize_research04(branch)
