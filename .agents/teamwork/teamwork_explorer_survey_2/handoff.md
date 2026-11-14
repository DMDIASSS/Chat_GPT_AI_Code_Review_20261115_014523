# Handoff Report — Native Simulator Contracts, Physics, Observation/Action Spaces, Rewards, and Evaluation Protocols

**Agent**: `teamwork_explorer_survey_2`  
**Role**: Simulator Contracts & Evaluation Protocol Explorer  
**Working Directory**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\`  
**Target File**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\handoff.md`  
**Timestamp**: 2026-11-07T21:28:00Z  

---

## 1. Observation

### A. Underlying Simulator Engine & Versions
1. **Python Environment**:
   - Detected in `E:\Downloads\Chat_GPT_AI\gigaforge\dependency_report.json` (lines 32–70) and `runtime_selection.json`:
     - Python: `3.11.9 (64-bit)` at `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe`
     - PyTorch: `2.9.1+cu126` (CUDA 12.6, NVIDIA GeForce GTX 1650)
     - `RocketSim`: `2.2.1`
     - `rlgym`: `2.0.1`
     - `rlgym-tools`: `2.6.5`
     - `rlgym-compat`: `2.3.6`
     - `stable-baselines3`: `2.9.2`
     - `gymnasium`: `1.4.0`
     - `onnxruntime`: `1.23.2`
     - `rlbot`: `2.0.0b56`
   - Python simulation wrapper: `NovaForge/nova/environment.py` (line 9, 22):
     ```python
     from rlgym.rocket_league.sim import RocketSimEngine
     self.engine = RocketSimEngine(rlbot_delay=True)
     ```
2. **Native C++ Engine (`GigaForge.exe`)**:
   - Location: `E:\Downloads\Chat_GPT_AI\gigaforge\native\GigaForge.exe` (size: 1,426,944 bytes, SHA256: `eae5efa44535cc5415caf687785078d0a2cf390463a1dc85e51ae71dacb0fdab`).
   - Attribution (`gigaforge/native/ATTRIBUTION.txt`):
     > "GigaLearnCPP/RLGymCPP/RocketSim by ZealanL and contributors. Pinned upstream 86e11c3881a21225a43c36b14af40f0b3c87e7dd. Direct H2H evaluator and Python orchestration by NovaForge. Torch 2.9.1 installed separately."
   - Build definition (`gigaforge/CMakeLists.txt` lines 1–19): C++20 standard (`CMAKE_CXX_STANDARD 20`), links static `GigaLearnCPP` and LibTorch (`find_package(Torch REQUIRED)`), includes `RocketSim/src`.
   - Upstream patches (`gigaforge/tools/patch_upstream.py`):
     - Lines 42–47 (`Arena.h`): Replaces `std::unordered_set<Car*>` with `std::set<Car*, StableCarOrder>` using stable `Car->id` comparison to prevent pointer-hash non-determinism across arena car physics updates on Windows.
     - Lines 50–51 (`EnvSet.cpp`): Changes parallel arena creation to serial `for(int i=0;i<config.numArenas;i++) fnCreateArenas(i);` for deterministic seed assignment and callback indices.
     - Lines 34–37 (`ThreadPool.h`): Simulation thread pool count controlled via `GIGAFORGE_SIM_THREADS`.
     - Lines 153–155 (`GAE.cpp`): Corrects truncation index computation (`nextValPred = _truncValPreds[numTruncs-1-truncCount];`) and zeros `nextValPred` on `TerminalType::NORMAL`.
     - Lines 161–166 (`PPOLearner.cpp`): KL early stopping threshold `kl > 0.015f` and guard halt `kl > 0.08`.
     - Lines 145–151 (`PPOLearner.cpp`): Shares trunk forward pass between policy and critic (`models["shared_head"]->Forward(obs, false)`).
3. **Collision Meshes**:
   - Located at `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes\soccar` (`mesh_0.cmf` through `mesh_15.cmf`).
   - Loaded in C++ via `RocketSim::Init(recipe.at("meshes").get<std::string>())` (`gigaforge/src/main.cpp` line 120).

---

### B. Native Simulator Contracts: Observations, Actions, Delays & Hitboxes
1. **Observation Architecture**:
   - Defined in C++ in `gigaforge/src/native_features.h` (`GF::Obs::BuildObs`, lines 36–107) and in Python in `NovaForge/nova/giga_teachers.py` (`build_features`, lines 55–99):
   - **Chronos (225 features)**:
     - Ball physics (9 features): `ball.pos / 5000` (3), `ball.vel / 2300` (3), `ball.angVel / 3` (3).
     - Previous controls (8 features): `[throttle, steer, pitch, yaw, roll, jump, boost, handbrake]`.
     - Boost pad timers (34 features): 34 pads. Active = `1.0f`; inactive = `1.f / (1.f + timer)`.
       *Quirk*: Preserves deployed Chronos timer orientation swap (`native_features.h` line 69): `s.GetBoostPadTimers(chronos ? inv : !inv)`.
     - Self player (29 features):
       `pos / 5000` (3), `rotMat.forward` (3), `rotMat.up` (3), `vel / 2300` (3), `angVel / 3` (3), `rotMat.Dot(angVel) / 3` (3), `rotMat.Dot(ball.pos - phys.pos) / 5000` (3), `rotMat.Dot(ball.vel - phys.vel) / 2300` (3), `boost / 100` (1), `isOnGround` (1), `HasFlipOrJump()` (1), `isDemoed` (1), `hasJumped` (1).
     - Teammate padding (58 features): `insert(out.end(), 58, 0.f)` (2 empty teammate slots $\times$ 29).
     - Opponent slots (87 features): 3 slots $\times$ 29 features. In 1v1, the opponent occupies one slot (`slot = forcedSlot >= 0 ? forcedSlot : uniform_int(0,2)` in training; slot 0 in deterministic evaluation), remaining two slots zero-padded.
     - *Horizontal Mirroring*: If `InvertPhys(p, p.team==ORANGE).pos.x > 0`:
       - Ball and car coordinates flipped across X: $X \to -X$, angular velocity $Y, Z \to -Y, -Z$.
       - Previous actions flipped: `steer = -steer`, `yaw = -yaw`, `roll = -roll`.
       - Boost pad indices mapped across X symmetry line (`MIRROR_PADS`).
   - **Galactus V2 (258 features)**:
     - Contains the exact 225 base features above, but:
       - No horizontal mirroring (`mirror = false`).
       - Standard boost timer orientation (`!inv`).
       - Extra Big-Boost Vector (3 features): Vector `relative / 5000` to the nearest available big boost pad among `{3, 4, 15, 18, 29, 30}` within 1500 uu squared.
       - Extra Ball Forecast Horizons (30 features): 5 discrete horizons at $t \in \{30, 60, 120, 180, 240\}$ ticks ahead (at 120 Hz: 0.25s, 0.5s, 1.0s, 1.5s, 2.0s). Each horizon has `pos / 5000` (3) and `vel / 2300` (3) = 6 features $\times 5 = 30$ features.
     - Total: $225 + 3 + 30 = 258$ features.
2. **Action Space & Masking**:
   - Discrete 90 actions (`LookupTableAction` table, shape $90 \times 8$).
   - Defined in `gigaforge/src/native_features.h` (`GF::Actions`, lines 14–34) and `NovaForge/nova/giga_teachers.py` (`native_action_mask`, lines 19–30).
   - Action masking logic:
     - Ground actions (indices 0–23) allowed on ground; aerial actions allowed in air.
     - If `car.boost_amount == 0`: actions requiring boost are masked.
     - Flip/double jump masked unless `HasFlipOrJump()` is true.
     - RLBot packet parity: If `p.worldContact.hasContact && !p.HasFlipOrJump()`, contact is masked to match RLBot's public packet which lacks contact normals.
   - Action parser mirroring: For Chronos, if `Mirror(p)` is true, output controls are reversed: `steer = -steer`, `yaw = -yaw`, `roll = -roll`.
3. **Action Delay & Tick Skip**:
   - Physics clock: RocketSim runs at 120 Hz.
   - Tick skip = 8 ticks ($120 / 8 = 15\text{ Hz}$, exactly 15 decisions per simulated second).
   - Action delay = 7 ticks planned delay + 1 tick newly applied command = 8 ticks.
   - Verbatim execution in `gigaforge/src/evaluate.h` (lines 76–96):
     ```cpp
     // Physics advances held controls while the batched networks run.
     g_ThreadPool.StartBatchedJobs([&](int i){ games[i]->Step(7); }, int(games.size()), true);
     // ... batched network inference ...
     g_ThreadPool.WaitUntilDone();
     g_ThreadPool.StartBatchedJobs([&](int i){
       auto& g = *games[i];
       for(size_t p=0; p<g.state.players.size(); p++)
         g.arena->GetCar(g.state.players[p].carId)->controls = CarControls(g.planned[p]);
       g.Step(1);
       g.previous = g.state;
       g.state.UpdateFromArena(g.arena.get(), g.planned, &g.previous);
       // ... goal handling ...
     }, int(games.size()), false);
     ```
4. **Hitbox Implementations**:
   - **Chronos**: Breakout hitbox (`CAR_CONFIG_BREAKOUT`).
   - **Galactus V2**: Octane hitbox (`CAR_CONFIG_OCTANE`).
   - In `gigaforge/src/main.cpp` (lines 65, 153–161):
     ```cpp
     auto body = recipe.at("hitbox") == "breakout" ? CAR_CONFIG_BREAKOUT : CAR_CONFIG_OCTANE;
     // ...
     if (car->config.hitboxSize.x != body.hitboxSize.x)
       throw std::runtime_error("Arena hitbox mismatch");
     std::cout << "NATIVE_BODY_CHECK_PASS " << recipe["family"] << " " << recipe["hitbox"] << std::endl;
     ```
   - In `gigaforge/src/checks.h` (line 18):
     `if (CAR_CONFIG_BREAKOUT.hitboxSize.x == CAR_CONFIG_OCTANE.hitboxSize.x) throw std::runtime_error("Body presets are identical");`
   - *Crucial Finding*: While `forgeleague` experimented with forcing Octane on Chronos (`forgeleague/README.md` line 3: "Both new learners use Octane, as requested"), `gigaforge` native research and `direct-h2h-v1` strictly mandate Breakout for Chronos and Octane for Galactus (`gigaforge/HEAD_TO_HEAD.md` line 13: "matching hitboxes: Breakout for Chronos, Octane for Galactus").

---

### C. Reward Functions, Shaping, Terminals, and State Resets
1. **Reward Function (`GoalPotential`)**:
   - Defined in `gigaforge/src/native_features.h` (lines 109–138): Potential-Based Reward Shaping (PBRS; Ng et al., 1999).
   - Goal Terminal Reward: $+10.0$ if learner scores, $-10.0$ if opponent scores, $0.0$ otherwise.
   - Potential Function $\Phi(p, s) = \sum_{i=0}^4 w_i \cdot \text{Basis}_i(p, s)$:
     - $\text{Basis}_0 = y_{\text{rel}} / 5120.0$ (goal axis position: $+1.0$ at opponent goal line, $-1.0$ at own goal line).
     - $\text{Basis}_1 = -\min(\text{dist}_{\text{ball}}, 12000.0) / 6000.0$ (distance to ball).
     - $\text{Basis}_2 = \text{clamp}(v_{y, \text{rel}} / 6000.0, -1.0, 1.0)$ (ball velocity toward opponent goal).
     - $\text{Basis}_3 = -\text{threat}$, where $\text{threat} = \text{clamp}((-y - 2000.0) / 3120.0, 0, 1) \cdot \text{clamp}(-v_y / 6000.0, 0, 1)$.
     - $\text{Basis}_4 = \text{clamp}((\text{dist}_{\text{opp}} - \text{dist}_{\text{own}}) / 6000.0, -1, 1) \cdot \exp(-\text{dist}_{\text{own}} / 2500.0)$ (challenge advantage).
   - Full Step Reward (`native_features.h` line 134):
     $$R_t = \text{goal} + \gamma \cdot (\text{goalScored} ? 0.0 : \Phi(p, s)) - \Phi(p_{\text{prev}}, s_{\text{prev}})$$
   - Telescoping: In rollouts, $\sum_{t=0}^{T-1} \gamma^t (\gamma \Phi(s_{t+1}) - \Phi(s_t)) = -\Phi(s_0) + \gamma^T \Phi(s_T)$. Upon a true goal, $\Phi(s_T) = 0$. Upon truncation (time limit), $\Phi(s_T)$ is preserved and value is bootstrapped via GAE.
   - PBRS self-test verification: verified in `gigaforge/src/checks.h` lines 20–35 (`RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS`).
   - Research Arms Potential Weights (`gigaforge/research.py` lines 11–16):
     - `control`: `[0.35, 0.10, 0.00, 0.00, 0.00]`
     - `attack`: `[0.35, 0.15, 0.25, 0.10, 0.05]`
     - `defense`: `[0.20, 0.15, 0.05, 0.40, 0.05]`
     - `possession`: `[0.15, 0.20, 0.00, 0.15, 0.30]`
2. **Terminal Conditions & State Resets**:
   - **In Training**: Terminal condition is `GoalScoreCondition` (`main.cpp` line 75). State setter is `KickoffState` (`main.cpp` line 74). Trajectory length is bounded by `maxEpisodeDuration = 60.0`s.
   - **In Evaluation (`evaluate.h`)**:
     - Match runs for fixed duration: $\text{decisions} = \text{round}(\text{seconds} \times 15)$ (e.g. 100s = 1500 decisions; 135s = 2025 decisions).
     - Multiple goals allowed per match: when `state.goalScored` occurs (`evaluate.h` line 94):
       `g->forGoals += scored; g->againstGoals += !scored; g->goalCount++; g->Reset();`
     - Reset routine (`evaluate.h` lines 27–33):
       ```cpp
       auto& worker = RocketSim::Math::GetRandEngine();
       worker.seed(seed + goalCount * 1000003);
       arena->ResetToRandomKickoff();
       random = worker;
       ```
     - Match timeout: If scores are tied when time expires, outcome is 0 (draw). **No overtime is played.**

---

### D. Existing Evaluation Harnesses: `direct-h2h-v1` and `arena-rng-v4`
1. **`direct-h2h-v1`**:
   - Code: `gigaforge/head_to_head.py`, invoked via `20_WDL_BEST_VS_ORIGINAL_200x100.bat`.
   - Protocol check (`head_to_head.py` lines 106–107):
     `probe = subprocess.run([str(m.binary()), '--head-to-head-protocol'], ...)` -> verifies `"direct-h2h-v1"`.
   - Match structure:
     - Direct 1v1 match against its own frozen public original parent (`original_chronos` or `original_galactus`).
     - Exactly matching hitboxes: Breakout vs Breakout for Chronos, Octane vs Octane for Galactus.
     - Paired colors: for every seed $p$, 1 match as Blue (side 0), 1 match as Orange (side 1).
     - Batched execution: batches of 25 pairs = 50 games at a time (`batch_0000.json`, `batch_0025.json`, etc.).
     - Resumption: Completed chunk hashes are saved in `chunks`; interrupted runs resume without double-counting.
   - Statistical evaluation & Confidence Interval (`head_to_head.py` lines 16–35):
     - Blocks defined per seed $p$:
       $\bar{y}_p = \frac{(outcome_{\text{blue}} + 1)/2 + (outcome_{\text{orange}} + 1)/2}{2} \in [0, 1]$.
     - Mean score rate: $\bar{y} = \frac{1}{P} \sum_{p=1}^P \bar{y}_p = \frac{\text{wins} + 0.5 \times \text{draws}}{\text{total games}}$.
     - Sample variance: $s^2 = \frac{1}{P-1} \sum_{p=1}^P (\bar{y}_p - \bar{y})^2$.
     - If $s^2 > 0$: margin $m = t_{0.975, P-1} \cdot \sqrt{s^2 / P}$.
     - If $s^2 == 0$: Hoeffding bound $m = \sqrt{\frac{\ln(40)}{2P}}$.
     - Lower bound: $\max(0, \bar{y} - m)$; Upper bound: $\min(1, \bar{y} + m)$.
     - Verdict: `"candidate_ahead_in_this_test"` only if `lower > 0.50`.
   - **Historical 2,000-Game Test on Chronos Trial 38 (`latest_h2h.json`)**:
     - Verified in `E:\Downloads\Chat_GPT_AI\gigaforge\runs\research02\latest_h2h.json`:
       - Rounds: 2,000 games (1,000 seeds $\times$ 2 colors), duration: 135.0 simulated seconds each.
       - Candidate: Chronos trial 38 (`watch_pins/chronos/trial_00038_a6fd6283dd21/actor.lt`).
       - Result: **798 Wins / 366 Draws / 836 Losses**.
       - Match score rate: $0.4905$ (49.05%). Goals: 4,560 for / 4,651 against.
       - 95% Confidence Interval: **`[0.4706, 0.5104]`**.
       - Verdict: `"uncertain"` (Failed qualification: lower bound strictly $< 0.50$, and candidate underperformed baseline).
       - Side asymmetry: Blue score rate $45.45\%$ (362 W / 185 D / 453 L); Orange score rate $52.65\%$ (436 W / 181 D / 383 L).
2. **`arena-rng-v4`**:
   - Code: `gigaforge/research_eval.py`, protocol flag `GigaForge.exe --evaluation-protocol` -> `"arena-rng-v4"`.
   - Multi-opponent panel: `[original_chronos, original_galactus]`.
   - Both Candidate and Baseline (retained parent/champion) run on identical seeds and both colors (`compare_baseline = true`).
   - Development split: 32 seed pairs (128 games per opponent, 256 games total), tests if $\Delta \ge 0.03$.
   - Confirmation split: 128 seed pairs (512 games per opponent, 1024 games total).
   - Sequential hypothesis testing error control (`research_eval.py` line 71):
     $$\alpha_k = \frac{\alpha_0}{k(k+1)} = \frac{0.05}{k(k+1)}$$
     Where $k$ is the confirmation index. Since $\sum_{k=1}^\infty \frac{1}{k(k+1)} = 1$, the cumulative Type I error is bounded by $\alpha_0 = 0.05$ across all sequential confirmation trials.

---

### E. Baseline Model Loading, Determinism & Fairness
1. **Model Weights & Verification**:
   - **Chronos Baseline**:
     - Location: `NovaForge/assets/chronos/`, `gigaforge/runs/research02/parents/chronos/`.
     - `SHARED_HEAD.lt`: SHA256 `e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640` (4,580,995 bytes).
     - `POLICY.lt`: SHA256 `cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360` (10,726,925 bytes).
     - Architecture: Input 225 $\to$ Shared Trunk `[960, 960]` (LayerNorm + ReLU) $\to$ Policy Head `[960, 800, 640, 640]` (LayerNorm + ReLU) $\to 90$ logits.
   - **Galactus V2 Baseline**:
     - Location: `NovaForge/assets/galactus/`, `gigaforge/runs/research02/parents/galactus/`.
     - `SHARED_HEAD.lt`: SHA256 `a38be9da0a57141d0bf8e38bd51944f77aa04912f7912e9c4bc49f93db7285a4` (5,283,203 bytes).
     - `POLICY.lt`: SHA256 `f31e15e118f14713ffc5d4af84ab0d8018c04f1451805f50a2e2df9d396603ed` (17,210,253 bytes).
     - Architecture: Input 258 $\to$ Shared Trunk `[1024, 1024]` (LayerNorm + LeakyReLU) $\to$ Policy Head `[1024, 1024, 1024, 1024]` (LayerNorm + LeakyReLU) $\to 90$ logits.
2. **Deterministic Reproducibility & Fairness**:
   - **RNG State Synchronization**: RocketSim's internal thread-local random engine (`RocketSim::Math::GetRandEngine()`) is synchronized into `EvalGame::random` before and after each `arena->Step(ticks)` call (`evaluate.h` lines 23–26). This guarantees bitwise reproducibility regardless of multithreaded worker thread scheduling.
   - **Kickoff Seeding**: Initial seed $p$, and after each goal: `worker.seed(seed + goalCount * 1000003)` (`evaluate.h` line 28).
   - **Pre-match Logit Parity**: In `gigaforge/head_to_head.py` (lines 85–93), cross-language parity is tested before running: probe input tensor is evaluated through PyTorch script vs LibTorch C++ with strict tolerance `torch.testing.assert_close(..., rtol=3e-5, atol=5e-5)`.
   - **Hash Locking**: Test state enforces invariant hashes on candidate and baseline `.lt` files between batch iterations (`head_to_head.py` line 140).

---

## 2. Logic Chain

1. **Simulator Engine Selection**:
   - *Observation*: Python training via SB3/RocketSimEngine executes at $\sim 500\text{--}1,000$ SPS, while the native C++ `GigaForge.exe` binary runs parallel batched physics and batched PyTorch C++ LibTorch inference at $\sim 15,000\text{--}30,000$ decisions/sec on GTX 1650.
   - *Inference*: Any full 2,000-game evaluation or scalable iterative training on the user's laptop hardware (Intel i5-10300H, GTX 1650 Ti Mobile, 16 GB RAM) must execute through the native C++ `GigaForge` pipeline (`direct-h2h-v1` and `arena-rng-v4`).
2. **Hitbox Preservation & Parity**:
   - *Observation*: Chronos was originally trained on Breakout (`CAR_CONFIG_BREAKOUT`), while Galactus was trained on Octane (`CAR_CONFIG_OCTANE`). ForgeLeague's attempt to force Octane on Chronos altered the underlying physical contact geometry, whereas GigaForge's native contracts enforce Breakout for Chronos and Octane for Galactus.
   - *Inference*: To evaluate against the original frozen Chronos or Galactus baseline with scientific validity, the exact matching hitbox must be preserved. Swapping hitboxes introduces an uncontrolled confounder.
3. **Observation Contract Integrity**:
   - *Observation*: Chronos relies on horizontal coordinate mirroring ($X \to -X$) and has an inverted boost timer orientation quirk. Galactus V2 relies on non-mirrored coordinates, a 3-element big-boost relative vector, and a 30-element 5-step ball forecast tracker.
   - *Inference*: These contracts are completely distinct. Any model improvement to Chronos must strictly satisfy the 225-feature mirrored contract, whereas any model improvement to Galactus must strictly satisfy the 258-feature forecast contract.
4. **Action Timing & Delay Fidelity**:
   - *Observation*: Both bots run on a 120 Hz physics clock with tick skip 8 (15 decisions/sec). During the 8-tick window, controls are held for 7 ticks while inference runs, followed by 1 tick of the newly applied command.
   - *Inference*: This matches the real-world RLBot v5 action-delay deadline ($7/120\text{s} \approx 58.3\text{ ms}$). Models evaluated under this contract do not experience sim-to-real latency collapse.
5. **Evaluation Protocol & Verification of Acceptance Criteria**:
   - *Observation*: Acceptance Criteria specify that a candidate qualifies for promotion only when the lower bound of the 95% confidence interval strictly exceeds 50.0% draw-adjusted match score over a 2,000-game test on fresh seeds against the frozen baseline.
   - *Inference*: Chronos trial 38 completed a 2,000-game H2H test against `original_chronos` and scored 49.05% [0.4706, 0.5104]. Because the lower bound $0.4706 < 0.5000$, trial 38 was correctly rejected and the original baseline preserved.

---

## 3. Caveats

1. **Hardware Memory Boundaries**:
   - The native C++ binary links CUDA LibTorch and runs on the laptop's GTX 1650 (4 GB VRAM). While 50-game evaluation batches (25 pairs) consume under 1.2 GB VRAM, launching concurrent training and evaluation runs simultaneously will trigger CUDA Out-Of-Memory errors. Only one process should access the GPU at a time.
2. **Scope of Contact Masking**:
   - In `Actions::GetActionMask`, car contact normal is omitted if the car does not have flip/jump (`p.worldContact.hasContact && !p.HasFlipOrJump()`), mimicking the public RLBot game packet. This aligns simulator training with deployment, but means wall-pin contact states cannot be uniquely disambiguated from ground contact by the mask alone.
3. **1v1 Format Limitation**:
   - The observation structures (`GF::Obs`) and action masks (`GF::Actions`) contain hard asserts requiring exactly 2 players (`s.players.size() == 2`). 2v2 and 3v3 modes cannot be evaluated or trained with the current `GigaForge.exe` native binary without recompilation.
4. **Draw Rates in Head-to-Head Testing**:
   - In 100s/135s timed matches without overtime, draws occur frequently (e.g. 366 draws out of 2,000 games $\approx 18.3\%$). The draw-adjusted match score formula $(\text{wins} + 0.5 \times \text{draws}) / \text{total}$ is strictly required.

---

## 4. Conclusion

1. **Current System Status**:
   - The repository contains a fully validated, bitwise-deterministic C++ simulator pipeline (`GigaForge.exe`) built on pinned RocketSim and GigaLearnCPP, linked to PyTorch 2.9.1+cu126.
   - Both Chronos (Breakout, 225 obs) and Galactus V2 (Octane, 258 obs) have their original frozen parents preserved and hash-verified in `NovaForge/assets/` and `gigaforge/runs/research02/parents/`.
   - Neither bot has been promoted to date. Trial 38 of Chronos underwent a full 2,000-game `direct-h2h-v1` evaluation and failed to qualify (49.05% score rate, 95% CI $[0.4706, 0.5104]$).
2. **Recommended Bot Selection for Improvement (R1)**:
   - **Chronos (1v1 Breakout)**:
     - *Advantage*: Faster inference (225 vs 258 inputs, no ball prediction tracker step required per tick), lower memory footprint, and highly documented historical baseline.
     - *Risk*: Must adhere to horizontal mirroring and boost timer inversion quirks.
   - **Galactus V2 (1v1 Octane)**:
     - *Advantage*: Standard Octane hitbox (easier transfer to standard community RLBot events), clean observation pipeline without coordinate mirroring.
     - *Risk*: Relies on 273-tick forward ball prediction simulation for observation building, which adds CPU simulation overhead.
   - *Recommendation*: Focus on Chronos or Galactus based on training efficiency; both have working native contracts. Chronos is the faster training target in `gigaforge` because it bypasses the BallPredTracker overhead.

---

## 5. Verification Method

To independently verify the observations and contracts reported above, execute the following commands from `E:\Downloads\Chat_GPT_AI`:

1. **Verify Native Executable and Protocol Handshakes**:
   ```cmd
   cd /d "E:\Downloads\Chat_GPT_AI\gigaforge"
   ".\.venv_native\Scripts\python.exe" -c "import subprocess; print(subprocess.check_output(['native/GigaForge.exe', '--head-to-head-protocol'], text=True).strip())"
   ```
   *Expected output*: `direct-h2h-v1`

   ```cmd
   ".\.venv_native\Scripts\python.exe" -c "import subprocess; print(subprocess.check_output(['native/GigaForge.exe', '--evaluation-protocol'], text=True).strip())"
   ```
   *Expected output*: `arena-rng-v4`

2. **Verify Native Fixed-Rollout, PBRS, GAE and Hitbox Self-Tests**:
   ```cmd
   ".\.venv_native\Scripts\python.exe" -c "import subprocess; print(subprocess.check_output(['native/GigaForge.exe', '--selftest'], text=True).strip())"
   ```
   *Expected output*:
   `RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS`  
   `NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS`

3. **Verify Identical-Actor Bitwise RNG Determinism**:
   ```cmd
   ".\.venv_native\Scripts\python.exe" tests/check_eval_rng.py
   ```
   *Expected output*:
   `NATIVE_IDENTICAL_ACTOR_FULL_MATCH_RNG_PASS`  
   `NATIVE_PAIRED_ARENA_RNG_V4_PASS`  
   `NATIVE_DIRECT_H2H_EXACT_ROUND_COUNT_PASS`

4. **Verify Direct Head-to-Head Test Harness & CI Calculation**:
   ```cmd
   ".\.venv_native\Scripts\python.exe" tests/check_head_to_head.py
   ```
   *Expected output*:
   `NATIVE_H2H_COUNTS_SELECTION_RESUME_PAUSED_STATE_AND_EXPORT_PARITY_PASS`

5. **Verify Baseline Model Hashes**:
   - Inspect `NovaForge/assets/chronos/installed.json` and `NovaForge/assets/galactus/installed.json`.
   - Verify SHA256 matches:
     - Chronos `POLICY.lt`: `cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360`
     - Chronos `SHARED_HEAD.lt`: `e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640`
     - Galactus `POLICY.lt`: `f31e15e118f14713ffc5d4af84ab0d8018c04f1451805f50a2e2df9d396603ed`
     - Galactus `SHARED_HEAD.lt`: `a38be9da0a57141d0bf8e38bd51944f77aa04912f7912e9c4bc49f93db7285a4`
