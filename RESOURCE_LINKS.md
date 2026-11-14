# Useful links from the project, previous chat and handoff

_Last organized 2026-10-17. These are **references**, not endorsements or proof that external claims work. The list intentionally excludes short-lived authenticated download URLs, local server addresses, secrets, internal tool links and duplicate generated ZIP builds. Historical items are **not instructions to resume RL/PPO training**._

## Primary project and context (start here)

| Purpose | Link |
| --- | --- |
| Project source | https://github.com/DMDIASSS/Chat_GPT_AI |
| Active branch (read current HEAD) | https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/native-quality-campaign |
| Existing long engineering handoff | https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/AI_CONTINUATION_PROMPT.md |
| Known diagnostics source snapshot `4c45dea` | https://github.com/DMDIASSS/Chat_GPT_AI/tree/4c45deadc39508459a1b69a4b6018f878453c89f |
| Workflow / local training guide | https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/REPLAY_FINAL_GUIDE.md |
| Jump/boost and RLBot check | https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_CONTROL_CHECK.md |
| All formats / cache support | https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_ALL_FORMATS.md |
| RLBot export instructions | https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/README_REPLAY_RLBOT_EXPORT.md |
| Historical offline-imitation handoff | https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/HANDOFF_OFFLINE_IMITATION.md |
| Last control-check source ZIP (update, **no weights**) | https://github.com/DMDIASSS/Chat_GPT_AI/raw/4c45deadc39508459a1b69a4b6018f878453c89f/downloads/Replay_Control_Check_Update.zip |
| Branch ZIP (code; possibly not datasets) | https://github.com/DMDIASSS/Chat_GPT_AI/archive/refs/heads/codex/native-quality-campaign.zip |
| Historical local Codex conversation (private) | https://chatgpt.com/local/01a12e3a-b5f7-7473-a0b8-783603c0906a |
| Historical Codex-app thread (private deep link) | codex://threads/01a12e3a-b5f7-7473-a0b8-783603c0906a |

**Chat access warning:** local/deep links might open the user's own session, but a new coding AI cannot automatically read the full content. Ask the user to attach the **exported text file in the AI conversation** if essential. Do not put a full private transcript in a public GitHub repository.

## Human replay data, validation and tooling

| Purpose | Link |
| --- | --- |
| User-referenced 3v3 replay group | https://ballchasing.com/group/ranked-3v3-2026-10-15-lwizwie17f |
| Ranked GC3–SSL doubles search | https://ballchasing.com/?playlist=11&min-rank=21&max-rank=22 |
| Earlier duels filtered search | https://ballchasing.com/?playlist=10&min-rank=21&max-rank=22&replay-after=2021-01-01&replay-before=2026-10-12 |
| Ballchasing API | https://ballchasing.com/doc/api |
| Ballchasing upload | https://ballchasing.com/upload |
| High-level replay dataset (community) | https://github.com/Rolv-Arild/rl-high-level-dataset |
| Replay pretraining research | https://github.com/Rolv-Arild/replay-pretraining |
| `replicar` reconstruction research | https://github.com/Rolv-Arild/replicar |
| Python Ballchasing tools | https://github.com/Rolv-Arild/python-ballchasing |
| RLGym tools | https://github.com/RLGym/rlgym-tools |
| `boxcars` replay decoder | https://github.com/nickbabcock/boxcars |
| Official RocketSim upstream | https://github.com/ZealanL/RocketSim |
| RocketSim-enabled gym / RLGym history | https://github.com/lucas-emery/rocket-league-gym |
| Current RLGym docs and values | https://rlgym.org/Cheatsheets/game_values |

The 3v3 group's exact contents/ranks and the authenticity/quality of outside replay uploads must be verified, not assumed from names or earlier chats. Follow API rules and rate limits. The direct replay parser still has known input rejection cases.

## RLBot and deployment

- RLBot framework: https://github.com/RLBot/RLBot
- RLBot documentation: https://wiki.rlbot.org/
- RLBot bot pack: https://github.com/RLBot/RLBotPack
- RLBot organization: https://github.com/orgs/RLBot/repositories
- Representative reference project `VirxEB` (research only): https://github.com/VirxEC/VirxEB
- Other bot examples mentioned in older chats (not training labels): https://github.com/ZeroII99II/RankedSSLRLBOT , https://github.com/ZeroII99II/NezBot , https://github.com/SubparN0va/GGLBot

## Compute, ML and performance references

- PyTorch scaled dot-product attention: https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html
- CUDA graphs guidance: https://pytorch.org/docs/stable/notes/cuda.html#cuda-graphs
- NVIDIA CUDA 12.6 installer archive: https://developer.nvidia.com/cuda-12-6-0-download-archive
- Weights & Biases docs: https://docs.wandb.ai/
- RLGym Python package: https://pypi.org/project/rlgym/

## Historical Slater, native training and mechanics (background **only**)

The earlier thread explored many approaches besides offline human replay imitation. Save these for future reference, but **do not treat them as current requirements**.

- Historical project branch: https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/improve-slater-training
- Historical mechanics branch: https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/mechanics-curriculum
- Historical native source branch: https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-gigalearn-replicar/GigaLearn_Project/Native_Backend/README.md
- GigaLearnCPP source (community; historical): https://github.com/ZealanL/GigaLearnCPP-Leak
- RL replication/learning projects: https://github.com/Rolv-Arild/rocket-learn , https://github.com/Rolv-Arild/rlgym
- GigaLearn guide and examples: https://github.com/PiggyVevo/GigalearnGuide , https://github.com/PiggyVevo/ExampleRocketLeagueBot
- Older PPO/RL guide, **not** current training instruction: https://github.com/ZealanL/RLGym-PPO-Guide/
- PPO reward discussion, historical: https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/rewards.md
- PPO learner settings, historical: https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/learner_settings.md
- Community mechanics list: https://0byte-coding.github.io/rocket_league_mechanics/
- Rocket League mechanics guide: https://prejump.com/rocket-league-mechanics
- Rank mechanics comparisons (informal): https://www.rocketleague-help.com/mechanics-by-rank , https://www.trophi.ai/post/rocket-league-mechanics-by-rank

## Videos and adjacent model research cited in the older chat (context, not current implementation)

- Community video reference A: https://www.youtube.com/watch?v=4VFoUgqSgIg&t=46s
- Community video reference B: https://www.youtube.com/watch?v=BttzyfPjUcg
- Community video reference C: https://www.youtube.com/watch?v=QprErElWT-E
- Earlier System One / Jev model idea: https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Older high-level replay dataset list/API reference: https://www.kaggle.com/api/v1/datasets/list/rolvarild/high-level-rocket-league-replay-dataset

These were shared as possible ideas or tooling references. Their applicability to the current replay-only imitation bot has **not** been established.

## Previous branch updates: historical downloads

These were mentioned in the exported conversation, but they are not a substitute for the latest branch; many were incremental, may be superseded and may not include model weights. **Do not blindly install them over the current checkout.**

- Replay reconstruction update: https://github.com/DMDIASSS/Chat_GPT_AI/raw/15160008ef2ac9b09d2e3385d90eda6c0ebc56cf/downloads/Replay_Reconstruction_Fix.zip
- Real data parser update: https://github.com/DMDIASSS/Chat_GPT_AI/raw/faa5cc7ec782b48d199cc7ff93f4cb47821fb71f/downloads/Replay_Real_Data_Fix_v3.zip
- Replay imitation code update: https://github.com/DMDIASSS/Chat_GPT_AI/raw/e1c3bc9dd8c3e82817a87360bf951c713d544923/downloads/Replay_Imitation_Offline_Update.zip
- RLBot exporter update: https://github.com/DMDIASSS/Chat_GPT_AI/raw/e8c987c0dd85c7b5b77f7db707429950ee5cb5b8/downloads/Replay_RLBot_Exporter.zip
- RLBot boost fix: https://github.com/DMDIASSS/Chat_GPT_AI/raw/c104f9eba35bcedf1e422cc58b63fea2888b312b/downloads/Replay_RLBot_Boost_Fix.zip
- Native runtime v2: https://github.com/DMDIASSS/Chat_GPT_AI/raw/5e9e87fc7ad9d64a6cf2c5e9344f4f5957939935/downloads/Replay_Native_Runtime_v2.zip
- Native runtime v2.1: https://github.com/DMDIASSS/Chat_GPT_AI/raw/a5711c4325fd184d553b994739eb5068b465d93b/downloads/Replay_Native_Runtime_v2_1.zip
- Multicore runtime: https://github.com/DMDIASSS/Chat_GPT_AI/raw/8fa976adada2ca4c0890784a48dfd4f77d968b7a/downloads/Replay_Native_Runtime_Multicore.zip
- GPU runtime benchmark update: https://github.com/DMDIASSS/Chat_GPT_AI/raw/dbf3340289f87028fc47929fe837cf985e1ec4f3/downloads/Replay_Runtime_GPU_Benchmark.zip

## Which information to share with another AI

For initial inspection, share **this context kit and repository branch**. For actual bot debugging, attach the two small `validation_diagnostics.json` and `CONTROL_DIAGNOSTICS.json` reports once generated. Attach matching model/export artifacts only if the AI is tasked with running those exact weights, and use a private transfer channel. For a true end-to-end history, attach the **sanitized** `Вставленный текст.txt` chat export in the conversation; a local URL is not access.
