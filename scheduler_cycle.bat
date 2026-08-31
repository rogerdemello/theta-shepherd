@echo off
rem One Theta Shepherd decision cycle. Registered in Windows Task Scheduler
rem every 20 min, 19:00-01:30 IST Mon-Fri; the agent itself checks the
rem market clock and exits when closed.
cd /d "E:\Alapaca hackathon"
set PYTHONIOENCODING=utf-8
rem Each task logs to its own file: Cycle and Publish both fire at :40 and
rem concurrent >> to one shared log makes the loser exit 1 with no output.
".venv\Scripts\python.exe" run_agent.py >> journal\scheduler_cycle.log 2>&1
