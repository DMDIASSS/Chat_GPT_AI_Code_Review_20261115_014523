# Worker Dispatch: Milestone 2 Implementation & Verification

**Agent**: `worker_m2_1` (`teamwork_worker`)  
**Working Directory**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m2_1\`  
**Assigned Scope**: Milestone 2 (Bounded Pilot & Resource Boundary Controls: Features 4, 5, 6)

## Mandatory Documents to Read First
1. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md` (authoritative request)
2. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md` (global project specification & architecture)
3. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m2\SCOPE.md` (Milestone 2 scope)
4. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m2_1\handoff.md` (Hardware telemetry & process boundaries)
5. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m2_2\handoff.md` (Checkpoint retention & pinning design)
6. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m2_3\handoff.md` (Bounded pilot & pause/resume protocol)

## Tasks
1. **Pre-flight Telemetry Gate**:
   - Check GPU temp and resource usage without touching user processes. CRITICAL: NEVER terminate or close `RocketLeague.exe`, `EpicGamesLauncher.exe`, or any user application. Respect concurrent gaming.
   - Enforce resource bounds: `GIGAFORGE_SIM_THREADS=4`, RAM <= 4.0 GB, VRAM <= 1.8 GB.
2. **Feature 5: Candidate Checkpoint Retention**:
   - Implement `pin_candidate()` in `gigaforge/research.py` exactly per `teamwork_explorer_m2_2/handoff.md`.
   - Hook `pin_candidate()` into screening pass (`preserve_promising`) and confirmation pass (`preserve_tested`).
   - Add unit test `test_candidate_pinned_permanently_in_watch_pins_on_confirmation` in `gigaforge/tests/test_trial_watch.py` verifying pinned candidate survival even after branch checkpoint directory deletion.
3. **Feature 6: Bounded Pilot Training & Pause/Resume Verification**:
   - Create and run `gigaforge/verify_pilot_f6.py` using `runs/pilot_chronos/` (isolated from `research02` and `native01`).
   - Verify pilot launch (Breakout Chronos, 32 games, 4 sim threads).
   - Verify asynchronous `STOP` file touch during iteration 1 causes clean exit code 0 at iteration boundary (8,192 steps).
   - Verify checkpoint integrity (`COMPLETE`, `RUNNING_STATS.json`, 6 weight/optimizer archives).
   - Verify clean resumption from 8,192 to 16,384 steps with weight and optimizer moment parity.
   - Clean up temporary `runs/pilot_chronos/`.
4. **Verification**:
   - Run `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\pytest.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests -v`
   - Run `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\pytest.exe tests/e2e -v`
   - Report all outcomes in `handoff.md`.


## 2026-11-07T22:50:35Z
Directive from Parent Orchestrator:
- STRICT NON-INTERFERENCE MANDATE: NEVER terminate, close, or interfere with `RocketLeague.exe`, `EpicGamesLauncher.exe`, or ANY user application or process under any circumstances.
- All training, pilots, and evaluations must strictly coexist with concurrent gaming and background applications.
- Enforce bounded resources: `GIGAFORGE_SIM_THREADS=4`, RAM <= 4.0 GB, VRAM <= 1.8 GB.
- Resume Milestone 2 tasks: Candidate Checkpoint Retention (Feature 5), Bounded Pilot & Pause/Resume (Feature 6), full test suites (`pytest gigaforge/tests -v`, `pytest tests/e2e -v`), and deliver handoff report.
