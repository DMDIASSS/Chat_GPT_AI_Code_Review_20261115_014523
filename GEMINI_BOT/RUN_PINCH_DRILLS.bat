@echo off
cd /d "%~dp0"
echo ========================================================
echo Starting Scenario & Pinch Fine-Tuning Drills...
echo ========================================================
"E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" train_scenarios.py --scenarios 100 --wandb offline
pause
