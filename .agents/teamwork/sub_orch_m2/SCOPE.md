# Scope: Milestone 2 — Bounded Pilot & Resource Boundary Controls

## Overview
Milestone 2 establishes hardware safety limits, process isolation, and automated candidate checkpoint retention, and verifies safe pause/resume behavior via a short bounded training pilot before launching longer multi-iteration experiments.

## Assigned Features
- **Feature 4**: Resource Boundaries & Safe Telemetry Monitoring — Declare and enforce wall-time, RAM ($\le 4.0\text{ GB}$), VRAM ($\le 1.8\text{ GB}$), and thermal ($< 85^\circ\text{C}$) bounds on the Intel i5-10300H / GTX 1650 laptop. Respect concurrent gaming: NEVER terminate `RocketLeague.exe`, `EpicGamesLauncher.exe`, or any user processes.
- **Feature 5**: Candidate Checkpoint Retention System — Implement automated checkpoint retention for top screening and confirmation candidates in `watch_pins/` or `shortlist/` to prevent rotation deletion (resolving the Trial 62 missing lookup bug).
- **Feature 6**: Bounded Pilot Training & Resumption Verification — Execute a bounded training pilot (1–2 PPO iterations, e.g. 16,384 timesteps) on Chronos 1v1 Breakout. Verify asynchronous `STOP` file signal handling, clean exit code 0, checkpoint save on pause, and weight-identical resumption.

## Acceptance Criteria
1. Hardware resource boundaries are explicitly declared and verified: Max VRAM $\le 1.8\text{ GB}$, Max System RAM $\le 4.0\text{ GB}$, thermal throttling guard $< 85^\circ\text{C}$, single GPU process policy.
2. Checkpoint retention mechanism is verified: candidates meeting confirmation criteria are automatically pinned or retained so `lookup: missing` never occurs.
3. Bounded pilot training run (1-2 iterations, 16,384 steps) executes cleanly and pauses on `STOP` file touch with exit code 0.
4. Resuming from the paused checkpoint restores exact model weights and optimizer state.
5. All Milestone 1 invariants and test suites (41/41 unit tests, 213/213 E2E tests) remain 100% passing.
