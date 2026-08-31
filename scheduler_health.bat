@echo off
rem Self-healing watchdog: if the 20-min cycle schedule silently died while
rem the market is open, this runs a cycle directly (cycle lockfile makes it
rem race-safe). Registered every 30 min inside the market window.
cd /d "E:\Alapaca hackathon"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" run_agent.py --health >> journal\scheduler_health.log 2>&1
