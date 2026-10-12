@echo off
rem Double-click to open the HelaGuide review page in your browser.
rem Needs Docker Desktop running with the postgres and neo4j containers started.
cd /d "%~dp0components\c2-knowledge-graph\service"
echo Starting the HelaGuide review page at http://127.0.0.1:8765
echo Keep this window open. Close it to stop.
".venv\Scripts\python.exe" -m app.admin_ui
pause
