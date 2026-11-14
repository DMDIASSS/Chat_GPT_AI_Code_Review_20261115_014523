Take over the existing Rocket League bot research project on the local Windows PC to develop, test, and produce a demonstrably stronger bot (improved Chronos or improved Galactus) through empirical research, bounded experiments, and fair held-out evaluation.

Working directory: E:\Downloads\Chat_GPT_AI
Integrity mode: development

## Requirements

### R1. Empirical Research and Model Improvement
Develop and test bot improvements for Chronos and/or Galactus, prioritizing a demonstrable, reliable improvement to one bot in 1v1 over maintaining two unsuccessful training systems. Decide autonomously whether to focus on Chronos (1v1 Breakout) or Galactus V2 (1v1 Octane) based on initial audit and baseline verification. Make ordinary reversible engineering and research decisions autonomously based on empirical evidence, feasibility, and expected improvement per unit of time. If no candidate qualifies within the declared compute budget, preserve the baseline and deliver the experimental results, diagnosis, and next justified experiment. Never manufacture or overstate success.

### R2. Correctness Audit and Bounded Experimentation
Begin with an audit and short pilot. Declare wall-time, RAM/VRAM limits, checkpoint cadence, and stopping conditions before longer runs. Preserve safe pause/resume and stop on resource instability. Inspect actual files, inventory existing code, dependencies, models, and results, and audit native simulator contracts (observation features, action delays, hitboxes), optimization pipelines, and reward structures before building larger systems. Run bounded experiments with matched controls, versioned experiments, and strict preservation of original artifacts, checkpoints, environments, exports, and historical results. Respect laptop hardware constraints (Intel i5-10300H, NVIDIA GTX 1650 Ti Mobile, 16 GB RAM).

### R3. Objective Verification and Promotion Protocol
Evaluate bot performance in fair, held-out direct head-to-head matches against relevant baselines using direct-h2h-v1 and arena-rng-v4 with balanced color rotations and fresh evaluation seeds. A candidate bot qualifies for promotion only when it demonstrates a statistically significant advantage over its baseline in held-out direct head-to-head testing, defined as the lower bound of the 95% confidence interval strictly exceeding a 50.0% draw-adjusted match score over a 2,000-game test on fresh seeds. Use separate development and confirmation seeds. Reserve the fresh 2,000-game final test for a frozen, selected candidate. Predeclare the confidence-interval method, accounting for paired colors. If testing multiple finalists, account for multiple comparisons. Before promotion, evaluate a fixed secondary opponent panel and report per-opponent changes, with regression tolerances declared beforehand.

### R4. Packaging, Export, and Deployment
Produce independently usable bot exports in RLBot-compatible formats (RLBot v5 .toml + .lt, and .pt + .cfg where supported) with working launchers, verifying configuration, runtime loading, and logit/action agreement against the source model. Measure exported inference latency—including observation construction and action selection—against the actual action-delay deadline, and verify whether deployment uses CPU or GPU.

### R5. Research Data and Access Governance
Use authorized Discord channels and exports via read-only Discord MCP research without posting, DMing, inviting, or publishing private logs. Unavailable Discord access must not block local research.

## Acceptance Criteria

### Bot Performance and Verification
- [ ] Candidate bot demonstrates a statistically significant advantage over the baseline in held-out 1v1 direct head-to-head matches (lower bound of the 95% confidence interval > 50.0% draw-adjusted match score across a fresh 2,000-game test).
- [ ] Direct head-to-head matches are conducted against the frozen baseline (original Chronos or Galactus V2) under identical simulator physics, hitboxes, and timing.
- [ ] Separate development and confirmation seeds are maintained; the fresh 2,000-game final test is reserved for a frozen, selected candidate.
- [ ] The confidence-interval method is predeclared, accounts for paired colors, and accounts for multiple comparisons if testing multiple finalists.
- [ ] Before promotion, the candidate is evaluated against a fixed secondary opponent panel with per-opponent changes reported, meeting predeclared regression tolerances.
- [ ] If no candidate qualifies within the declared compute budget, the baseline is preserved and experimental results, diagnosis, and the next justified experiment are delivered without manufacturing or overstating success.

### System Correctness and Resource Boundaries
- [ ] Audit and short pilot are completed before longer runs, with wall-time, RAM/VRAM limits, checkpoint cadence, and stopping conditions declared beforehand.
- [ ] Original models, checkpoints, environments, exports, and existing evaluation results are preserved without accidental overwrites or unintentional training resumptions.
- [ ] Checkpoints, training configs, model hashes, dataset splits, seeds, and raw match logs are preserved with complete provenance.
- [ ] Safe pause/resume is preserved, and runs halt automatically on resource instability or thermal/memory limit violations.

### Packaging, Deployment, and Governance
- [ ] Exported bot loads and executes successfully in an RLBot v5 test match without crashes.
- [ ] Exported inference latency (including observation construction and action selection) is verified against the action-delay deadline, with CPU/GPU deployment verified.
- [ ] Working Windows launchers, provenance records, and start/watch/report/pause procedures are verified and documented.
- [ ] Discord MCP research is read-only on authorized channels, and local research proceeds without blocking if Discord access is unavailable.
