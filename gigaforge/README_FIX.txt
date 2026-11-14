GIGAFORGE W&B FIX FOR START 3
============================

Issue found in the GitHub branch codex/novaforge-v1:
- GigaForge/setup_runtime.py installs wandb>=0.23,<0.25.
- NovaForge/requirements-wandb.txt requires wandb==0.31.0.
- Shared nova/tracking.py calls wandb.login(prompt=False, verify=True).
- prompt=False is unsupported in the old GigaForge SDK versions.

INSTALL (without resetting any experiments):
1) Extract the contents of this ZIP directly into:
   E:\Downloads\Chat_GPT_AI\gigaforge\
   Allow setup_runtime.py to be overwritten (backup the original if modified).
2) Double-click FIX_WANDB_START3.bat ONE TIME.
3) On successful verification, double-click 3_START_OR_RESUME.bat.

The fix targets the Python environment Start 3 actually uses. It upgrades
only the optional W&B package and its Python dependencies. It does NOT reset
runs/native01 or change bot weights, checkpoints, or NovaForge's .venv.
The repaired setup_runtime.py prevents subsequent GigaForge setup runs from
reinstalling incompatible W&B versions.

Credentials are discovered by the W&B SDK for your Windows account. No key
is copied or stored by these files. If NovaForge used a session-only
WANDB_API_KEY environment variable, run Start 3 with that same environment;
otherwise its normal persisted W&B login should be reused automatically.

If login verification still fails, the batch script prints the actual
exception from the W&B check. Avoid sharing any API keys or unredacted
credential files.
