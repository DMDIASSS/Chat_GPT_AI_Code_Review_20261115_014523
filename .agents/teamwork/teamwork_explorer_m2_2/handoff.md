# Handoff Report: Candidate Checkpoint Retention and Lifecycle Management Investigation

**Author**: `teamwork_explorer_m2_2`  
**Milestone**: M2 (Feature 5: Candidate Checkpoint Retention System)  
**Target Recipient**: Orchestrator (`cee93413-6e94-42af-a811-08721badd7f7`) / M2 Worker  

---

## 1. Observation

### Observation 1.1: Head-to-Head Candidate Fallback in `latest_h2h.json`
In `gigaforge/runs/research02/latest_h2h.json` (lines 11–26 and 34):
```json
    "actor": "E:\\Downloads\\Chat_GPT_AI\\gigaforge\\runs\\research02\\watch_pins\\chronos\\trial_00038_a6fd6283dd21\\actor.lt",
    "attempts": [
      {
        "trial": 62,
        "family": "chronos",
        "confirmation_delta": 0.046875,
        "lookup": "missing"
      },
      {
        "trial": 38,
        "family": "chronos",
        "confirmation_delta": 0.029296875,
        "lookup": "native"
      }
    ]
```
- Head-to-head selection ranked Trial 62 first because its confirmation delta (+4.6875%) was higher than Trial 38 (+2.9297%).
- Trial 62 failed lookup with status `"missing"`.
- The evaluation harness fell back to Trial 38, which was located as `"native"` in `watch_pins/chronos/trial_00038_a6fd6283dd21/actor.lt`.

### Observation 1.2: Trial 62 Watch Request Record and Exact Files
In `gigaforge/runs/research02/watch_requests/trial_00062_chronos.json` (lines 1–40):
- Trial 62 record:
  - Family: `chronos`
  - Arm: `evolved_40`
  - Candidate path recorded: `branches\chronos\evolved_40\cb4e93c281cc_0\checkpoints\1048576`
  - Confirmation delta: `+0.046875` (+4.6875 percentage points)
  - Lower bound: `-0.040227`, Upper bound: `+0.133977`, Blocks: 256
  - Expected file hashes:
    - `SHARED_HEAD.lt`: `713b9b0549e86960ff2fe2050d97292bcf550cf3afd6a244ae13f51a56cb679a`
    - `POLICY.lt`: `525e7be99e606885c9da4b5420c20f52961c224e8cbbf33b651d9c4890b25a44`
  - Lookup result:
    `kind: "missing"`, `checked: 62`, `reason: "No matching actor files found in saved checkpoints, policy versions, shortlist, pinned actors or this run's exports. No substitute selected."`

### Observation 1.3: Trial 62 Development Screening and Shortlist Rejection
In `gigaforge/runs/research02/evaluations/lab_00062_chronos_development.json`:
- Lines 2605–2618: Development screen scored `delta = 0.046875`, `lower = -0.05715757`, `upper = 0.15090757`, `blocks = 64`, `decision = "promising"`.
In `gigaforge/research.py`:
- Lines 183–205 (`preserve_promising`):
  ```python
  def preserve_promising(m,run,state,family,candidate,result):
   """Keep two best positive-screen actors per family outside native rotation."""
   if result['statistics'].get('delta',0)<=0:return
   entries=state.setdefault('shortlist',{}).setdefault(family,[])
   rank=lambda item:(item['statistics'].get('lower') if item['statistics'].get('lower') is not None else -10,item['statistics']['delta'])
   ...
   if len(entries)>=2 and rank(item)<=min(map(rank,entries)):return
  ```
In `gigaforge/runs/research02/shortlist/chronos.json` (lines 1–40):
- Contained only two candidates:
  1. Trial 42: `delta = 0.078125`, `lower = -0.014695`, `blocks = 64`
  2. Trial 38: `delta = 0.046875`, `lower = -0.035572`, `blocks = 64`
- Trial 62's rank tuple `(-0.057158, 0.046875)` was strictly worse on `lower` than Trial 38 `(-0.035572, 0.046875)`.
- Consequently, line 193 returned immediately, and Trial 62 was NOT admitted to `shortlist`.

### Observation 1.4: Native C++ Engine Checkpoint Saving and Rotation
In `gigaforge/src/main.cpp` (lines 140–142):
```cpp
cfg.checkpointFolder=recipe.at("checkpoints").get<std::string>();cfg.tsPerSave=32768;
cfg.checkpointsToKeep=3;cfg.savePolicyVersions=!cfg.checkpointFolder.empty();cfg.tsPerVersion=32768;cfg.maxOldVersions=4;
cfg.trainAgainstOldVersions=!cfg.checkpointFolder.empty();cfg.trainAgainstOldChance=.25;
```
- Every 32,768 timesteps (`tsPerSave = 32768`), GigaForge writes a checkpoint directory.
- `cfg.checkpointsToKeep = 3`: The native C++ learner keeps only the 3 most recent checkpoints. Any checkpoint older than 3 saves (98,304 timesteps) is deleted from disk.
- `cfg.maxOldVersions = 4`: The native C++ learner keeps at most 4 policy versions in `checkpoints/policy_versions/`. Any version older than 4 saves (131,072 timesteps) is deleted.

### Observation 1.5: Subsequent Training Erased Checkpoint 1048576
In `gigaforge/runs/research02/lab_state.json`:
- Lines 1492–1510: At Trial 66, arm `chronos/evolved_40` was selected again.
- Training resumed on `branches\chronos\evolved_40\cb4e93c281cc_0\checkpoints` from 1,048,576 timesteps and ran up to 1,310,720 timesteps (+262,144 timesteps).
- Direct inspection of `branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/`:
  - Existing checkpoint folders: `1245184`, `1277952`, `1310720` (exactly 3 checkpoints).
  - Existing policy versions in `policy_versions/`: `1212416`, `1245184`, `1277952`, `1310720` (exactly 4 versions).
  - Checkpoint `1048576` was completely deleted by native C++ rotation during Trial 66.

### Observation 1.6: Historical Note in `TRIAL_WATCH.md`
In `gigaforge/TRIAL_WATCH.md` (lines 29–35):
> "Future positive confirmation-test candidates now have a separate bounded archive of two actors per family, ranked by match-score point estimate. These remain UNVERIFIED; promotion and exports still require the existing full guards. This fixes a retention gap: the earlier shortlist ranked development screens and did not guarantee preserving the best confirmation-test result. It cannot recover an already deleted model."
- This confirms that at the time Trial 62 ran, `preserve_tested()` did not exist. Trial 62 was never copied out of the branch checkpoint folder, and was subsequently purged by native rotation.

---

## 2. Logic Chain

1. **Evaluation Flow During Trial 62**:
   - Trial 62 trained on branch `branches/chronos/evolved_40/cb4e93c281cc_0` up to timestep 1,048,576 (Observation 1.2).
   - In development screening, Trial 62 scored `delta = +0.046875`, `lower = -0.057158` (Observation 1.3).
   - `preserve_promising` was called. Because `shortlist` already contained Trial 42 and Trial 38 with higher lower bounds (`-0.014695` and `-0.035572`), Trial 62 was not added to `shortlist` (Observation 1.3).
   - Development screening returned `decision = "promising"`, triggering confirmation evaluation on 128 seed pairs (256 blocks) (Observation 1.2).
   - Confirmation evaluation scored `delta = +0.046875`, `lower = -0.040227` (Observation 1.2). Because `lower <= 0`, `decision` was `"uncertain"` (not `"improved"`).
   - Because `decision != "improved"`, `protect()` was not called (which only saves champions).
   - Because `preserve_tested()` did not exist when Trial 62 executed, Trial 62 was not saved to `tested_candidates/` or `watch_pins/` (Observation 1.6).
   - Trial 62 existed solely as raw files in `branches/chronos/evolved_40/cb4e93c281cc_0/checkpoints/1048576`.

2. **Checkpoint Pruning Mechanism**:
   - In Trial 66, the same arm (`chronos/evolved_40`) resumed training from 1,048,576 timesteps (Observation 1.5).
   - Native C++ engine `GigaForge.exe` saves every 32,768 steps and retains only `checkpointsToKeep = 3` and `maxOldVersions = 4` (Observation 1.4).
   - After 98,304 additional timesteps (at 1,146,880 timesteps), checkpoint `1048576` was deleted from `checkpoints/`.
   - After 131,072 additional timesteps, version `1048576` was deleted from `policy_versions/`.
   - At the end of Trial 66 (1,310,720 timesteps), all weights for Trial 62 were permanently destroyed on disk (Observation 1.5).

3. **Head-to-Head Lookup Failure**:
   - `head_to_head.py:select()` scans confirmation results in `lab_state.json` and sorts by `delta` descending (Observation 1.1).
   - Trial 62 was ranked #1 (`delta = +0.046875`).
   - `trial_watch.find_exact()` searched `preferred` (`checkpoints/1048576`), `branches`, `shortlist`, `tested_candidates`, `watch_pins`, `champions`, `parents`, and `exports`.
   - None of the 62 searched directories contained `POLICY.lt` hash `525e7be9...` (Observation 1.2).
   - `find_exact` returned `kind: "missing"`.
   - `head_to_head.py` logged `lookup: "missing"` in `latest_h2h.json` and fell back to Trial 38 (`delta = +0.029297`), which was safely preserved in `shortlist/` (Observation 1.1).

4. **Identified Architectural Retention Gaps**:
   - **Gap 1**: Shortlist only stores 2 items per family and sorts by `(lower, delta)`. Wide confidence intervals on development screening cause high-delta candidates (like Trial 62) to be dropped.
   - **Gap 2**: `preserve_tested` only keeps 2 items per family in `tested_candidates/`. When a 3rd positive candidate arrives, `del entries[2:]` and `shutil.rmtree` delete earlier ones.
   - **Gap 3**: Neither `preserve_promising` nor `preserve_tested` generates an `actor.lt` TorchScript package or stores into `watch_pins/`.
   - **Gap 4**: Native C++ checkpoint rotation (`checkpointsToKeep = 3`) and version rotation (`maxOldVersions = 4`) operate completely asynchronously from Python evaluation, erasing checkpoints within 98k/131k timesteps whenever an arm is continued.

---

## 3. Caveats

1. **Trial 62 Weights Irrecoverability**:
   As acknowledged in `TRIAL_WATCH.md`, neural network weights cannot be synthesized from evaluation statistics or metadata. Without an external backup or export artifact containing `POLICY.lt` hash `525e7be99e606885c9da4b5420c20f52961c224e8cbbf33b651d9c4890b25a44` and `SHARED_HEAD.lt` hash `713b9b0549e86960ff2fe2050d97292bcf550cf3afd6a244ae13f51a56cb679a`, Trial 62's exact actor cannot be reconstructed. Trial 38 is currently the highest-performing verified available candidate (`delta = +0.029297`).
2. **Read-Only Scope**:
   This explorer investigation strictly avoided modifying or deleting any checkpoints, configs, or source files in accordance with the read-only directive.
3. **Hardware Storage Budget**:
   Retaining full checkpoints (`~40 MB` each) and compiled actors (`~15 MB` each) requires `~55 MB` per pinned candidate. On drive `E:` with 210.9 GB free space, permanently retaining 50 pinned candidates requires `~2.75 GB` (< 1.5% of free space), which is well within capacity.

---

## 4. Conclusion & Retention System Design

### 4.1 Root Cause Summary
Chronos Trial 62 was reported as `lookup: "missing"` because:
1. It was rejected from `shortlist` due to a strict 2-item cap ranked on development `lower` bound.
2. It was not promoted to champion (where `protect()` would have saved it) because its confirmation 95% lower bound was `-0.0402` (`<= 0`).
3. No automatic confirmation pinning existed at that time.
4. When arm `chronos/evolved_40` trained again in Trial 66, native C++ `GigaForge.exe` checkpoint rotation (`checkpointsToKeep = 3`, `maxOldVersions = 4`) deleted checkpoint `1048576` and version `1048576`.

### 4.2 Automated Retention Rule Design
Whenever a candidate completes evaluation during research training:
1. **Trigger Conditions**:
   - **Screening Rule**: If development evaluation yields `result['decision'] in ('promising', 'improved')` OR `result['statistics'].get('delta', 0) >= cfg.get('minimum_delta', 0.03)`.
   - **Confirmation Rule**: If confirmation evaluation yields `result['statistics'].get('delta', 0) > 0` OR `result['decision'] == 'improved'`.
2. **Immediate Execution Timing**:
   - Pinning MUST occur immediately upon return from `evaluate()`, while `current` is guaranteed to exist on disk, BEFORE any further training iterations or branch pruning can run.
3. **Permanent Retention Destination**:
   - Stored in `run / 'watch_pins' / family / f'trial_{trial:05d}_{tag[:12]}'` (where `tag = digest(files)`).
   - This directory is permanent: it is NEVER subject to `shutil.rmtree` by `prune_branches`, `preserve_promising`, or `preserve_tested`.
   - It is natively recognized and searched by `trial_watch.find_exact()` (in `roots` and `exports`), `head_to_head.py:select()`, and `18_WATCH_CHRONOS_TRIAL_62.bat`.
4. **Artifacts Preserved in Pin Directory**:
   - `SHARED_HEAD.lt` and `POLICY.lt` (exact weights for native evaluation).
   - `native.json` (sealed generation metadata).
   - Complete training checkpoint files if present: `POLICY_OPTIM.lt`, `SHARED_HEAD_OPTIM.lt`, `CRITIC.lt`, `CRITIC_OPTIM.lt`, `RUNNING_STATS.json`, `COMPLETE` (enables exact weight & optimizer resumption).
   - Compiled TorchScript actor: `actor.lt` packaged via `DirectActor` + `save_actor()`.
   - Sidecar metadata: `actor.lt.json` with contract, role, research trial, and evaluation evidence.
   - Manifest: `pin_manifest.json` recording timestamp, trial, family, split, delta, and 95% CI.

---

## 5. Worker Implementation Plan

### Step 1: Implement `pin_candidate()` in `gigaforge/research.py`
Add the following function in `gigaforge/research.py`:
```python
def pin_candidate(m, run, state, family, candidate, result, split):
    """Permanently pin positive screening or confirmation candidate before rotation pruning."""
    from trial_watch import identity, FILES
    from research_eval import digest
    import torch
    from nova.giga_teachers import GigaNetwork
    from nova.forge_models import DirectActor, save_actor, check_actor

    trial = state['trial']
    source = Path(candidate)
    if not all((source / n).is_file() for n in FILES):
        return None

    files = identity(m, source)
    tag = digest(files)
    pin_dir = run / 'watch_pins' / family / f'trial_{trial:05d}_{tag[:12]}'
    pin_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy native model weights
    for name in FILES:
        if not (pin_dir / name).exists():
            shutil.copy2(source / name, pin_dir / name)

    # 2. Copy complete checkpoint state if present (optimizers, critic, running stats)
    checkpoint_files = ('POLICY_OPTIM.lt', 'SHARED_HEAD_OPTIM.lt', 'CRITIC.lt',
                        'CRITIC_OPTIM.lt', 'RUNNING_STATS.json', 'COMPLETE')
    for name in checkpoint_files:
        src_file = source / name
        dst_file = pin_dir / name
        if src_file.is_file() and not dst_file.exists():
            shutil.copy2(src_file, dst_file)

    # 3. Seal and verify generation
    m.seal_generation(pin_dir, family)
    m.verify_generation(pin_dir)

    # 4. Materialize standalone TorchScript actor.lt with sidecar metadata
    actor = pin_dir / 'actor.lt'
    if not actor.exists():
        network = DirectActor(family)
        network.core.load_state_dict(GigaNetwork(pin_dir, family).state_dict(), strict=True)
        role = f'trial {trial} {split} candidate ({result["decision"]})'
        hitbox = 'breakout' if family == 'chronos' else 'octane'
        save_actor(
            network, actor, family, hitbox=hitbox,
            source_native=m.read(pin_dir / 'native.json'),
            role=role, research_trial=trial,
            trial_evidence=dict(
                trial=trial, family=family, split=split,
                decision=result['decision'], statistics=result['statistics'],
                files=files
            )
        )
        check_actor(actor, family)

    # 5. Write manifest for fast querying
    manifest = dict(
        trial=trial, family=family, split=split,
        decision=result['decision'], statistics=result['statistics'],
        files=files, pinned_at=time.time(), candidate=str(candidate)
    )
    m.write(pin_dir / 'pin_manifest.json', manifest)

    # 6. Update lab_state pinned index
    pins = state.setdefault('pinned_candidates', {}).setdefault(family, [])
    if not any(p.get('tag') == tag for p in pins):
        pins.append(dict(trial=trial, tag=tag, path=str(pin_dir.relative_to(run)),
                         delta=result['statistics'].get('delta'), split=split))

    print(f'RESEARCH_CANDIDATE_PINNED: {family} trial {trial} ({split} delta {result["statistics"].get("delta"):+.4f}) -> {pin_dir}', flush=True)
    return pin_dir
```

### Step 2: Hook `pin_candidate()` into Training Loop in `gigaforge/research.py`
In `gigaforge/research.py` inside `train()` (around line 350 and 360):
1. **Screening Hook**:
   ```python
   result = evaluate(m, run, state, family, current, 'development', cfg, tracker)
   if cfg['version'] == 'reward-lab-v2':
       preserve_promising(m, run, state, family, current, result)
       # Automated Permanent Pinning on Screening Pass
       if result['decision'] in ('promising', 'improved') or result['statistics'].get('delta', 0) >= cfg.get('minimum_delta', 0.03):
           pin_candidate(m, run, state, family, current, result, 'development')
       persist(m, run, state)
   ```
2. **Confirmation Hook**:
   ```python
   result = evaluate(m, run, state, family, current, 'confirmation', cfg, tracker)
   if result['decision'] == 'improved' and screen not in ('promising', 'improved'):
       result['decision'] = 'uncertain'
   if cfg['version'] == 'reward-lab-v2':
       preserve_tested(m, run, state, family, current, result)
       # Automated Permanent Pinning on Confirmation Pass
       if result['statistics'].get('delta', 0) > 0 or result['decision'] == 'improved':
           pin_candidate(m, run, state, family, current, result, 'confirmation')
       persist(m, run, state)
   ```

### Step 3: Add Unit Test in `gigaforge/tests/test_trial_watch.py`
Add `test_candidate_pinned_permanently_in_watch_pins_on_confirmation()`:
- Create a test fixture with synthetic candidate checkpoint.
- Call `pin_candidate` with confirmation delta `+0.046875`.
- Verify `watch_pins/<family>/trial_00062_<tag>/` contains `POLICY.lt`, `SHARED_HEAD.lt`, and `actor.lt`.
- Verify `trial_watch.find_exact()` finds the candidate as `kind == 'native'`.
- Delete original branch checkpoint directory (`shutil.rmtree(source)`).
- Verify `trial_watch.find_exact()` STILL finds the pinned candidate in `watch_pins/` without lookup failure.
- Verify `head_to_head.py:select()` succeeds without `lookup: "missing"`.

---

## 6. Verification Method

### 6.1 Test Execution Command
Run the GigaForge test suite using the pinned native virtual environment:
```powershell
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\pytest.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests
```
Expectation: All existing 41 tests pass, plus the new retention test (42 passed, 0 failed).

### 6.2 End-to-End Retention Simulation Check
Run the native trial watch validation script:
```powershell
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests\check_trial_watch_native.py
```
Expectation: Outputs `EXACT_TRIAL_NATIVE_ACTOR_PARITY_PIN_AND_EXPORT_RECOVERY_PASS`.

### 6.3 Head-to-Head Selection Check
Run the native head-to-head check script:
```powershell
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests\check_head_to_head.py
```
Expectation: Outputs `NATIVE_H2H_COUNTS_SELECTION_RESUME_PAUSED_STATE_AND_EXPORT_PARITY_PASS`.

### 6.4 Invalidation Conditions
This retention fix would be invalidated if:
1. `watch_pins/` is placed under `branches/` where `prune_branches` could delete it.
2. `pin_candidate()` is delayed until after training resumes, allowing native C++ rotation (`tsPerSave = 32768`, `checkpointsToKeep = 3`) to delete the checkpoint first.
3. Existing test `test_future_confirmation_actors_survive_rotation_and_are_bounded` breaks due to tampering with `tested_candidates` bounded structure.
