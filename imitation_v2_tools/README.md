# Fresh replay imitation v2 — reproducible local starter

This is an **additive** folder; it does **not** overwrite `train.py` or update_000271. It has a genuine PyTorch offline imitation trainer (3,356,931 trainable weights) with an 8-frame history, 8-action chunk predictor, a **short-horizon goal-side classification head**, replay reconstruction import, local metrics and optional W&B. There is **no reinforcement learning, self-play, Nexto teacher, or 271 initialization**.

**Important:** This is not yet the complete TAS+token+64-way planner bot. Its chunk head predicts raw controls, not action tokens; the 3-class head predicts whether a goal for/against occurs in 10 seconds, **not** a learned simulator action value. A 64-candidate RocketSim planner and RLBot policy runner still have to be built and timed. No uploaded replays have been run through replicar here because the RocketSim `.cmf` meshes and compiled CLI are not available in this environment. The included smoke training used **synthetic fixtures** only.

## User uploads reviewed, 16 Oct 2026

- `ranked-duels.rar`: 228 `.replay` files, 212 unique exact file hashes, 16 exact duplicates. Seven files under 100 KiB (not automatically invalid). This is the user's claimed 1v1 GC3–SSL collection; rank was **not** independently verified from the file or API metadata.
- `tas.rar`: 67 `.data` files, 108,461 combined frame/control-like records, one zero-record file, all with the observed `version=1`, `8-byte header + 32*n + 128` binary layout. Unknown input bit masks, analog field names, tick rate, meaning of 128-byte tail, initial-state semantics, game/map requirements. `tas/report.json` logs an invalid wildcard on its originating Windows run. **Never train on these until the creator/plugin and input format are identified.**
- `Discord.rar`: inspected archived RLGym `#imitation-learning` (6900 messages), `#ml-lounge` (9000), `#rocketsim` (4300), `#rlgym-learn` (9500), `#rlgym-tools` (3200) and RLBot `#machine-learning` (68,700). Summarized important technique and data concerns in `RESEARCH.md`. The archives are not copied into this pack.

## Windows setup

Extract this folder **into your repository root**, e.g. `E:\Downloads\Chat_GPT_AI\imitation_v2_tools`. Run all these PowerShell examples from the **repository root** after installing Python and making a venv:

```powershell
cd E:\Downloads\Chat_GPT_AI
python -m pip install numpy torch pyarrow wandb
python imitation_v2_tools\audit_sources.py
python -m unittest discover -s imitation_v2_tools\tests -v
```

### Ballchasing 2v2 download

Get an API token privately from [Ballchasing](https://ballchasing.com/doc/api). Do not post it or add it to Git. The API exposes `grand-champion` as its highest documented rank filter, which does **not** isolate GC3–SSL. Keep its rank metadata `unverified` until actual ranks are checked. The downloader verifies 2 blue + 2 orange players, duration, replay ID, content type, HTTPS pagination and local SHA; retries/backoff and manifest enable resuming.

```powershell
$env:BALLCHASING_TOKEN = Read-Host 'Ballchasing API token'
python imitation_v2_tools\fetch_ranked_doubles.py --dry-run --limit 25
python imitation_v2_tools\fetch_ranked_doubles.py --limit 200
Remove-Item Env:\BALLCHASING_TOKEN
```

Free/non-patron accounts are limited to ~200 replay **downloads per hour** and 1/sec by the documented API (check current limits). Stop and resume later if you encounter a quota error; do not evade API limits. The browser URL `playlist=11&min-rank=21&max-rank=22` uses a different numeric UI filter from the API's documented named filters. We **do not** claim these downloads are all GC3–SSL.

### RocketSim reconstruction via replicar v2

[Rolv-Arild/replicar](https://github.com/Rolv-Arild/replicar) is the recommended replay reconstructor. It supports Windows, requires **Rust 1.97+** and RocketSim soccar collision meshes `.cmf` that you legally obtain locally; it is built with `cargo build --release -p replicar-cli`. Follow its latest README. From its checkout:

```powershell
cargo build --release -p replicar-cli
```

Then, from your bot repo root, replace `C:\path\to\replicar.exe` and `E:\path\to\collision_meshes`:

```powershell
python imitation_v2_tools\replicar_convert.py --replicar "C:\path\to\replicar.exe" --meshes "E:\path\to\collision_meshes" --input data\replays\ranked-duels --output data\replicar\duels --tick-step 8 --jobs 4
python imitation_v2_tools\replicar_convert.py --replicar "C:\path\to\replicar.exe" --meshes "E:\path\to\collision_meshes" --input data\replays\ranked-doubles --output data\replicar\doubles --tick-step 8 --jobs 4
```

Run `replicar inspect` and inspect `index.parquet` for **failed or unsupported replays**; do not assume the files all parse. Do not use its `--rows frames` mode for the 15 Hz sequence config here: use `--tick-step 8`. Reconstruction's air controls and intermediate states are **estimates** fitted using later packets, not recorded human inputs. Validate quality on held-out source matches and propagate any uncertainty before training.

### Build supervised dataset and train

```powershell
python imitation_v2_tools\build_replicar_dataset.py --input data\replicar --output data\imitation_npz --tick-step 8
# Online mode: log in locally first, never paste token into code or chat.
wandb login
python imitation_v2_tools\train_imitation.py --data data\imitation_npz --output runs\fresh-imitation-v1 --epochs 40 --batch-size 256 --wandb-mode online --wandb-project rl-imitation-fresh
```

For offline W&B logging add `--wandb-mode offline` and later run `wandb sync runs\fresh-imitation-v1\wandb\<run-folder>` or let W&B show the precise directory. For no W&B installation use `--wandb-mode disabled`. W&B plus local JSONL logs `train/loss`, `val/analog_mae`, `val/button_accuracy`, `val/value_ce`, and per-mode validation metrics (`val_duels/`, `val_doubles/`) if source manifests exist.

Resume without resetting weights:

```powershell
python imitation_v2_tools\train_imitation.py --data data\imitation_npz --output runs\fresh-imitation-v1 --epochs 60 --batch-size 256 --wandb-mode online --resume
```

**Data controls:** replay-SHA split into train/val/test before window extraction; exact duplicate files deduped; fixed-size history and action chunks cannot cross goal or pause boundaries; required control/physics columns cannot be missing; future outcome fields go to the value **targets only**. If the same underlying match was re-exported to two different files, SHA dedup alone cannot detect that: identify match IDs or provide ballchasing manifests to strengthen match-level grouping. Full matches, not frames, must remain in a single split. Do not tune on `test`.

**Architecture & remaining blockers:** This 3.36M-parameter GRU BC baseline is usable for supervised **experiment setup**, not a finished competitive RLBot. It currently lacks discrete action-token VQ, the 64 candidate RocketSim forward planner, a tested policy-only and planned-policy RLBot executable, verified real match score data, actual replay reconstruction diagnostics, and any TAS labels. These additions depend on the original TAS exporter/schema and working RocketSim/replicar meshes and evaluator. We should not declare gameplay improvement from decreasing loss alone.

### Real independent evaluation gate

The conservative `quality_gate.py` expects an **externally measured** JSON document with `heldout_replays`, `replay_reconstruction_position_p90_uu`, `rollout_matches`, `model_only_winrate`, `baseline_winrate`, `model_only_own_goals`, `baseline_own_goals`, `planner_p95_ms`. It rejects missing results and cannot calculate match metrics for you. The position-error and runtime limits are **provisional** thresholds; calibration to your deployment matters. Example:

```powershell
python imitation_v2_tools\quality_gate.py runs\actual-independent-evaluation.json
```

Do **not** fill this JSON with fabricated placeholder scores. The evaluator must compare policy-only gameplay to a fixed baseline, plus planned gameplay separately. Do not let kickoff scripts mask poor policy performance.

## Software sources

- https://github.com/Rolv-Arild/replicar
- https://github.com/Rolv-Arild/replay-pretraining
- https://github.com/Rolv-Arild/python-ballchasing
- https://github.com/ZealanL/RocketSim
- https://github.com/VirxEC/rocketsim-rs
- https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/learner_settings.md (PPO only, **not BC** hyperparameters)
- https://github.com/PiggyVevo/GigalearnGuide (GigaLearnCPP/PPO installation and monitoring, **not** a BC trainer)
