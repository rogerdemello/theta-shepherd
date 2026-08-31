@echo off
rem Nightly post-close pipeline (01:45 IST; UTC date still equals the session
rem date): retrospective -> regenerate dashboard -> publish to GitHub Pages.
cd /d "E:\Alapaca hackathon"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" run_agent.py --retro >> journal\scheduler_retro.log 2>&1
".venv\Scripts\python.exe" dashboard.py >> journal\scheduler_retro.log 2>&1
git add docs/dashboard.html >> journal\scheduler_retro.log 2>&1
git diff --cached --quiet || (git commit -m "auto: nightly dashboard refresh" && git push) >> journal\scheduler_retro.log 2>&1
