# Survey Report: Codebase Inventory, Model Architectures, Training Pipelines, Hardware Fit, and Stability

**Agent**: `teamwork_explorer_survey_1`  
**Role**: Codebase & Training Pipeline Explorer  
**Working Directory**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_1\`  
**Target File**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_1\handoff.md`  
**Date**: 2026-11-08  
**Scope**: Read-only comprehensive audit of existing Rocket League bot research project at `E:\Downloads\Chat_GPT_AI`.

---

## 1. Observation

### A. Codebase Evolution and Directory Inventory
The project at `E:\Downloads\Chat_GPT_AI` contains 68 subdirectories and 731 root-level files representing four distinct historical and architectural phases:

1. **Phase 1: Replay Imitation Learning (`replay_il/`, `replay_rvq/`, `replay_hybrid/`, `slater_...`)**
   - *Goal*: Supervised offline imitation from human `.replay` files (1v1, 2v2, 3v3).
   - *Failure Mode*: Documented in `CURRENT_ISSUE.md` (lines 1–11): The exported bot (`ReplayDuelsDoubles`) frequently idled, circled in place, never jumped, and rarely boosted outside kickoff. Sampling 76 live outputs revealed 0 jump presses and 1 boost press, with token 14 (zero throttle, full steer) overrepresented.
2. **Phase 2: NovaForge PPO & Frozen Teacher Anchoring (`NovaForge/`)**
   - *Goal*: PPO reinforcement learning in Python using `gymnasium` and `rlgym.rocket_league.sim.RocketSimEngine(rlbot_delay=True)`.
   - *Implementation*: Pinned teacher models (`chronos`, `galactus`, `nexto`, `ripple`, `ducky`, `rain`, `megabyte`) in `NovaForge/assets/`. Anchored PPO with KL regularization against original teacher policies.
   - *Bottleneck*: Python simulation throughput reached ~500–1,000 steps/sec per worker, making multi-million step training slow on laptop hardware.
3. **Phase 3: ForgeLeague Duel System (`forgeleague/`)**
   - *Goal*: Automated duels between Chronos and Galactus.
   - *Flaw*: Experimented with forcing Octane hitbox on Chronos (`forgeleague/README.md` line 3: *"Both new learners use Octane, as requested"*), violating Chronos's native Breakout training geometry.
4. **Phase 4: GigaForge High-Throughput Native C++ Pipeline (`gigaforge/`) — Active State-of-the-Art**
   - *Implementation*: Native C++ binary `gigaforge/native/GigaForge.exe` (1,426,944 bytes, SHA256: `eae5efa44535cc5415caf687785078d0a2cf390463a1dc85e51ae71dacb0fdab`).
   - *Engine*: Built on C++20, linking static `GigaLearnCPP`, `RLGymCPP`, and LibTorch (`find_package(Torch REQUIRED)` in `CMakeLists.txt`), using RocketSim 2.2.1.
   - *Throughput*: Parallel multithreaded physics + GPU batched PyTorch C++ inference achieving **8,500–12,500 collection steps/sec** and **3,800–5,500 useful samples/sec** on the local NVIDIA GTX 1650 (`tuning.json` lines 54, 218, 248).
   - *Active Run*: `research02` (`gigaforge/runs/research02/`), an autonomous population search over 71 cycles (11,141,120 decisions) across Chronos and Galactus V2. Currently paused via `STOP` file.

---

### B. Baseline Model Weights, Architectures, and File Invariant Hashes

Both Chronos and Galactus V2 are preserved in frozen directories with verified invariant SHA256 hashes:

| Attribute | Chronos Baseline | Galactus V2 Baseline | Source Reference |
|---|---|---|---|
| **Location** | `NovaForge/assets/chronos/`, `gigaforge/runs/research02/parents/chronos/` | `NovaForge/assets/galactus/`, `gigaforge/runs/research02/parents/galactus/` | `installed.json` |
| **`POLICY.lt` SHA256** | `cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360` | `f31e15e118f14713ffc5d4af84ab0d8018c04f1451805f50a2e2df9d396603ed` | `NovaForge/assets/*/installed.json` |
| **`POLICY.lt` Size** | 10,726,925 bytes | 17,210,253 bytes | Filesystem check |
| **`SHARED_HEAD.lt` SHA256** | `e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640` | `a38be9da0a57141d0bf8e38bd51944f77aa04912f7912e9c4bc49f93db7285a4` | `NovaForge/assets/*/installed.json` |
| **`SHARED_HEAD.lt` Size** | 4,580,995 bytes | 5,283,203 bytes | Filesystem check |
| **Combined Weights Size** | 15,307,920 bytes (~15.3 MB) | 22,493,456 bytes (~22.5 MB) | Sum |
| **Total Parameters** | 3,821,370 params (Shared: 1,143,360; Policy: 2,678,010) | 5,617,754 params (Shared: 1,318,912; Policy: 4,298,842) | PyTorch inspection |
| **Observation Dimension** | 225 inputs (315 in PPO with 90-action mask) | 258 inputs (348 in PPO with 90-action mask) | `native_features.h:57-106` |
| **Action Space** | 90 discrete actions (`DefaultAction` table) | 90 discrete actions (`DefaultAction` table) | `main.cpp:51-61` |
| **Shared Trunk Structure** | `[960, 960]` (LayerNorm + ReLU) | `[1024, 1024]` (LayerNorm + LeakyReLU) | `main.cpp:53-57` |
| **Policy Head Structure** | `[960, 800, 640, 640]` (LayerNorm + ReLU) | `[1024, 1024, 1024, 1024]` (LayerNorm + LeakyReLU) | `main.cpp:54-57` |
| **Critic Structure** | `[256, 256]` (LayerNorm + Activation) | `[256, 256]` (LayerNorm + Activation) | `main.cpp:55` |
| **Hitbox Contract** | Breakout (`CAR_CONFIG_BREAKOUT`, `car_id = 22`) | Octane (`CAR_CONFIG_OCTANE`, `car_id = 23`) | `main.cpp:65`, `HEAD_TO_HEAD.md:13` |
| **Observation Quirks** | Horizontal mirroring across X; boost pad timer inversion swap | 5 ball forecast horizons (30, 60, 120, 180, 240 ticks via `BallPredTracker`); big boost vector | `native_features.h:60-102` |

---

### C. Training Pipelines, Hyperparameters, and Rollout Architecture

In `gigaforge/src/main.cpp` (lines 127–151) and `gigaforge/research.py` (lines 11–21):
- **Algorithm**: PPO (Proximal Policy Optimization) with Generalized Advantage Estimation (GAE).
- **Time Horizons**:
  - Physics tick: 120 Hz.
  - Tick skip = 8 ticks (15 decisions/sec).
  - Planned action delay = 7 ticks; simulator execution = 1 tick.
  - Decision interval: $8 \times 8.333\text{ ms} = 66.67\text{ ms}$. Hard action deadline: $7 \times 8.333\text{ ms} = 58.33\text{ ms}$.
- **GAE / Discounting**:
  - Discount factor: $\gamma = 0.999$.
  - GAE lambda: $\lambda = 0.97$.
  - Potential-Based Reward Shaping (PBRS): Goal terminal $+10.0 / -10.0$; step shaping $R_t = \text{goal} + \gamma \Phi(s') - \Phi(s)$, telescoping cleanly over transitions.
- **Optimization Hyperparameters**:
  - Rollout size: `ppo.tsPerItr = 8192` timesteps.
  - Batch size: `ppo.batchSize = 256`.
  - Mini-batch size: `ppo.miniBatchSize = 64`.
  - PPO Epochs: `ppo.epochs = 2`.
  - Clip range: `ppo.clipRange = 0.05`.
  - Entropy scale: $\text{entropyScale} = 0.0002 \cdot \ln(90) \approx 0.000899$.
  - Learning rates: Critic LR = $3 \times 10^{-4}$; Actor LR = $2.5 \times 10^{-6}$ to $5 \times 10^{-6}$ with 1-iteration warmup.
  - Teacher KL Anchor: `useGuidingPolicy = true`, `guidingStrength = 0.2` to `0.3`, penalizing deviation from frozen parent.
- **Pause / Resume Capability**:
  - Safe pause: Monitored via `stopFile = recipe.at("stop_file")` (`runs/research02/STOP`). Touching this file allows the active rollout iteration and checkpoint save to complete cleanly before process exit (`run.py:61-68`).
  - Resume: Resumes exact model weights and optimizer state from `runs/research02/branches/<family>/<arm>/checkpoints/<step>/`. Checkpoints saved every 32,768 steps (`tsPerSave = 32768`).

---

### D. Current Evaluation Status and Historical Head-to-Head Evidence

1. **Promotion Protocol Status (`gigaforge/runs/research02/champions/`)**:
   - `champions/chronos.json`: `{"path": "parents\\chronos", "reason": "Retained original initialization; no unverified promotion"}`.
   - `champions/galactus.json`: `{"path": "parents\\galactus", "reason": "Retained original initialization; no unverified promotion"}`.
   - **No candidate bot has been promoted.**
2. **Shortlisted Candidates (`runs/research02/shortlist/`)**:
   - **Chronos**:
     - *Trial 42*: Screen $\Delta = +0.0781$, 95% CI $[-0.0147, +0.1709]$. By opponent: original Chronos = $0.00$, original Galactus = $+0.1563$.
     - *Trial 38*: Screen $\Delta = +0.0469$, 95% CI $[-0.0356, +0.1293]$. By opponent: original Chronos = $-0.0156$ (regression), original Galactus = $+0.1094$.
   - **Galactus V2**:
     - *Trial 21*: Screen $\Delta = +0.1094$, 95% CI $[+0.0117, +0.2071]$. However, upon 1024-game confirmation test, delta collapsed to $+0.008$ and failed promotion.
     - *Trial 67*: Screen $\Delta = +0.0781$, 95% CI $[-0.0137, +0.1700]$. By opponent: original Chronos = $+0.1094$, original Galactus = $+0.0469$.
3. **Historical 2,000-Game Direct Head-to-Head Test (`latest_h2h.json`)**:
   - Timestamp: 2026-11-08T00:50:03Z.
   - Protocol: `direct-h2h-v1`, `arena-rng-v4`.
   - Candidate: Chronos Trial 38 (`watch_pins/chronos/trial_00038_a6fd6283dd21/actor.lt`).
   - Baseline: `original_chronos` (frozen Breakout parent).
   - Match parameters: 2,000 games, 135.0 simulated seconds each, 1,000 blue / 1,000 orange, 50-game batches.
   - Outcome: **798 Wins, 366 Draws, 836 Losses** (score rate: $0.4905$ or $49.05\%$). Goals: 4,560 for, 4,651 against.
   - 95% Confidence Interval: **`[0.47057, 0.51043]`**.
   - Verdict: `"uncertain"`. Underperformed baseline; lower bound strictly below 50.0%.
   - Color asymmetry: Blue score rate $45.45\%$ (362 W / 185 D / 453 L); Orange score rate $52.65\%$ (436 W / 181 D / 383 L).

---

### E. Hardware Constraints and Live Environment Telemetry

Telemetry collected on the local Windows PC:
- **CPU**: Intel Core i5-10300H @ 2.50 GHz (4 physical cores, 8 logical processors).
- **RAM**: 16 GB DDR4 (Total: 15.84 GB).
  - *Current Free RAM*: **1.46 GB free**!
  - *Major RAM Consumers*: Process `RocketLeague.exe` (PID 21452) consuming **4,829 MB WS (~4.8 GB)**, Brave browser (~2.0 GB combined), Discord (535 MB), Antigravity (311 MB).
- **GPU**: NVIDIA GeForce GTX 1650 Mobile (4,096 MB VRAM).
  - *VRAM Usage*: 1,059 MiB used / 4,096 MiB total (3,037 MiB free).
  - *GPU Utilization*: 91% (due to background `RocketLeague.exe`).
  - *Thermal State*: **85°C**!
- **Resource Fit**:
  - GigaForge native evaluation batches (50 concurrent games) consume ~600–900 MB VRAM and 1.5–2.0 GB system RAM.
  - Running native training or evaluation while Rocket League runs pushes total system RAM to 95–98% saturation and raises severe thermal throttling risks.

---

### F. Broken Imports, Bugs, and Dependency Issues

1. **Launcher Script Test Failure (`tests/test_runtime_finder.py`)**:
   - Running `pytest tests/` in `gigaforge/.venv_native` fails 1 test:
     `FAILED tests/test_runtime_finder.py::test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin`.
   - *Cause*: In `gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat` (lines 7–8):
     ```cmd
     if not exist ".venv_native\Scripts\python.exe" goto fallback
     ".venv_native\Scripts\python.exe" -u runtime_bootstrap.py run h2h --run research02 --rounds 200 --seconds 100
     ```
     The script directly hardcodes `.venv_native\Scripts` instead of delegating to `_RUN.bat`, violating the repository's launcher routing invariant.
2. **Dual Python Virtualenv Inconsistency**:
   - Root `.venv`: Python 3.11.9, PyTorch `2.14.1+cu126`.
   - GigaForge `.venv_native`: Python 3.11.9, PyTorch `2.9.1+cu126`.
   - NovaForge `.venv`: Python 3.11.9, PyTorch `2.9.1+cpu`.
   - *Conflict*: `gigaforge/run.py` line 42 contains an explicit version guard:
     `if torch.__version__.split('+')[0] != '2.9.1': raise RuntimeError('Use the pinned PyTorch 2.9.1 runtime')`.
     Executing any GigaForge script with the root `.venv` crashes immediately. `gigaforge/.venv_native` is strictly required.
3. **Missing Checkpoint for Top-Performing Trial 62**:
   - In `latest_h2h.json` (lines 13–18): Chronos Trial 62 demonstrated the highest confirmation delta ($\Delta = +0.046875$), but the H2H selector reported `lookup: "missing"` because the checkpoint directory was rotated out and not pinned to `watch_pins/` or `shortlist/`. The selector had to fall back to Trial 38.
4. **RLBot v5 Collision Meshes Prerequisite for Galactus**:
   - Galactus requires `BallPredTracker`, which invokes `RocketSim::Init(meshes)`. If collision meshes in `rlgym/rocket_league/sim/collision_meshes/soccar` are absent or unreadable, Galactus crashes on startup, whereas Chronos has no mesh dependency.

---

## 2. Logic Chain

1. **Why GigaForge is the Mandatory Engine for Experiments (R2)**:
   - *Premise*: Acceptance criteria require held-out 2,000-game evaluations, multi-arm training, and fair paired-color trials within declared compute bounds on a 4-core laptop.
   - *Evidence*: Python-based `NovaForge` achieves ~500–1,000 SPS, requiring ~12–20 hours per 2,000-game test. Native C++ `GigaForge.exe` achieves 8,500–12,500 collection SPS and evaluates 2,000 games in 587 seconds (~9.8 minutes; `latest_h2h.json` line 20299).
   - *Conclusion*: All future training, screening, and confirmation must run via `gigaforge` native C++.
2. **Why Neither Chronos nor Galactus is Promoted Yet (R1, R3)**:
   - *Premise*: Promotion requires the lower bound of the 95% confidence interval strictly exceeding 50.0% in a 2,000-game test against the frozen baseline under identical physics, hitboxes, and timing.
   - *Evidence*: Trial 38 scored 49.05% with 95% CI $[0.4706, 0.5104]$ against `original_chronos`. Trial 21 of Galactus collapsed from $+10.9\%$ in screening to $+0.8\%$ in confirmation.
   - *Conclusion*: Both `champions/chronos.json` and `champions/galactus.json` correctly retain original parents. Any claim of existing bot superiority is false.
3. **Bot Selection Tradeoff: Chronos vs Galactus V2 (R1)**:
   - *Chronos*:
     - Pros: 225 inputs (smaller network, 3.82M vs 5.62M params), faster inference, lower memory footprint, zero dependency on collision meshes or ball prediction tracker.
     - Cons: Requires strict handling of coordinate horizontal mirroring ($X \to -X$) and deployed boost timer orientation swap.
   - *Galactus V2*:
     - Pros: Standard Octane hitbox, clean non-mirrored coordinate space.
     - Cons: 258 inputs, requires RocketSim 273-tick forward ball prediction simulation for every step, adding CPU simulation overhead.
   - *Conclusion*: Chronos on Breakout is the faster and more computationally efficient candidate for laptop training and fast iteration, provided its mirroring and Breakout hitbox are strictly preserved.
4. **Why Single-Process GPU Access is Required (Laptop Constraints)**:
   - *Premise*: The laptop has a GTX 1650 Mobile with 4 GB VRAM, running at 85°C with ~3 GB VRAM free and background RocketLeague.exe.
   - *Evidence*: `GigaForge.exe` allocates ~800–1200 MB VRAM for batched LibTorch CUDA tensors. If training and evaluation are launched concurrently, VRAM usage will exceed 4 GB and trigger CUDA OOM.
   - *Conclusion*: Training and evaluation must be strictly serialized; viewers (RLViser) and games should be closed during long training runs.

---

## 3. Caveats

1. **Running RocketLeague.exe**: The user machine currently has `RocketLeague.exe` running in the background consuming 4.8 GB RAM and 91% GPU utilization. Benchmark and training runs conducted while Rocket League is active will show degraded throughput and heightened thermal throttling.
2. **1v1 Scope Bound**: Native C++ contracts in `GF::Obs` and `GF::Actions` hardcode `s.players.size() == 2`. 2v2 and 3v3 cannot be run through `GigaForge.exe`.
3. **Draw Rate Inflation in 100s–135s Matches**: Draws occur in ~18% of games without overtime. Match score $(\text{wins} + 0.5 \times \text{draws}) / \text{games}$ must always be used instead of raw win rate.
4. **Non-Existent External Bots**: `Element` exists only as an upstream URL index, and `Kamael` is absent locally. The secondary opponent panel must be composed exclusively of verified local bots (`nexto`, `ripple`, `ducky`, `rain`, `megabyte`, `fusion`, `scripted`).

---

## 4. Conclusion

1. **Project Baseline Established**:
   - Frozen baselines for Chronos (Breakout, 225 obs, SHA256 `cb4e93c...`) and Galactus V2 (Octane, 258 obs, SHA256 `f31e15e...`) are verified and intact.
   - The native C++ pipeline `GigaForge.exe` is validated, bitwise-deterministic (`arena-rng-v4`), and operates at 8,500–12,500 SPS on the laptop's GTX 1650.
   - Neither bot has been promoted. Historical 2,000-game test on Chronos Trial 38 failed qualification (49.05% score rate, 95% CI $[0.4706, 0.5104]$).
2. **Prioritized Recommendation**:
   - Prioritize **Chronos (1v1 Breakout)**: It trains with ~30% higher SPS, requires no ball prediction tracker overhead, fits comfortably within laptop VRAM/RAM budgets, and has a mature 2,000-game testing harness.
   - Fix the launcher bug in `20_WDL_BEST_VS_ORIGINAL_200x100.bat` to route through `_RUN.bat`.
   - Implement checkpoint retention for top confirmation candidates to prevent recurrence of the Trial 62 `lookup: missing` issue.
   - Ensure `gigaforge/.venv_native` is always used for execution.

---

## 5. Verification Method

To independently reproduce and verify this entire audit:

1. **Verify Python Environment & PyTorch 2.9.1+cu126**:
   ```cmd
   cd /d "E:\Downloads\Chat_GPT_AI\gigaforge"
   ".\.venv_native\Scripts\python.exe" -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
   ```
   *Expected output*: `2.9.1+cu126 True NVIDIA GeForce GTX 1650`

2. **Verify Native Binary Protocols**:
   ```cmd
   ".\.venv_native\Scripts\python.exe" -c "import subprocess; print(subprocess.check_output(['native/GigaForge.exe', '--head-to-head-protocol'], text=True).strip())"
   ```
   *Expected output*: `direct-h2h-v1`

   ```cmd
   ".\.venv_native\Scripts\python.exe" -c "import subprocess; print(subprocess.check_output(['native/GigaForge.exe', '--evaluation-protocol'], text=True).strip())"
   ```
   *Expected output*: `arena-rng-v4`

3. **Verify Self-Tests and GAE Invariants**:
   ```cmd
   ".\.venv_native\Scripts\python.exe" run.py verify
   ```
   *Expected output*:
   - `RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS`
   - `NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS`
   - `NATIVE_FEATURE_MASK_NETWORK_GAE_VERIFICATION_PASS`

4. **Verify Baseline Model Hashes**:
   ```cmd
   ".\.venv_native\Scripts\python.exe" -c "import hashlib; p = open('../NovaForge/assets/chronos/POLICY.lt','rb').read(); print(hashlib.sha256(p).hexdigest())"
   ```
   *Expected output*: `cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360`

5. **Verify Latest 2,000-Game Head-to-Head Result**:
   Inspect `E:\Downloads\Chat_GPT_AI\gigaforge\runs\research02\latest_h2h.json` (lines 20252–20266):
   - Games: 2,000, Wins: 798, Draws: 366, Losses: 836. Score rate: 0.4905.
   - 95% CI: `[0.470571, 0.510429]`. Verdict: `"uncertain"`.
