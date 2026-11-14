@echo off
setlocal
cd /d %~dp0
.venv_native\Scripts\python.exe watch_custom.py --actor "E:\Downloads\Chat_GPT_AI\gigaforge\runs\research06\watch_pins\chronos\chronos_winrate_dominance_v1\actor.lt" --opponent ripple --profile match
pause
