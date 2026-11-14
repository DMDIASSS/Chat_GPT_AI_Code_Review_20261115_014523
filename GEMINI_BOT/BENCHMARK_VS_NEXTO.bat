@echo off
cd /d "%~dp0"
echo ========================================================
echo Starting Autonomous RocketSim Benchmark vs Nexto...
echo ========================================================
"E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" benchmark_vs_nexto.py --games 5 --duration 180
pause
