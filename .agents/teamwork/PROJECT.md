# Project: Rocket League Bot Research (GigaForge Chronos 1v1 Breakout)

## Architecture
The project is built on a high-throughput, bitwise-deterministic reinforcement learning and evaluation architecture:
- **Simulator Layer**: C++20 native binary `gigaforge/native/GigaForge.exe` linking static GigaLearnCPP, RocketSim 2.2.1, and LibTorch 2.9.1+cu126. Provides 8,500–12,500 SPS on the local NVIDIA GTX 1650.
- **Python Coordination Layer**: `gigaforge/.venv_native` (Python 3.11.9, PyTorch 2.9.1+cu126) orchestrating training (`run.py`, `research.py`), screening/confirmation (`research_eval.py`), and head-to-head evaluation (`head_to_head.py`).
- **Observation & Action Contract**:
  - Focus Target: **Chronos (1v1 Breakout)**.
  - Observation: 225-feature vector with horizontal coordinate & action mirroring ($X \to -X$) and preserved boost pad timer orientation quirk.
  - Action Space: 90 discrete actions with contact and boost masking.
  - Timing: 120 Hz physics, tick skip = 8 (15 decisions/sec), action delay = 7 ticks held + 1 tick newly applied command (hard 58.33 ms deadline).
  - Hitbox: Breakout (`CAR_CONFIG_BREAKOUT`, `car_id = 22`).
- **Reward Engine**: Potential-Based Reward Shaping (PBRS, `GoalPotential`) with 5 basis terms (goal axis pos, ball dist, goal vel, threat, challenge) and $\pm 10.0$ goal terminal.
- **Evaluation Harnesses**:
  - `direct-h2h-v1`: Paired-color, paired-seed direct head-to-head match runner against frozen `original_chronos` with Student-t 95% CI.
  - `arena-rng-v4`: Multi-opponent panel evaluation with sequential $\alpha$-spending error control ($\alpha_k = 0.05 / (k(k+1))$).
- **Packaging & Export Layer**: RLBot v5 `bot.bot.toml` + `loadout.toml` with identical TorchScript archives `actor.lt` and `actor.pt` + `.json` sidecars, running single-thread on CPU (`torch.set_num_threads(1)`).

---

## Feature Inventory

Every feature identified during Survey Phase 0 is cataloged here with its assigned milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Baseline Hash & Contract Preservation | Verify invariant SHA256 hashes for Chronos (`cb4e93...`, `e0aac6...`) and Galactus baselines | M1 | survey_1, survey_2 |
| 2 | Launcher Routing & Virtualenv Invariant | Fix `20_WDL_BEST_VS_ORIGINAL_200x100.bat` to route via `_RUN.bat` and enforce `gigaforge/.venv_native` | M1 | survey_1 |
| 3 | Native Simulator Self-Tests & GAE Verification | Execute and pass native C++ self-tests (`--selftest`, PBRS telescoping, GAE truncation, body checks) | M1 | survey_2 |
| 4 | Resource Boundaries & Safe Telemetry Monitoring | Declare and enforce wall-time, RAM/VRAM limits, and verify thermal/process safety before long runs | M2 | survey_1 |
| 5 | Candidate Checkpoint Retention System | Protect top screening and confirmation checkpoints from rotation deletion (resolve Trial 62 missing bug) | M2 | survey_1 |
| 6 | Bounded Pilot Training & Resumption Verification | Run short bounded training cycle (1-2 iterations) and verify clean pause/resume via `STOP` file | M2 | survey_1, survey_2 |
| 7 | Chronos Targeted Model Optimization | Execute bounded PPO training with matched controls, teacher KL anchor, and PBRS potential arms | M3 | survey_1, survey_2 |
| 8 | Multi-Arm Screening via `arena-rng-v4` Dev Split | Screen population candidates on 32 seed pairs (128 games/opp) to filter for $\Delta \ge 0.03$ | M3 | survey_2 |
| 9 | Candidate Confirmation Split Evaluation | Evaluate top screening candidates on 128 seed pairs (512 games/opp) under sequential $\alpha$-spending | M3 | survey_2 |
| 10 | Secondary Opponent Panel Evaluation | Benchmark frozen candidate against fixed panel (`nexto`, `ripple`, `ducky`, `rain`, `megabyte`, `fusion`, `scripted`) | M4 | survey_3 |
| 11 | Regression Tolerance Verification | Validate per-opponent score rates against declared regression tolerances | M4 | survey_3 |
| 12 | Held-Out 2,000-Game Direct H2H Evaluation | Run frozen candidate against `original_chronos` using `direct-h2h-v1` on fresh confirmation seeds | M5 | survey_1, survey_2 |
| 13 | Statistical Confidence Interval & Promotion Gate | Predeclare Student-t paired-color 95% CI; lower bound > 50.0% required for promotion, else preserve baseline | M5 | survey_1, survey_2 |
| 14 | RLBot v5 TOML & Loadout Packaging | Generate `bot.bot.toml` and `loadout.toml` with `car_id = 22` (Breakout) for RLBot v5 | M6 | survey_3 |
| 15 | Model Dual Serialization & Sidecar Generation | Export identical `actor.lt` and `actor.pt` TorchScript archives with contract metadata JSON | M6 | survey_3 |
| 16 | Logit & Argmax Action Parity Verification | Enforce zero-tolerance numerical (`rtol=0, atol=0`) and argmax action parity between source and export | M6 | survey_3 |
| 17 | CPU-Only Deployment & Single-Thread Enforcement | Enforce `map_location='cpu'` and `torch.set_num_threads(1)` for isolated export inference | M6 | survey_3 |
| 18 | End-to-End Latency Benchmarking vs 58.33ms Deadline | Measure full callback time (packet -> obs -> inference -> controller) against 58.33 ms limit | M6 | survey_3 |
| 19 | Windows Launcher Suite Verification | Validate `INSTALL.bat` and `DIAGNOSE.bat` self-contained offline execution | M6 | survey_3 |
| 20 | Read-Only Discord Governance & Provenance Logging | Maintain provenance of all models, configs, seeds, and keep Discord research read-only and offline | M1-M6 | survey_3 |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Correctness Audit & Environment Hardening | Features 1, 2, 3, 20: Fix launcher routing, verify `.venv_native` PyTorch 2.9.1 runtime, run all unit/regression tests, verify baseline hashes and native self-tests. | none | DONE |
| M2 | Bounded Pilot & Resource Boundary Controls | Features 4, 5, 6: Establish RAM/VRAM/thermal limits, implement candidate checkpoint retention, run bounded pilot training with safe pause/resume verification. | M1 | IN_PROGRESS |
| M3 | Chronos Model Optimization & Arena Screening | Features 7, 8, 9: Execute versioned training runs with matched controls for Chronos (1v1 Breakout), evaluate dev split screening, and run confirmation split evaluation under $\alpha$-spending. | M2 | PLANNED |
| M4 | Secondary Opponent Panel Evaluation | Features 10, 11: Benchmark leading candidate against the fixed secondary opponent panel (`nexto`, `ripple`, `ducky`, `rain`, `megabyte`, `fusion`, `scripted`), report per-opponent changes and verify regression tolerances. | M3 | PLANNED |
| M5 | Held-Out 2,000-Game Direct H2H Evaluation & Promotion Gate | Features 12, 13: Execute frozen candidate in 2,000-game test via `direct-h2h-v1` on fresh seeds against `original_chronos`; compute 95% CI; decide promotion or baseline preservation without manufacturing success. | M4 | PLANNED |
| M6 | Packaging, RLBot v5 Export & Latency Verification | Features 14, 15, 16, 17, 18, 19: Export bot to RLBot v5 TOML + loadout + identical `.lt`/`.pt`, verify zero-tolerance logit parity, verify CPU execution and latency < 58.33 ms, test Windows launchers. | M5 | PLANNED |

---

## Interface Contracts

### Python Coordinator ↔ Native C++ Engine (`GigaForge.exe`)
- **CLI Flags**:
  - `--head-to-head-protocol` -> prints `direct-h2h-v1\n`
  - `--evaluation-protocol` -> prints `arena-rng-v4\n`
  - `--selftest` -> exits 0 with self-test pass assertions
  - JSON recipe via stdin / temp file:
    ```json
    {
      "family": "chronos",
      "hitbox": "breakout",
      "anchor": "parents/chronos",
      "checkpoints": "branches/chronos/arm/checkpoints",
      "stop_file": "runs/research02/STOP",
      "metrics_file": "runs/research02/metrics.jsonl",
      "games": 50,
      "tsPerItr": 8192
    }
    ```
- **Stop File Protocol**: Touching `runs/research02/STOP` signals `GigaForge.exe` to complete current iteration, write checkpoint and metrics, and exit cleanly with code 0.

### Chronos Policy Contract
- **Input Observation**: Float32 tensor shape `(B, 225)`, range normalized approximately `[-5, 5]`.
- **Horizontal Mirroring**: If car $X > 0$, mirror $X \to -X$, angular velocity $Y, Z \to -Y, -Z$, boost pad indices across Y-axis, controls `steer`, `yaw`, `roll` negated.
- **Hitbox**: Breakout (`CAR_CONFIG_BREAKOUT`, `car_id = 22`).
- **Output Action**: Discrete index in `[0, 89]` mapped via `DefaultAction` table to 8 controls: `[throttle, steer, pitch, yaw, roll, jump, boost, handbrake]`.

### RLBot v5 Export Contract
- **Root Directory**: Contains `bot.bot.toml`, `loadout.toml`, `actor.lt`, `actor.pt`, `actor.lt.json`, `actor.pt.json`, `run_forge.py`, `INSTALL.bat`, `DIAGNOSE.bat`.
- **Deployment Device**: CPU only (`torch.set_num_threads(1)`, `map_location='cpu'`).
- **Latency Budget**: Total callback latency (packet parse + obs build + forward pass + action decode) strictly $< 58.33\text{ ms}$ (7 physics ticks at 120 Hz).

---

## Code Layout
- `gigaforge/` — Primary native RL and evaluation platform
  - `native/GigaForge.exe` — High-throughput C++20 simulator & LibTorch runner
  - `src/` — C++ source files (`main.cpp`, `native_features.h`, `evaluate.h`, `checks.h`)
  - `run.py`, `research.py`, `research_eval.py`, `head_to_head.py` — Python coordination scripts
  - `.venv_native/` — Pinned Python 3.11 + PyTorch 2.9.1+cu126 environment
  - `runs/research02/` — Active research run state, checkpoints, logs, and `latest_h2h.json`
- `NovaForge/` — Teacher assets and RLBot v5 integration harnesses
  - `assets/` — Frozen baseline teacher models (`chronos`, `galactus`, `nexto`, `ripple`, etc.)
  - `nova/` — Export utilities (`forge_export.py`, `forge_models.py`, `giga_teachers.py`)
- `tests/` — Repository test suite and protocol verification scripts
- `.agents/teamwork/` — Agent coordination metadata, plans, and reports

---

## Resource & Hardware Limits
- **Laptop Hardware**: Intel Core i5-10300H (4 cores, 8 threads), NVIDIA GTX 1650 Mobile (4GB VRAM), 16GB RAM.
- **Concurrent Gaming & Process Protection**: NEVER terminate, close, or interfere with `RocketLeague.exe`, `EpicGamesLauncher.exe`, or any user game/application. Respect concurrent gaming by keeping GigaForge within strict memory/thread bounds (`GIGAFORGE_SIM_THREADS=2` to `4`, VRAM <= 1.8 GB) and throttling/pausing training rather than closing user applications.
- **Memory Boundaries**:
  - Max GigaForge VRAM allocation: $\le 1.8\text{ GB}$.
  - Max System RAM allocation: $\le 4.0\text{ GB}$.
- **Thermal Threshold**: GPU temperature must remain $< 85^\circ\text{C}$; throttle or halt if exceeded.
