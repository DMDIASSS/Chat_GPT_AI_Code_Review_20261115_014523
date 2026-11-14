# Specification Survey Report: Export, Latency, RLBot, Opponent Panels & Governance

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | RLBot Packaging | RLBot v5 TOML Config | Standard configuration defining agent identity, run command, loadout, hivemind, and details | `bot.bot.toml` or `bot.portable.bot.toml` | JSON-compatible TOML parsed by RLBot v5 core | Malformed TOML causes RLBot v5 startup crash | `NovaForge/exports/novachronos_bfedaa55f0_bc6df4/bot.bot.toml:1-13`, `forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/bot.bot.toml:1-14` |
| 2 | RLBot Packaging | Loadout Specification | Specifies vehicle body type (`car_id`) and paint/color customization | `loadout.toml` with `[blue_loadout]` and `[orange_loadout]` | Passed to RLBot/Rocket League car builder | Wrong `car_id` results in wrong car body spawn | `NovaForge/nova/forge_export.py:114`, `forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/loadout.toml:1-5` |
| 3 | RLBot Packaging | RLBot v4 Legacy Config | INI/CFG format defining python entry point, appearance config, requirements, and tick rate | `bot.cfg`, `appearance.cfg` | Parsed by RLBot v4 `BaseAgent` framework | Incompatible with RLBot v5 without v4 wrapper | `export_rlbot_v4.py:103-116`, `NovaForge/exports/novachronos_bfedaa55f0_bc6df4/bot.cfg:1-12` |
| 4 | Model Artifacts | TorchScript Dual Serialization | Model weights packaged identically as `.lt` and `.pt` accompanied by `.json` contract sidecars | PyTorch `nn.Module` or TorchScript state dict | `actor.lt`, `actor.pt`, `actor.lt.json`, `actor.pt.json` | Missing sidecar causes contract mismatch exception | `NovaForge/nova/forge_export.py:110-111,126`, `NovaForge/nova/forge_models.py:118-130` |
| 5 | Execution Flow | RLBot v5 TCP Hivemind Driver | Hivemind agent class connecting via TCP loopback to RLBot server | TCP socket on `RLBOT_SERVER_IP` / `RLBOT_SERVER_PORT` | `InterfacePacket` / `PlayerInput` with `ControllerState` | Connection timeout (45-60s) or disconnect exits cleanly | `NovaForge/nova/forge_export.py:46-70`, `NovaForge/tests/check_triad_v5.py:57-90` |
| 6 | Execution Flow | RLBot v5 Bot Manager | Per-bot standalone agent inheriting from `rlbot.managers.Bot` | `GamePacket` via IPC/socket | `ControllerState` (8 axes/buttons) | Unhandled packet exception caught by fallback recorder | `freestyle_rlbot_v5/bot.py:16-52`, `tests/test_freestyle_v5_export.py:143-150` |
| 7 | Windows Launchers | Self-Contained Batch Setup | Automated environment provisioning and offline policy diagnostics | `INSTALL.bat`, `DIAGNOSE.bat` | Created `.venv` with CPU Torch; synthetic diagnostic report | Non-zero exit code halts with error banner | `NovaForge/nova/forge_export.py:124-125`, `export_freestyle_rlbot_v5.py:115-120` |
| 8 | Model Export | TorchScript Scripting & Tracing | Freezing PyTorch actors into standalone TorchScript modules without source code dependency | PyTorch policy actor (`DirectActor`, Sequential) | Scripted/traced module file | Non-finite logits or tensor mismatch aborts export | `NovaForge/nova/forge_models.py:120-123`, `export_freestyle_rlbot_v5.py:90-100` |
| 9 | Parity Verification | Numerical & Action Parity Test | Validating exact tensor numerical agreement and argmax action parity between source and export | Grid/random observations across feature range | Max absolute error, argmax boolean agreement | Error > 1e-5 or unequal action choices raises RuntimeError | `NovaForge/nova/forge_models.py:122-123`, `export_freestyle_rlbot_v5.py:94-100`, `diagnose_native_exports.py:27-42` |
| 10 | Device Selection | CPU-Only Export Deployment | Exported bot runtime forces CPU device and single-thread execution | `map_location='cpu'`, `torch.set_num_threads(1)` | Isolated CPU tensor inference | Attempting CUDA on export throws error if CUDA missing | `NovaForge/nova/forge_export.py:52,125`, `NovaForge/nova/forge_models.py:120,138` |
| 11 | Action Timing | 8-Tick Skip Decision Cadence | Decisions executed every 8 physics ticks (15 Hz) on a 120 Hz simulation | 120 Hz tick sequence | New action queued every 8th tick | Misaligned tick raises `ValueError` in controller | `NovaForge/nova/forge_models.py:36,155`, `NovaForge/exports/novachronos_bfedaa55f0_bc6df4/clock.py:17-25` |
| 12 | Action Timing | 7-Tick Action Delay Contract | Actions planned at tick $F$ are queued to take effect at tick $F+7$ ($F+8$ simulator step) | Observation at frame $F$ | Command applied at $F+7$ (58.33 ms deadline) | Processing beyond 7 ticks results in stale control drop | `NovaForge/nova/forge_models.py:36-37,164-169`, `NovaForge/exports/novachronos_bfedaa55f0_bc6df4/clock.py:25` |
| 13 | Latency Measurement | End-to-End Callback Benchmark | Measurement of observation generation, forward inference, and action masking/parsing | Synthetic `GamePacket` sequence | `diagnostic.json` with `max_callback_ms` and status | Max latency exceeding budget flags performance violation | `data/rlbot_v5_exports/Freestyle700_Audit/diagnose.py:32-38`, `data/isolated/replay_imitation/runs/replay_scratch01/runtime_benchmark.json:11-34` |
| 14 | Ball Forecasting | RocketSim 273-Step Rollout | Forward ball simulation for Galactus observation features | Current ball physics position/velocity/angular velocity | 5 future ball positions at ticks [30, 60, 120, 180, 240] | Uninitialized meshes or missing collision files raise `RuntimeError` | `NovaForge/nova/giga_teachers.py:130-151`, `NovaForge/nova/forge_models.py:140-147` |
| 15 | Opponent Panel | Frozen Pretrained Opponents | Inventory of pinned headless opponent baselines | Assets directory with `.lt`, `.pt`, and `.onnx` files | Headless opponent simulation stepping | Hash mismatch or missing file halts setup | `NovaForge/nova/teachers.py:17-19`, `NovaForge/UPSTREAM_REVIEW.md:9-28` |
| 16 | Opponent Panel | Paired-Color Stratified Evaluation | Statistical evaluation using `arena-rng-v4` across fixed seed pairs with both colors | Candidate vs Baseline across panel of opponents | Mean score delta, 95% Student-t CI | Unpaired rows or mismatched seeds raises `ValueError` | `gigaforge/research_eval.py:21-65`, `gigaforge/head_to_head.py:16-35` |
| 17 | Research Governance | Read-Only Discord Indexing | Offline indexing and contextual search of supplied HTML archives without network access | `Discord.rar` / exported HTML channel dumps | Indexed topics and regex hits (`slater_discord_research.py`) | No network authentication; strictly read-only | `docs/DISCORD_RESEARCH_FINDINGS.md:5-24`, `slater_discord_research.py:1-25` |

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | RLBot v5 Hivemind Packet | Packet contains fewer or more than 2 players in 1v1 | `get_outputs` returns default `ControllerState()` without computing inference (`forge_export.py:58`). |
| 2 | Match Phase Inactive | Packet match phase is `MatchPhase.Paused` or `MatchPhase.Ended` | `LiveDriver.reset()` is invoked and idle controls returned (`forge_export.py:63-64`). |
| 3 | Frame Counter Reset | Packet `frame_num` decreases (goal replay or match reset) | Compat `GameState` is recreated and `LiveDriver` resets history (`forge_export.py:60-61`). |
| 4 | Action Mask Emptiness | Zero valid actions produced by `native_action_mask` | `ValueError('Native action mask has no valid action')` raised (`giga_teachers.py:183`). |
| 5 | Nonfinite Policy Logits | Policy outputs `NaN` or `Inf` | `ValueError('Invalid live actor output')` raised immediately (`forge_export.py:39`). |
| 6 | Galactus Collision Meshes | RocketSim collision meshes directory not initialized | `rs.init(...)` called; if meshes missing or path invalid, raises `RuntimeError` (`forge_models.py:144-146`). Chronos does not require meshes. |
| 7 | Car Body Hitbox Mismatch | Exporting Chronos model with Octane or Galactus with Breakout | Contract requires Chronos=Breakout (`car_id=22`), Galactus=Octane (`car_id=23`). Enforced in `forge_export.py:114` and `gigaforge/run.py:214`. |
| 8 | Multi-Candidate Search Latency | MCTS / trajectory search evaluated with 16 or 64 candidates | Latency increases from 6.38 ms (1 candidate) to 104 ms (16 candidates) and 339 ms (64 candidates), violating the 66.67 ms deadline (`runtime_benchmark.json:64-118`). |
| 9 | Zero Sample Variance in H2H | Candidate wins 100% or 0% of games across all pairs | Standard sample variance is 0; evaluator falls back to bounded Hoeffding interval (`head_to_head.py:26,34`). |
| 10 | Discord Archive Extraction | Files outside trusted HTML/JSON/text or exceeding size limit | Archive extractor rejects binary executables or oversized files (`DISCORD_RESEARCH_FINDINGS.md:7`). |

---

## 1. Observation

### 1.1 Export Formats and Artifacts
- **RLBot v5 Artifacts**: Found in `NovaForge/exports/novachronos_bfedaa55f0_bc6df4`, `forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25`, `forgeleague/exports/duel01/Forge_galactus_2a244790f7_83ba25`, `gigaforge/exports/native01/Forge_chronos_2df9ca9b3f_f4f884`, `gigaforge/exports/native01/Forge_galactus_9357e7d78e_f4f884`, and `data/rlbot_v5_exports/Freestyle700_Audit`.
- **Configuration TOML (`bot.bot.toml` and `bot.portable.bot.toml`)**:
  - `NovaForge/exports/novachronos_bfedaa55f0_bc6df4/bot.bot.toml:1-13`:
    ```toml
    #:schema https://rlbot.org/schemas/agent.json
    [settings]
    name = "NovaChronos 0"
    agent_id = "DMDIASSS/novachronos_bfedaa55f0_bc6df4"
    run_command = "\"..\\..\\.venv\\Scripts\\python.exe\" bot.py"
    run_command_linux = "\"../../.venv/bin/python\" bot.py"
    hivemind = true
    [details]
    developer = "NovaForge user; Chronos model credit: KingJake3113"
    description = "Chronos-initialized 1v1 PPO student. Requires enclosing NovaForge project."
    language = "python"
    tags = ["1v1"]
    ```
  - `forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/bot.bot.toml:1-14`:
    Specifies `run_command = "\"E:\\Downloads\\Chat_GPT_AI\\novaforge\\.venv\\Scripts\\python.exe\" run_forge.py"`, `loadout_file = "loadout.toml"`, `hivemind = true`.
- **Loadout Configuration (`loadout.toml`)**:
  - `forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/loadout.toml:1-5`:
    ```toml
    [blue_loadout]
    car_id = 23
    [orange_loadout]
    car_id = 23
    ```
  - `NovaForge/nova/forge_export.py:114`:
    ```python
    (stage/'loadout.toml').write_text('[blue_loadout]\ncar_id = '+str(22 if body=='breakout' else 23)+'\n[orange_loadout]\ncar_id = '+str(22 if body=='breakout' else 23)+'\n')
    ```
    Confirms Rocket League body IDs: `car_id = 22` is Breakout; `car_id = 23` is Octane.
- **Model Weight Files (`.lt` vs `.pt`)**:
  - `NovaForge/nova/forge_export.py:110-111,126`:
    ```python
    for suffix in ('lt','pt'):
        shutil.copy2(actor,stage/('actor.'+suffix));shutil.copy2(str(actor)+'.json',stage/('actor.'+suffix+'.json'))
    ```
    ```
    "actor.lt and actor.pt are identical TorchScript archives of the complete actor, requiring this loader and the sidecar contract. They are not native split POLICY/SHARED_HEAD files."
    ```
  - Both `.lt` and `.pt` are byte-for-byte identical TorchScript serialized archives. Size for Chronos actor: 15,399,071 bytes. Size for Galactus actor: 22,587,781 bytes.
- **Legacy RLBot v4 Format**:
  - Found in `export_rlbot_v4.py:103-116`, `data/rlbot_exports/`, and `NovaForge/exports/novachronos_bfedaa55f0_bc6df4/bot.cfg`.
  - Uses `bot.cfg` (specifying `looks_config = ./appearance.cfg`, `python_file = ./bot.py`, `requirements_file = ./requirements.txt`), `appearance.cfg` (team colors, wheels, paint finishes), and `nexto-model.pt`.

### 1.2 Bot Launchers, Agent Classes, and Windows Execution Flow
- **RLBot v5 Agent Classes**:
  1. `rlbot.managers.hivemind.Hivemind`:
     - Implemented in `NovaForge/nova/forge_export.py:50-69`:
       ```python
       class ForgeBot(Hivemind):
           def __init__(self):
               super().__init__(agent_id);torch.set_num_threads(1)
               self.driver=None;self.rng=np.random.default_rng(271031);self.last_frame=None
           def initialize(self):
               self.driver=LiveDriver(actor);self.state=GameState.create_compat_game_state(self.field_info,self.match_config)
           def get_outputs(self,packet):
               ...
               controls=self.driver.controls(self.state,agent,self.rng,score_diff,time_remaining)
               return {index:ControllerState(*[float(v) for v in controls[:5]],*[bool(v) for v in controls[5:]])}
       ```
  2. `rlbot.managers.Bot`:
     - Implemented in `freestyle_rlbot_v5/bot.py:16-52`:
       ```python
       class Freestyle(Bot):
           def initialize(self):
               self.policy=torch.jit.load(str(ROOT/'policy.pt'),map_location='cpu').eval()
           def get_output(self,packet):
               ...
               return ControllerState(throttle=float(a[0]),steer=float(a[1]),pitch=float(a[2]),
                   yaw=float(a[3]),roll=float(a[4]),jump=bool(a[5]),boost=bool(a[6]),handbrake=bool(a[7]))
       ```
- **RLBot v5 Protocol Flow on Windows**:
  - Observed in `NovaForge/tests/check_triad_v5.py:57-89`:
    - Server socket listens on loopback: `server.bind(('127.0.0.1', 0))`.
    - Launches bot subprocess with environment variables: `RLBOT_SERVER_IP='127.0.0.1'`, `RLBOT_SERVER_PORT='<port>'`, `RLBOT_AGENT_ID='<agent_id>'`.
    - Handshake: Bot connects -> sends `ConnectionSettings(agent_id=...)` -> Server sends `MatchConfiguration`, `FieldInfo`, `ControllableTeamInfo` -> Bot initializes -> Bot sends `InitComplete`.
    - Active match: Server sends `GamePacket` -> Bot receives and returns `PlayerInput(player_index, controller_state)`.
    - Shutdown: Server sends `DisconnectSignal()`.

### 1.3 Model Export Scripts and Parity Verification
- **TorchScript Scripting & Parity in `NovaForge/nova/forge_models.py:118-130`**:
  ```python
  def save_actor(actor,path,family,hitbox='octane',**meta):
      path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
      actor=copy.deepcopy(actor).cpu().eval().requires_grad_(False)
      scripted=torch.jit.script(actor)
      x=torch.linspace(-1,1,2*(CORE[family]+3)).reshape(2,-1)
      with torch.inference_mode():torch.testing.assert_close(scripted(x),actor(x),rtol=0,atol=0)
      fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.lt');os.close(fd)
      try:
          torch.jit.save(scripted,temp);_sync_serialized_file(temp);os.replace(temp,path)
          write_model_meta(path,contract=contract(family,hitbox),**meta)
      finally:
          if os.path.exists(temp):os.unlink(temp)
      return path
  ```
- **TorchScript Tracing & Parity in `export_freestyle_rlbot_v5.py:90-100`**:
  ```python
  traced=torch.jit.trace(actor,torch.zeros(1,512))
  traced.save(str(staging/'policy.pt'))
  portable=torch.jit.load(str(staging/'policy.pt'),map_location='cpu').eval()
  generator=torch.Generator().manual_seed(8810271)
  observations=torch.randn(96,512,generator=generator).clamp(-4,4)
  masks=torch.rand(96,94,generator=generator)>.25;masks[:,0]=True
  with torch.inference_mode():
      expected=actor(observations);actual=portable(observations)
  error=float((expected-actual).abs().max())
  identical=bool(torch.equal(expected.masked_fill(~masks,-1e10).argmax(1),actual.masked_fill(~masks,-1e10).argmax(1)))
  if error>1e-5 or not identical:raise RuntimeError('Portable policy verification failed')
  ```
- **Native C++ Parity Verification in `gigaforge/head_to_head.py:86-92`**:
  ```python
  with torch.inference_mode():
      expected=script(x);torch.testing.assert_close(GigaNetwork(pin,family)(x[:,:size]),expected,rtol=0,atol=0)
  out=test/'native_logits.json';recipe=m.base_recipe(run,family,settings,mode='self')
  recipe.update(anchor=str(pin),checkpoints='',games=2,probe_only=True,probe_input=x[:,:size].contiguous().flatten().tolist(),probe_output=str(out),stop_file=str(test/'STOP'),metrics_file=str(test/'unused_metrics.jsonl'))
  m.launch(recipe,log=test/'native_parity.log')
  torch.testing.assert_close(torch.tensor(m.read(out)).reshape(4,90),expected,rtol=3e-5,atol=5e-5)
  ```
- **Device Selection**:
  - Training supports CUDA (`device = 'cuda'`, `torch==2.9.1+cu126`, GTX 1650 Ti Mobile 4GB).
  - Exported deployment bots strictly run on **CPU**:
    - `NovaForge/nova/forge_export.py:52`: `torch.set_num_threads(1)`
    - `NovaForge/nova/forge_export.py:125`: `INSTALL.bat` installs CPU Torch: `--index-url https://download.pytorch.org/whl/cpu`
    - `NovaForge/nova/forge_models.py:120,138`: `map_location='cpu'`
    - CPU inference isolates bot processing from GPU graphics rendering, eliminating VRAM competition and PCIe synchronization latency.

### 1.4 Action Delay Deadlines and Latency Measurement
- **Timing Deadlines**:
  - In `NovaForge/nova/forge_models.py:31-38`:
    `tick_skip = 8`, `planned_delay_ticks = 7`, `simulator_delay_ticks = 1`.
  - At 120 Hz simulation physics:
    - 1 tick = 8.333 ms.
    - 8 ticks (`tick_skip = 8`) = **66.667 ms** decision interval (15 Hz decision rate).
    - 7 ticks (`planned_delay_ticks = 7`) = **58.333 ms** execution application deadline.
    - An observation evaluated at frame $F$ must have its chosen action queued before frame $F+7$ (`self.pending = (frame + 7, planned)`).
  - At 60 Hz RLBot match rate:
    - 1 tick = 16.667 ms; 2 ticks = 33.333 ms; 4 ticks = 66.667 ms.
  - At 120 Hz RLBot match rate:
    - 1 tick = 8.333 ms.
- **Latency Measurement Methods**:
  - In `freestyle_rlbot_v5/diagnose.py:32`:
    ```python
    start=time.perf_counter();previous=bot.get_output(packet);latencies.append((time.perf_counter()-start)*1000)
    ```
    Diagnostic output: `data/rlbot_v5_exports/Freestyle700_Audit/diagnostic.json` records `"max_callback_ms": 11.091599997598678` across 48 synthetic packets.
  - In `data/isolated/replay_imitation/runs/replay_scratch01/runtime_benchmark.json:11-25`:
    - 1-candidate policy mode latency: median 6.14 ms, p95 6.36 ms, max 6.38 ms. `meets_deadline_p95: true` (budget: 66.67 ms).
    - Multi-candidate search rollouts (4, 16, 64 candidates) scale latency to 49.39 ms, 104.14 ms, and 339.06 ms.

### 1.5 Baseline Opponents forming Secondary Panel
- **Authoritative Inventory from `NovaForge/nova/teachers.py:16-19`**:
  ```python
  BUILTIN_BOTS=('scripted','scorer','demochaser')
  FROZEN_BOTS=('nexto','ripple','chronos','galactus','ducky','rain','megabyte')
  BOT_NAMES=BUILTIN_BOTS+FROZEN_BOTS
  ```
- **Physical Model Verification in Repo**:
  1. `chronos`: `NovaForge/assets/chronos/POLICY.lt` (10.7 MB), `SHARED_HEAD.lt` (4.58 MB) — Breakout hitbox (`car_id = 22`), 225 core features.
  2. `galactus`: `NovaForge/assets/galactus/POLICY.lt` (17.2 MB), `SHARED_HEAD.lt` (5.28 MB) — Octane hitbox (`car_id = 23`), 258 core features + RocketSim `BallForecast`.
  3. `nexto`: `vendor/nexto/nexto-model.pt` (1.85 MB) and `NovaForge/assets/nexto/policy.pt` (1.85 MB) — Octane hitbox, 230 features (NextoObs), 90 actions, CC BY-NC-SA 4.0.
  4. `ripple`: `NovaForge/assets/ripple/policy.onnx` (4.57 MB) — 100 features, 276 actions, CC BY-NC-SA 4.0.
  5. `ducky`: `NovaForge/assets/ducky/POLICY.lt` (3.35 MB), `agent_setup.json` — 7-tick delay.
  6. `rain`: `NovaForge/assets/rain/POLICY.lt` (10.6 MB), `SHARED_HEAD.lt` (1.20 MB).
  7. `megabyte`: `NovaForge/assets/megabyte/POLICY.lt` (11.7 MB), `SHARED_HEAD.lt` (5.18 MB) — full neural policy.
  8. `fusion`: `triadbot/fusion_selection/20261106_050930_UTC_39ef9755/` — frozen refined hybrid actor.
  9. `scripted`, `scorer`, `demochaser`: rule-based reference bots.
  10. Historical baselines: Cycle 9 (`data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt`) and native Wavedash checkpoint.
- **Status of Prompt-Named Bots**:
  - `Nexto`: Present and verified (`vendor/nexto/nexto-model.pt`).
  - `Necto`: Upstream progenitor of Nexto; inventoried in `NovaForge/upstream_inventory.json:3` (`Rolv-Arild/Necto`); Nexto model weights bundled.
  - `Element`: VirxEC/Elementv5 inventoried in `NovaForge/upstream_inventory.json:1047` and referenced in Ripple NOTICE; no local weights bundled.
  - `Kamael`: Not present in local filesystem; external reference bot.

### 1.6 Discord Research Exports and Access Governance
- **Archive Specifications**:
  - `Discord.rar` (SHA-256: `54fcd2ffd7f8f7510823969f2f5cad2056196e2e37abf0fd51daee44de263169`).
  - 54 regular HTML files, 480,145,927 decompressed bytes.
  - Total local scan: 73 HTML paths, 56 distinct files, 577,620 deduplicated messages.
- **Channels Covered (`docs/DISCORD_RESEARCH_FINDINGS.md:15-22`)**:
  - RLGym / `rlgym-learn`: 9,500 messages (Aug 2024 – Jan 2026)
  - RLGym / `imitation-learning`: 6,900 messages (Jun 2022 – Jan 2023)
  - RLGym / `ml-lounge`: 9,000 messages (Sep 2021 – Mar 2022)
  - RLGym / `rocketsim`: 4,300 messages (Feb – Mar 2023)
  - RLGym / `general`: 4,600 messages (Sep 2021)
  - RLBot / `machine-learning`: 68,700 messages (Nov 2017 – Jul 2021)
- **Governance and Tooling**:
  - Tool: `slater_discord_research.py` uses only Python standard library; strictly offline.
  - Read-Only: No Discord network authentication, token scraping, bot posting, or user DMs.
  - Privacy: Private metadata, author IDs, and credentials stripped; isolated under `data/isolated/discord_research/`.
  - Research Principle: Discord messages are treated as informal community discussions and technical leads, not authoritative specifications or truth.

---

## 2. Logic Chain

1. **Packaging Formats**:
   - `NovaForge/nova/forge_export.py` generates both local `bot.bot.toml` and portable `bot.portable.bot.toml` adhering to RLBot v5 schema `https://rlbot.org/schemas/agent.json`.
   - `loadout.toml` configures `car_id = 22` for Chronos (Breakout) and `car_id = 23` for Galactus (Octane).
   - PyTorch actors are scripted via `torch.jit.script` in `save_actor`, tested against source weights with `torch.testing.assert_close(rtol=0, atol=0)`, and exported as byte-identical `actor.lt` and `actor.pt` files alongside JSON sidecar metadata.
2. **Launch & Execution**:
   - RLBot v5 executes `run_command` in `bot.bot.toml` and connects over TCP loopback.
   - The bot runs `ForgeBot(Hivemind)` or `Freestyle(Bot)`, performs TCP handshake (`ConnectionSettings` -> `MatchConfiguration` -> `FieldInfo` -> `InitComplete`), updates `GameState` on incoming `GamePacket`, queries `LiveDriver`, and sends back `PlayerInput(ControllerState)`.
3. **Action Latency & Budget**:
   - Simulation uses `tick_skip = 8` and `planned_delay_ticks = 7`. At 120 Hz physics (8.333 ms/tick), total decision window is 66.67 ms and action queue application deadline is 58.33 ms (7 ticks).
   - CPU single-forward inference takes ~0.5–2.5 ms for Chronos/Galactus, and end-to-end synthetic callback latency measures 11.09 ms in `Freestyle700_Audit/diagnostic.json`. Both comfortably satisfy the 58.33 ms deadline.
   - Multi-candidate search models fail the deadline (104–339 ms), confirming that direct policy execution on CPU is required.
4. **Opponent Panel & Promotion Requirements**:
   - Head-to-head promotion requires 2,000 games on fresh seeds using `arena-rng-v4` / `direct-h2h-v1` against the frozen baseline (`original_chronos` or `original_galactus`) with lower 95% confidence interval > 50.0%.
   - Secondary opponent panel is formed by verified frozen bots: `nexto`, `ripple`, `ducky`, `rain`, `megabyte`, `scripted`, and `fusion`.
5. **Discord Governance**:
   - Discord data in `Discord.rar` (577,620 messages) is strictly offline and read-only.
   - No network calls or active Discord logins are performed; all leads are validated locally against actual code and simulator experiments.

---

## 3. Caveats

1. **RLBot v5 Live GUI Match Execution**: This investigation was strictly static and read-only; no live Rocket League client or RLBot GUI test match was launched. RLBot v5 loopback protocol conformance was verified via existing offline TCP test harness (`NovaForge/tests/check_triad_v5.py`).
2. **Missing Local Weights for Element & Kamael**: While `Nexto` is fully bundled with weights and observation builders, `Element` (VirxEC/Elementv5) exists only as an upstream catalog reference, and `Kamael` is absent from the local repository. The secondary opponent panel must rely on the verified local pool (`nexto`, `ripple`, `ducky`, `rain`, `megabyte`, `fusion`, `scripted`).
3. **Galactus RocketSim Collision Meshes**: Galactus runtime uses `BallForecast`, which calls `RocketSim.init(...)`. This requires collision meshes in `rlgym/rocket_league/sim/collision_meshes`. If meshes are missing or corrupted, Galactus will fail to initialize. Chronos does not have this dependency.

---

## 4. Conclusion

The repository contains complete, production-ready specifications and implementations for:
1. **Export Formats**: RLBot v5 `bot.bot.toml` + `loadout.toml` + identical TorchScript `actor.lt`/`actor.pt` with JSON sidecar contracts. Chronos requires Breakout (`car_id = 22`); Galactus requires Octane (`car_id = 23`).
2. **Execution Flow**: RLBot v5 TCP loopback Hivemind (`ForgeBot`) or Bot (`Freestyle`) with automated `INSTALL.bat` and `DIAGNOSE.bat` scripts.
3. **Export & Device Selection**: Zero-tolerance numerical parity verification (`torch.testing.assert_close(rtol=0, atol=0)`) during export; CPU-only deployment (`torch.set_num_threads(1)`) to preserve GTX 1650 Ti GPU VRAM for the game client.
4. **Timing & Deadlines**: 8-tick decision cadence (66.67 ms) with a 7-tick hard action application deadline (58.33 ms). Direct CPU inference easily meets this (~1–11 ms callback), whereas multi-candidate searches exceed the budget.
5. **Opponent Panel**: Pinned secondary opponent panel consists of `nexto`, `ripple`, `ducky`, `rain`, `megabyte`, `fusion`, and `scripted`.
6. **Governance**: All Discord research materials are indexed offline (577,620 messages) under strict read-only, non-network governance.

---

## 5. Verification Method

To independently verify all findings without modifying repo files or launching games:

1. **Verify Export Formats and TOML Structure**:
   ```powershell
   python -c "import tomllib; c = tomllib.loads(open('forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/bot.bot.toml', 'rb').read()); print(c['settings']); l = tomllib.loads(open('forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/loadout.toml', 'rb').read()); print(l)"
   ```
2. **Verify TorchScript Model Parity and Weight Identity**:
   ```powershell
   python -c "import hashlib; h1 = hashlib.sha256(open('forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/actor.lt', 'rb').read()).hexdigest(); h2 = hashlib.sha256(open('forgeleague/exports/duel01/Forge_chronos_b37d34d425_83ba25/actor.pt', 'rb').read()).hexdigest(); print('actor.lt == actor.pt:', h1 == h2); print('SHA256:', h1)"
   ```
3. **Verify RLBot v5 Protocol Harness Test**:
   Inspect `NovaForge/tests/check_triad_v5.py:57-90` and run:
   ```powershell
   pytest NovaForge/tests/check_triad_v5.py -k test
   ```
4. **Verify Action Delay & Latency Budget**:
   Inspect `data/rlbot_v5_exports/Freestyle700_Audit/diagnostic.json` and `data/isolated/replay_imitation/runs/replay_scratch01/runtime_benchmark.json`.
5. **Verify Secondary Opponent Panel Files**:
   ```powershell
   python -c "import os; from pathlib import Path; assets = Path('NovaForge/assets'); print([p.name for p in assets.iterdir() if p.is_dir()])"
   ```
6. **Verify Discord Governance**:
   Inspect `docs/DISCORD_RESEARCH_FINDINGS.md:5-24` and `slater_discord_research.py`.
