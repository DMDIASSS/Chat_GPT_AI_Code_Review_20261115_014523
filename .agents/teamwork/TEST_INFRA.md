# TEST_INFRA — E2E Testing Track Infrastructure & Architecture

**Project**: Rocket League Bot Research (GigaForge Chronos 1v1 Breakout)  
**Track**: E2E Testing Track  
**Runner**: `pytest` 8.4.2 via `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe`  
**Execution Environment**: Python 3.11.9 (64-bit), PyTorch 2.9.1+cu126, CUDA 12.6, Windows x64  
**Native Simulator**: `gigaforge/native/GigaForge.exe` (C++20, RocketSim 2.2.1, LibTorch 2.9.1)  
**Status**: ACTIVE  

---

## 1. Executive Summary & Verification Strategy

The End-to-End (E2E) Testing Track designs, implements, and maintains an authoritative, opaque-box, requirement-driven test suite for the Rocket League bot research platform. The test suite operates independently from internal implementation details, validating behavior, contracts, numerical invariants, timing deadlines, statistical rigor, and governance constraints across all 20 features cataloged in `PROJECT.md`.

### Core Verification Principles
1. **Opaque-Box & Requirement-Driven**: Tests assert observable external behavior, contract conformance, mathematically proven formulas, cryptographic hashes, and exit codes.
2. **Progressive Testability & Failure Signaling**: Tests provide unambiguous progressive pass/fail signals across milestones M1–M6. When a feature is incomplete, broken, or regressed, tests fail with detailed diagnostic reporting; when requirements are met, tests pass deterministically.
3. **Hardware-Aware & Isolated**: Respects laptop hardware limits (Intel i5-10300H, GTX 1650 4GB VRAM, 16GB RAM) by ensuring tests run isolated, bounded, and without uncontrolled concurrent GPU load.
4. **Zero-Tolerance Parity & Fairness**: Verifies paired colors, paired seeds, bitwise RNG reproducibility, and zero-tolerance numerical logit and action parity.

---

## 2. Directory Layout & Test Suite Structure

Test suites are located in `tests/e2e/` (strictly outside `.agents/teamwork/`):

```
E:\Downloads\Chat_GPT_AI\
├── tests/
│   └── e2e/
│       ├── __init__.py
│       ├── conftest.py               # Shared fixtures, environment setup, reference constants
│       ├── test_tier1_features.py     # Tier 1: Feature Coverage (>=5 tests per feature for all 20 features)
│       ├── test_tier2_boundaries.py   # Tier 2: Boundary & Corner Cases (>=5 tests per feature where boundaries exist)
│       ├── test_tier3_interactions.py # Tier 3: Cross-Feature Interactions & Pairwise Combinations
│       └── test_tier4_scenarios.py    # Tier 4: Real-World Realistic Application Scenarios
├── gigaforge/
│   ├── .venv_native/                  # Dedicated test execution Python environment
│   └── native/GigaForge.exe           # High-throughput native C++ simulator
├── NovaForge/
│   └── assets/                        # Frozen baseline models and opponent assets
└── .agents/teamwork/
    ├── TEST_INFRA.md                  # This document
    └── TEST_READY.md                  # Publication gate check report
```

---

## 3. Four-Tier Verification Model

The test architecture organizes verification into four progressive tiers:

| Tier | Category | Minimum Coverage | Purpose & Scope |
|---|---|---|---|
| **Tier 1** | **Feature Coverage** | $\ge 5$ test cases per feature (100 total) | Exhaustive verification of primary happy-path behavior, functional contracts, schemas, and invariants for each of the 20 features. |
| **Tier 2** | **Boundary & Corner Cases** | $\ge 5$ test cases per feature (where boundaries exist) | Boundary stress, missing inputs, division-by-zero, extreme ranges, corrupted files, zero variance fallbacks, and error paths. |
| **Tier 3** | **Cross-Feature Interactions** | Pairwise combinations | Integration across feature pairs: seed-pairing + color symmetry; pause -> save -> resume -> H2H eval; export -> dual serialization -> CPU inference -> latency budget. |
| **Tier 4** | **Real-World Scenarios** | $\ge 5$ realistic end-to-end applications | Full simulated match chunk batching & resumption; offline RLBot v5 mock packet stream; secondary opponent panel round-robin; complete autonomous research cycle pilot. |

---

## 4. 20-Feature Coverage Matrix

All 20 features from `PROJECT.md` are covered across Tiers 1–4:

| Feature # | Feature Name | Milestone | Tier 1 (Coverage) | Tier 2 (Boundaries) | Tier 3 (Interactions) | Tier 4 (Scenarios) |
|---|---|---|---|---|---|---|
| **F1** | Baseline Hash & Contract Preservation | M1 | `test_f1_baseline_hashes` (5) | `test_f1_corrupted_hash_rejection` (5) | F1 $\times$ F15 | S4 |
| **F2** | Launcher Routing & Virtualenv Invariant | M1 | `test_f2_launcher_routing` (5) | `test_f2_missing_venv_fallback` (5) | F2 $\times$ F19 | S4 |
| **F3** | Native Simulator Self-Tests & GAE Verification | M1 | `test_f3_native_selftest` (5) | `test_f3_protocol_invalid_flag` (5) | F3 $\times$ F6 | S1, S5 |
| **F4** | Resource Boundaries & Safe Telemetry Monitoring | M2 | `test_f4_resource_limits` (5) | `test_f4_vram_thermal_breach` (5) | F4 $\times$ F6 | S5 |
| **F5** | Candidate Checkpoint Retention System | M2 | `test_f5_checkpoint_retention` (5) | `test_f5_missing_checkpoint_lookup` (5) | F5 $\times$ F8 | S5 |
| **F6** | Bounded Pilot Training & Resumption Verification | M2 | `test_f6_pause_resume_stopfile` (5) | `test_f6_stopfile_latency_boundary` (5) | F6 $\times$ F12 | S5 |
| **F7** | Chronos Targeted Model Optimization | M3 | `test_f7_chronos_ppo_contract` (5) | `test_f7_kl_anchor_divergence` (5) | F7 $\times$ F8 | S5 |
| **F8** | Multi-Arm Screening via `arena-rng-v4` Dev Split | M3 | `test_f8_dev_split_screening` (5) | `test_f8_threshold_filtering_bounds` (5) | F8 $\times$ F9 | S3, S5 |
| **F9** | Candidate Confirmation Split Evaluation | M3 | `test_f9_confirmation_alpha_spending` (5) | `test_f9_alpha_spending_convergence` (5) | F9 $\times$ F13 | S3 |
| **F10** | Secondary Opponent Panel Evaluation | M4 | `test_f10_secondary_panel_inventory` (5) | `test_f10_missing_opponent_asset` (5) | F10 $\times$ F11 | S3 |
| **F11** | Regression Tolerance Verification | M4 | `test_f11_regression_tolerances` (5) | `test_f11_extreme_regression_bounds` (5) | F11 $\times$ F13 | S3 |
| **F12** | Held-Out 2,000-Game Direct H2H Evaluation | M5 | `test_f12_direct_h2h_execution` (5) | `test_f12_unequal_paired_seeds` (5) | F12 $\times$ F13 | S1 |
| **F13** | Statistical Confidence Interval & Promotion Gate | M5 | `test_f13_confidence_interval_math` (5) | `test_f13_zero_variance_hoeffding` (5) | F13 $\times$ F12 | S1 |
| **F14** | RLBot v5 TOML & Loadout Packaging | M6 | `test_f14_rlbot_v5_toml_schema` (5) | `test_f14_malformed_toml_detection` (5) | F14 $\times$ F15 | S2, S4 |
| **F15** | Model Dual Serialization & Sidecar Generation | M6 | `test_f15_dual_serialization_identity` (5) | `test_f15_missing_sidecar_validation` (5) | F15 $\times$ F16 | S2, S4 |
| **F16** | Logit & Argmax Action Parity Verification | M6 | `test_f16_logit_action_parity` (5) | `test_f16_all_masked_action_boundary` (5) | F16 $\times$ F17 | S2, S4 |
| **F17** | CPU-Only Deployment & Single-Thread Enforcement | M6 | `test_f17_cpu_single_thread_runtime` (5) | `test_f17_cuda_leak_guard` (5) | F17 $\times$ F18 | S2, S4 |
| **F18** | End-to-End Latency Benchmarking vs 58.33ms Deadline | M6 | `test_f18_latency_benchmark_budget` (5) | `test_f18_search_latency_violation` (5) | F18 $\times$ F17 | S2, S4 |
| **F19** | Windows Launcher Suite Verification | M6 | `test_f19_windows_launchers` (5) | `test_f19_offline_install_isolation` (5) | F19 $\times$ F2 | S4 |
| **F20** | Read-Only Discord Governance & Provenance Logging | M1-6 | `test_f20_discord_governance` (5) | `test_f20_network_forbidden_guard` (5) | F20 $\times$ F1 | S5 |

---

## 5. Authoritative Expected Output Oracles

For every test case, expected outputs are derived from explicit, immutable ground truth:

1. **Cryptographic Hashes (F1, F15)**:
   - Chronos Policy: `cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360`
   - Chronos Shared Trunk: `e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640`
   - Galactus V2 Policy: `f31e15e118f14713ffc5d4af84ab0d8018c04f1451805f50a2e2df9d396603ed`
   - Galactus V2 Shared Trunk: `a38be9da0a57141d0bf8e38bd51944f77aa04912f7912e9c4bc49f93db7285a4`
2. **Native Protocol Handshakes (F3)**:
   - `--head-to-head-protocol` $\to$ verbatim `direct-h2h-v1\n`
   - `--evaluation-protocol` $\to$ verbatim `arena-rng-v4\n`
   - `--selftest` $\to$ exit code 0 and stdout containing `RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS` and `NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS`.
3. **Statistical Confidence Interval Formulas (F13)**:
   - Score rate per seed pair: $\bar{y}_p = \frac{(W + 0.5 \times D)_{\text{blue}} + (W + 0.5 \times D)_{\text{orange}}}{2}$.
   - Overall mean: $\bar{y} = \frac{1}{P}\sum \bar{y}_p$.
   - Sample variance: $s^2 = \frac{1}{P-1}\sum (\bar{y}_p - \bar{y})^2$.
   - Margin of error (Student-t, 95%): $m = t_{0.975, P-1} \cdot \sqrt{s^2 / P}$ when $s^2 > 0$.
   - Hoeffding fallback: $m = \sqrt{\ln(40) / (2P)}$ when $s^2 = 0$.
   - Promotion criterion: Lower bound $\bar{y} - m > 0.5000$.
4. **Sequential $\alpha$-Spending (F9)**:
   - Error allocation for confirmation step $k$: $\alpha_k = \frac{0.05}{k(k+1)}$.
   - Convergence property: $\sum_{k=1}^\infty \alpha_k = 0.05$.
5. **Action Delay Deadline (F18)**:
   - Physics: 120 Hz ($8.333\text{ ms/tick}$).
   - Decision skip: 8 ticks ($66.667\text{ ms}$).
   - Application delay: 7 ticks ($58.333\text{ ms}$).
   - Maximum callback latency allowable: strictly $< 58.33\text{ ms}$.
6. **Hitbox Geometry Presets (F3, F14)**:
   - Chronos: `CAR_CONFIG_BREAKOUT` (`car_id = 22`).
   - Galactus: `CAR_CONFIG_OCTANE` (`car_id = 23`).

---

## 6. How to Run the Test Suite

Execute tests using the repository's pinned native virtual environment:

### Full Test Suite Run
```powershell
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/ -v
```

### Run by Verification Tier
```powershell
# Tier 1: Feature Coverage
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/test_tier1_features.py -v

# Tier 2: Boundary & Corner Cases
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/test_tier2_boundaries.py -v

# Tier 3: Cross-Feature Interactions
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/test_tier3_interactions.py -v

# Tier 4: Real-World Scenarios
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/test_tier4_scenarios.py -v
```

### Run by Specific Feature
```powershell
# Example: Feature 1 (Baseline Hashes)
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/ -k "f1_" -v

# Example: Feature 13 (Confidence Interval)
E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest tests/e2e/ -k "f13_" -v
```
