@echo off
setlocal
cd /d %~dp0
.venv_native\Scripts\python.exe watch_custom.py --actor "E:\Downloads\Chat_GPT_AI\gigaforge\runs\research05\watch_pins\chronos\chronos_antidive_isolated_v3\actor.lt" --opponent original_galactus --profile match
pause
