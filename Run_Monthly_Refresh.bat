@echo off
REM Monthly refresh of the saved websites. Run by hand, or schedule it (see below).
REM   1. fetch every seed again; only pages whose text changed are saved again
REM   2. cut changed pages into searchable chunks
REM   3. list pages the sites now link to that we do not know yet (not added automatically)
REM Reading changed pages with the model, and approving, stays in the review screen.
REM
REM To run it every month: Windows Task Scheduler -> Create Basic Task -> Monthly ->
REM Start a program -> this file.

cd /d "%~dp0components\c2-knowledge-graph\service"
set LOG=..\research\data\crawl\refresh_log.txt
echo ==== %date% %time% ==== >> %LOG%

.venv\Scripts\python.exe -m app.core.acquisition --db >> %LOG% 2>&1
.venv\Scripts\python.exe -m app.core.knowledge.chunks --ingest >> %LOG% 2>&1
.venv\Scripts\python.exe -m app.core.acquisition --discover https://www.drp.gov.lk/en/home.php --depth 6 --limit 400 >> %LOG% 2>&1

echo Done. Open Start_Review_UI.bat: changed pages appear under "Page changed since it was read".
echo Details are in components\c2-knowledge-graph\research\data\crawl\refresh_log.txt
pause
