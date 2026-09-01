@echo off
rem Near-live frontend: regenerate the static dashboard from the journal +
rem account API and push to GitHub Pages, every 30 min during the session.
rem Push only happens when the content actually changed.
cd /d "E:\Alapaca hackathon"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" dashboard.py >> journal\scheduler_publish.log 2>&1
rem Publish and Retro can both commit+push within seconds of each other, which
rem got the loser's push rejected outright ("cannot lock ref"). Rebase onto the
rem winner and retry instead of dropping the commit on the floor.
git add docs/dashboard.html >> journal\scheduler_publish.log 2>&1
git diff --cached --quiet || (git commit -m "auto: dashboard refresh" && (git push || (git pull --rebase && git push))) >> journal\scheduler_publish.log 2>&1
