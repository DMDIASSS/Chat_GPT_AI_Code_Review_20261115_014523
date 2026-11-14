# Scope: E2E Testing Track

## Overview
The E2E Testing Track is responsible for designing, implementing, and validating a comprehensive, requirement-driven, opaque-box test suite for the Rocket League bot research project. When all tiers are verified, it publishes `TEST_READY.md`.

## Methodology & Tiers
- **Tier 1: Feature Coverage (>=5 per feature)**:
  - Feature 1: Model hash invariance across parent & assets.
  - Feature 2: Launcher routing delegating to `_RUN.bat`.
  - Feature 3: Native `--selftest` and `--head-to-head-protocol` handshakes.
  - Feature 4: Resource limits, thermal boundaries, and process telemetry.
  - Feature 5: Checkpoint retention rules for shortlisted trials.
  - Feature 6: Safe pause/resume via `STOP` file.
  - Feature 12: `direct-h2h-v1` match runner execution.
  - Feature 13: 95% Confidence Interval calculation (Student-t paired-color).
  - Feature 14-19: RLBot v5 TOML parsing, TorchScript parity, CPU device selection, callback latency budget (<58.33 ms).
- **Tier 2: Boundary & Corner Cases (>=5 per feature)**:
  - Zero sample variance Hoeffding bound fallback.
  - Action mask zero valid actions exception.
  - Contact normal omission matching public packet.
  - Blue/Orange side parity and color rotation symmetry.
  - Missing collision meshes handling.
- **Tier 3: Cross-Feature Combinations (pairwise coverage)**:
  - Paired colors + paired seeds.
  - Training pause -> checkpoint save -> resume -> H2H evaluation.
  - Model export -> TCP loopback handshake -> latency benchmarking.
- **Tier 4: Real-World Application Scenarios**:
  - Full simulated head-to-head match chunk.
  - Offline RLBot v5 mock packet stream processing.
  - Secondary opponent panel round-robin test.

## Key Deliverables
- `TEST_INFRA.md`: Template index describing test runner, directory layout, and coverage matrix.
- `TEST_READY.md`: Ready signal published when all test tiers are verified.
