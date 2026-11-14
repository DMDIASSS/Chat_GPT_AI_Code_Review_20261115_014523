# GEMINI_BOT: Ghost Hybrid Architecture

## 1. Overview
**GEMINI_BOT** is an elite Rocket League AI built on the **Ghost Architecture** designed in our comprehensive guide. It resolves the core bottleneck where previous attempts to combine **Chronos** and **Galactus** produced an underperforming "student" that only achieved a ~60% win rate against Nexto (`update_271`), despite Chronos and Galactus individually crushing Nexto with a 30/31 (~97%) win rate.

---

## 2. Why the Previous Student Failed (and How We Fixed It)

### The Failure Modes of the Previous Distillation / Triad:
1. **The Probability-Blending Trap ("Compromise Collapse")**:
   - In previous attempts, distillation averaged the output distributions (e.g. Chronos 50%, Galactus 25%).
   - When Chronos recommends **shadowing back post** (Action A) and Galactus recommends **committing to a high-speed aerial pinch** (Action B), averaging their logits forces the network toward a compromise action (Action C: driving slowly in midfield without boost).
   - The student neither defended nor attacked effectively, leading to frequent whiffs and an abysmal 60% win rate against Nexto.
2. **Feature Mismatch & Predictive Blindness**:
   - **Chronos** uses a **225-dimensional** state representation with team-relative mirroring.
   - **Galactus** uses a **258-dimensional** state representation containing **5 future ball-prediction trajectory samples** (`[30, 60, 120, 180, 240]` ticks).
   - Trying to force both into a single 225-dim student stripped Galactus of its predictive aerial vision.
3. **Random Teacher Switching (`FairSelector`)**:
   - Previous versions randomly swapped teachers every decision based on age/repetition weighting. A bot cannot start an aerial with Galactus on tick 0, switch to Chronos on tick 8, and switch to Ripple on tick 16 without completely losing control of the car.

---

## 3. The Ghost Hybrid Solution in GEMINI_BOT

```
                      +-----------------------------+
                      |   Field State Observation   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |    Tactical Threat Judge    |
                      |   Threat T & Opportunity O  |
                      |   + Tactical Hysteresis     |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                     |                     |
     (Threat >= 0.50)         (Pinch Window)      (Opportunity >= 0.35)
               v                     v                     v
     +-------------------+ +-------------------+ +-------------------+
     |   CHRONOS CORE    | |   PINCH ENGINE    | |   GALACTUS CORE   |
     |  225-dim features | |   Wall/Surface    | |  258-dim features |
     |  Impenetrable Def | |   Vector Squeeze  | |  Predictive Look  |
     |  Shadow / 50-50s  | |  High-Speed Exit  | |  Aerials & Shots  |
     +---------+---------+ +---------+---------+ +---------+---------+
               |                     |                     |
               +---------------------+---------------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Native 90-Action Mask     |
                      |  (Eliminates illegal moves) |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | 120Hz Car Controller Output |
                      +-----------------------------+
```

1. **No Dilution / 100% Master Authority**:
   - When defensive pressure is high ($T \ge 0.50$), **Chronos** receives 100% control with its native 225-dim inputs and ReLU network.
   - When offensive opportunities or aerial windows open ($O \ge 0.35$), **Galactus** receives 100% control with its native 258-dim predictive vision and LeakyReLU network.
2. **Tactical Hysteresis / Commitment Lock**:
   - Once Galactus commits to an aerial strike or a pinch is initiated, the mode is locked for multiple decision steps until ball contact or recovery. The bot never oscillates mid-maneuver.
3. **Pinch & Scenario Solver**:
   - Identifies sidewall/ground pinch setups where ball velocity can be multiplied into an instant 120+ km/h goal.
4. **Provably Safe Reward Shaping**:
   - Training uses potential-based shaping $\Delta \Phi = \gamma \Phi(s') - \Phi(s)$ from `TacticalJudge.compute_potential()`. The reward telescopes across time, mathematically preventing infinite loops or reward farming.

---

## 4. File Layout

| File | Purpose |
|---|---|
| `bot.py` | RLBot entry point. Runs at 120Hz with 8-tick decision skip. Renders in-game 3D HUD. |
| `agent.py` | `GhostAgent`: loads Chronos and Galactus neural weights, evaluates Judge, and routes commands. |
| `judge.py` | `TacticalJudge`: evaluates threat levels, opportunity scores, pinch geometry, and manages hysteresis locks. |
| `obs.py` | Universal observation builder (225-dim Chronos features, 258-dim Galactus features, and ball forecast). |
| `actions.py` | 90-action lookup table and native GigaLearn action masking. |
| `benchmark_vs_nexto.py` | Autonomous headless 1v1 match runner against Nexto in RocketSim. |
| `train_scenarios.py` | Fine-tuning & scenario training script with potential-based shaping and WandB logging. |
| `scenarios.py` | Scenario generator for sidewall pinches, shadow defense saves, and kickoffs. |
| `replay_tracking.py` | Time-aligned replay tracking with tolerance and deviation termination. |
| `ballchasing_download.py` | Automated SSL 2v2/3v3 replay downloader from ballchasing.com. |
| `bot.toml` | RLBot v5 configuration file. |
| `bot.cfg` | RLBot v4 configuration file. |
| `loadout.toml` | Custom vehicle appearance (Octane). |

---

## 5. How to Run

### 1. Verify Setup:
Double-click `VERIFY.bat` or run:
```powershell
& "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" bot.py
```
Outputs diagnostics confirming neural weights are loaded and verified on CUDA/CPU.

### 2. Run Benchmark vs Nexto:
Double-click `BENCHMARK_VS_NEXTO.bat` or run:
```powershell
& "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" benchmark_vs_nexto.py --games 5 --duration 180
```
Simulates full matches in RocketSim at high speed and outputs goals, win rates, and mode breakdown.

### 3. Run Scenario & Pinch Drills:
Double-click `RUN_PINCH_DRILLS.bat` or run:
```powershell
& "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" train_scenarios.py --scenarios 100 --wandb offline
```

### 4. Play in RLBot:
Open **RLBotGUI** and add the folder `E:\Downloads\Chat_GPT_AI\GEMINI_BOT`. Both RLBot v4 (`bot.cfg`) and RLBot v5 (`bot.toml`) will detect and run `GEMINI_BOT` seamlessly.
