# Run the final C4 application, run the tests, reproduce the study

All commands are PowerShell, from `C:\Users\Lenovo\Desktop\HelaGuide\components\c4-presentation`. Generated data lives under `service\.local` (git-ignored).

## 1. Start the complete final application (content 3.1 with the trained policy)
Backend (port 8021). Use FIXED folder names, not a timestamp, if you want learned feedback and saved profiles to survive a restart.
```powershell
cd service
$env:C4_WORKSPACE_MODE = "simulation"; $env:C4_WORKSPACE_SEED = "0"; $env:C4_WORKSPACE_CONTENT_MODE = "demo"
$env:C4_WORKSPACE_DATABASE = "$PWD\.local\v2\workspace\final\state.sqlite3"
$env:C4_GUIDANCE_CONTENT_SCHEMA = "c4-guidance-content-3.1"
$env:C4_PREPARED_CONTENT_ENABLED = "true"; $env:C4_PREPARED_CONTENT_MODE = "demo"; $env:C4_PREPARATION_ON_MISS = "false"; $env:C4_LLM_ENABLED = "false"
$env:C4_PREPARED_CONTENT_DIRECTORY = "$PWD\.local\prepared-content\final\v31"
$env:C4_GUIDANCE_API_ENABLED = "true"; $env:C4_RESEARCH_PREVIEWS_ENABLED = "true"
$env:C4_DEMO_ACCEPTED_CONTENT = "true"   # LOCAL RESEARCH DEMO ONLY: ordinary journeys use the cached, source-grounded official wording (see docs/C4-DEMO-ACCEPTANCE.md). Omit for strict reviewed-only behaviour.
$env:C4_PP1_POLICY_ENABLED = "true"
$env:C4_PP1_POLICY_DIRECTORY = "$PWD\.local\pp1-learning\v31-live-final"
$env:C4_PP1_CHECKPOINT = "$PWD\.local\pp1-learning\v31-study-20261022-a\seed-23-x0.25-525-n5000.npz"
$env:C4_PP1_EXPLORATION = "0.25"
$env:C4_PP1_EXPERIMENT_DIRECTORY = "$PWD\.local\pp1-learning\v31-study-20261022-a"
.\.venv\Scripts\python.exe -m uvicorn app.workspace:app --host 127.0.0.1 --port 8021
```
The checkpoint is the 525-feature model trained on 5,000 synthetic observations with exploration 0.25, seed 23 (best on the development cases). Do not set `C4_PP1_POLICY_ENABLED` to start without personalisation (guests and standard guidance still work).
Frontend (second window):
```powershell
cd demo-frontend
$env:VITE_C4_API_BASE_URL = "http://127.0.0.1:8021"
npm run dev -- --host 127.0.0.1 --port 5173
```
Open `http://127.0.0.1:5173/` (citizen view), `http://127.0.0.1:5173/?research=1` (preview chooser, inspector, comparison, learning evidence) and `http://127.0.0.1:5173/#embed/synthetic-practice-v2` (standalone card). Create demo profiles from the sidebar (or see `research\verify_pp1_v31_demo.py` for the profiles used in the demos).
The historical 3.0 application still starts exactly as before: omit `C4_GUIDANCE_CONTENT_SCHEMA` and use a 3.0 prepared-content folder and the 3.0 policy folder; it never reads 3.1 stores.

## 2. Tests and builds
```powershell
cd service
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp=.local\prepared-content\pytest-run
cd ..\demo-frontend
npm run lint; npx tsc -b; npm test; npm run build
```
(`--basetemp` must be inside the C4 folder because the content registry only accepts folders under it.)

## 3. Reproduce the 3.1 study
```powershell
cd service
$env:OPENBLAS_NUM_THREADS = "1"; $env:OMP_NUM_THREADS = "1"
$out = ".local\pp1-learning\v31-study-NEW"
# one process per seed, 4 encoder variants each, 5,000 observations (checkpoints at 0, 50, 200, 600, 2000, 5000)
foreach ($s in 11,23,37,51,71) { Start-Process -NoNewWindow .\.venv\Scripts\python.exe "-m app.studies.experiment31 train --output $out --seed $s --budget 5000" }
# dev-selected exploration scale (525 only)
foreach ($s in 11,23,37,51,71) { Start-Process -NoNewWindow .\.venv\Scripts\python.exe "-m app.studies.experiment31 train --output $out --seed $s --budget 5000 --exploration 0.25 --variants 525" }
# matched-assumption runs (525 only)
foreach ($a in "low_need","under_heavy","over_heavy","preference_led") { foreach ($s in 11,23,37) { Start-Process -NoNewWindow .\.venv\Scripts\python.exe "-m app.studies.experiment31 train --output $out --seed $s --budget 2000 --assumption $a --variants 525" } }
# after every process has finished: re-assess the saved checkpoints (adds the diagnostic, verifies determinism), then report, plots and replay
foreach ($f in Get-ChildItem $out\result-*.json) { $tag = $f.BaseName -replace "^result-",""; .\.venv\Scripts\python.exe -m app.studies.experiment31 reassess --output $out --tag $tag }
.\.venv\Scripts\python.exe -m app.studies.experiment31 report --output $out
.\.venv\Scripts\python.exe -m app.studies.experiment31 plots --output $out
.\.venv\Scripts\python.exe -m app.studies.experiment31 replay --output $out --run seed-23-x0.25-525
```
Runs are deterministic: the same seed reproduces the same numbers. The numbers in `docs\PP1-V31-RESULTS.md` came from `.local\pp1-learning\v31-study-20261022-a`; `research\v31_compatibility_dryrun.py` and `research\verify_pp1_v31_demo.py` produce the compatibility and demo records.
