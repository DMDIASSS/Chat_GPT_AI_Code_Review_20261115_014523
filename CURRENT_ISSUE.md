# Current issue — replay-trained RLBot often idles, circles and does not appear to jump

**Status on 2026-10-17:** investigated partially; source diagnostics published; user-machine outputs are not yet verified in the supplied conversation. Treat this as an open bug, not a diagnosis already settled.

## Observed symptoms

- The `ReplayDuelsDoubles` bot sometimes sits AFK or turns in circles; sometimes touches/defends the ball.
- User barely sees boost outside kickoff and has not noticed jumping.
- Earlier five-second-sampled log: 76 sampled policy outputs, 0 jump and 1 boost; the sampling cadence can miss short button presses.
- Token 14 often chosen (22 samples), with zero throttle, substantial steering and no button pulses. This explains the issued steering, but not the model's selection of that token.
- The 256-token vocabulary includes jump/boost in some first-eight-tick chunks; absence of those actions in one sampled rollout does **not** prove tokenization removed them.

## Evidence to gather next

| Evidence | File or method | What it distinguishes |
| --- | --- | --- |
| Raw vs tokenized vs predicted action coverage | `data\isolated\replay_imitation\runs\replay_scratch01\validation_diagnostics.json` | demonstration imbalance, tokenization loss, model underprediction |
| Export/model argmax and numeric parity | Same JSON | wrong/frozen/obsolete RLBot weights, export divergence |
| Real issued buttons, kickoff separation | `data\rlbot_exports\ReplayDuelsDoubles\CONTROL_DIAGNOSTICS.json` | model issued vs suppressed controls |
| Inference latency/packet gaps | Same JSON | 66.67 ms budget violations, missed edges, resets |
| Actual match observations versus training features | instrument specific packet/features without leaking account info | input/domain mismatch |
| Exact all-format run state | `REPLAY_IL_FINAL.bat status` and current run reports | whether newer data/model actually exists |

Run `CHECK_REPLAY_DUELS_DOUBLES.bat` from the existing Windows checkout to produce the first report. Run RLBot for a minute with the updated export for live report; don't treat launch alone as proof of a model fix.

## Diagnostic decision tree

1. **Raw jump/boost very rare?** Check human source coverage and reconstruction validity (edge retention, truncation, parser errors). No synthetic action labels.
2. **Raw coverage good but tokenized coverage poor?** Investigate medoid chunk fitting / 32-tick vs first-eight-tick retention. Preserve the old dictionary and model; version any new vocabulary.
3. **Tokenized coverage good but predictions poor?** Inspect token distribution, conditional accuracy by jump/boost states, data balance and validation. A new supervised loss/architecture should be a *separate versioned experiment*.
4. **Predictions good offline but export differs?** Repair exact export/checkpoint/dictionary parity, not the learned controls.
5. **Export parity good but issued commands absent or timing exceeds budget?** Fix packet-driven runtime, callback cadence, short button pulse application and history reset behavior; test with the user's runtime.
6. **Commands correct and timely but behavior still poor?** Diagnose closed-loop distribution shift, mismatch between human trajectories and model-driven states, missing inputs / physics semantics, and measure repeatable game outcomes.

## Acceptance criteria

- Produce actual user-model figures, not random-fixture-only tests.
- For each symptom, state what is confirmed and what remains uncertain.
- If modifying source, include a matching unit/integration test and a relevant quantitative before/after check without bypassing checksum/protocol safety.
- Inspect at least one short real live match or report after a behavioral change before saying the symptom is solved.
- Avoid forced constant throttle, random jumps/boost, or a disguised scripted policy presented as learned progress.

## Related instructions

- https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_CONTROL_CHECK.md
- https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/REPLAY_FINAL_GUIDE.md
- https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/AI_CONTINUATION_PROMPT.md
