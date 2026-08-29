@echo off
rem Nightly retrospective: distill the session's journal into lessons.md.
rem Runs at 01:45 IST (post-close); the UTC date still equals the session date.
cd /d "E:\Alapaca hackathon"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" run_agent.py --retro >> journal\scheduler.log 2>&1
