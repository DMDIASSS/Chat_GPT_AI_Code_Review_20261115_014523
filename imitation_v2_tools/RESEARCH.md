# Findings from repos and supplied Discord archives

## Decision: what to reuse rather than rewrite

1. **Rolv-Arild/replicar v2** is the most relevant current replay-control reconstruction library. It takes `.replay` -> RocketSim reconstructed states/inputs -> Parquet. Air pitch/yaw/roll and input timings are inferred, **not ground truth**; `car_<i>_air_controls_source` identifies where inputs came from. Save diagnostic provenance and reconstruct error on held-out matches. This is more defensible than writing a new control fitter without physics verification. `replay-pretraining` explains why past+future can help infer missing replay controls (IDM), but an IDM should be used to *create offline labels*, never to inject future game state into online model inputs.
2. **Rolv-Arild/python-ballchasing** and the documented Ballchasing API are useful for downloading/manifests, but the public API's highest named rank is `grand-champion`, not numeric `GC3–SSL` filters visible in the page UI. Filename/rank claims are not verified without metadata/IDs. Download quota is lower than listing quota.
3. **ZealanL/RocketSim** is the relevant fast, approximate physics engine for replay reconstruction and later short-rollout planning. Physics prediction drifts over long horizons; include observed state corrections. RocketSim meshes are needed. **VirxEC/rocketsim-rs** is a Rust binding useful if a future 64-way search is CPU-constrained; benchmark against existing C++/Python bridges rather than assuming 64×1s is fast enough.
4. **ZealanL/RLGym-PPO-Guide** and **PiggyVevo/GigalearnGuide** are useful for Windows build prerequisites, metrics, checkpoints, CPU/GPU simulation speed, and evaluation discipline. Their PPO `ent_coef`, PPO batch sizes, reward shaping, and self-play configuration **do not transfer to this pure imitation recipe**. GigaLearn's W&B and optional skill-tracker are examples of performance monitoring, not evidence that offline cloning has improved.

## Archived RLGym `#imitation-learning` and RLBot discussions

The supplied Discord archive has ~6,900 messages in `#imitation-learning`, ~9,000 in `#ml-lounge`, ~4,300 in `#rocketsim`, ~9,500 in `#rlgym-learn`, ~3,200 in `#rlgym-tools` and ~68,700 in RLBot `#machine-learning`. I inspected the text/keyword themes and relevant discussions rather than treating every unverified claim as authoritative.

- Rolv observed that replay actors other than the recording player can have noisier/interpolated states (`#imitation-learning` message `990937507279548467`). That argues for per-car update freshness and source confidence in training weights.
- The archive discusses reconstructing action with a **history and future window** (e.g., Waddles, message `990813224888856576`) and the fact certain inputs are not identifiable from some dynamics. Distinguish action-label inference from the actual causal policy.
- Multiple archived messages acknowledge **train/validation leakage** from overlapping windows / data reshuffling (Waddles messages `991648370995249162`, `992368361088503928`, `992430153294696498`). This strongly supports split-by-replay before generating any chunk.
- Rotational inputs are missing in `.replay`; original `replay-pretraining` later included replay-supplied boost, throttle, steering, and jump/dodge constraints while inferring air controls. Don't overstate label certainty.
- The `#rocketsim` channel has relevant physics mismatch reports and binding compatibility discussions. In message `1074818803256541294`, Zealan describes an intentionally omitted input sensitivity/deadzone adjustment in a then-current implementation. Version pinning and direct validation matter.
- `#rlgym-learn` centers on PPO pipelines, not supervised video/replay cloning. For this project we reuse concepts of reproducibility, logging and checkpoint separation, not policy gradient updates.

## Suggested experiment order

- Stage 0: verify replay hashes, playlists, identifiers, durations and provenance. Reject short/noisy/unsupported data only after inspecting it; currently 7 replays are <100KB and their validity is undetermined. Reserve 10% complete matches for test, never inspect them during optimization.
- Stage 1: use `replicar` on 1v1, inspect conversion failures, imputed vs replay-recorded inputs, held-out drift, train 8-step raw action chunks; compare against simple repeat-last-action baseline. Do not claim original source is SSL without rank metadata.
- Stage 2: collect 2v2 and train balanced mode representation with opponent/teammate slots; evaluate each mode separately. Compare a mixed model against per-mode ablations.
- Stage 3: request TAS plugin/source + confirmation of input bit fields, analog scale, tick rate and initial state and map. Re-simulate exactly before training TAS as a small, mechanics-specific corpus; never mix unverified TAS labels with ranked match behavior cloning.
- Stage 4: learn a calibrated long/short horizon value head, only after verifying that positives are not overwhelmed by the no-goal class; report Brier/calibration and end-of-clip selection. This initial value head is only an outcome classifier, **not an action-specific value function**.
- Stage 5: implement conditional action tokens (VQ or discrete sequence palette), 64 candidate sampling, batch RocketSim 1s rollouts, select by checked calibrated value, profile p95 latency. Compare against unplanned policy and rule-based safety baseline on model-only kickoff scenarios. If planner hurts, do not ship it.

## What we still need

- **TAS exporter/plugin repo or download URL**, explanation of `.data` record layout and whether its trailing 128 bytes encode initial car+ball state; tick rate and map/mod dependencies.
- **`collision_meshes` directory** (path only, not Git-uploaded assets), replicar executable build/install result, or terminal error output. A minimal processed sample Parquet plus index errors will let us verify real-column compatibility without transferring all matches.
- **Hardware**: Windows version, CPU model/cores, NVIDIA GPU and VRAM, available RAM and storage. Needed to choose batch/worker count, and to establish 64-rollout viability.
- **Ballchasing account/API access**: obtain and keep a token locally; send only manifest or nonsecret download/error logs. Provide rank/mode verification rules/priority (strict GC3–SSL vs broad GC+ balance) and the number of matches desired.
- **RLBot deployment**: Which RLBot version/API, action tick rate, and model runner will be used for actual games? Code/checkpoints of the unpublished new imitation model, if it already exists, so this baseline can be integrated instead of duplicated.
