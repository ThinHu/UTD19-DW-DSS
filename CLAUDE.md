# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Team split: OLAP model, KPI measures, slice/dice analytics dashboard and business questions belong to Ly — don't build them here. DW checks/testing after DW v1 belong to Hữu — changes are OK but must be reported to him.

Two Python packages in one repo (both at the repo root, not under `src/` despite what README.md says):

- **`utd19_dw`**: a DuckDB data warehouse over the UTD19 traffic dataset (Luzern, 2015-01-01 → 2015-06-30). It runs plain SQL files in stages.
- **`utd19_dss`** (DSS v5): a decision-support engine plus a FastAPI backend that ranks detectors by a congestion "Priority Score". It has a React/Vite dashboard in `frontend/`.

Docs, comments, config notes and UI strings are in Vietnamese. Keep that convention when editing.

## Commands

`make` targets exist, but `make` may not be installed on this Windows machine, so these are the direct commands:

```bash
pip install -e .[dev,dss]                 # setup (dss extra = numpy/sklearn/fastapi/uvicorn)

python -m utd19_dw.profiling              # source data quality survey
python -m utd19_dw.pipeline               # DW ETL → data/work/utd19.duckdb (auto: --full if data/raw/utd19_u.csv exists, else --from-export)
python -m utd19_dw.weather                # optional: Open-Meteo daily weather → data/raw/external/ (dw.dim_weather)
python -m utd19_dw.export                 # Parquet/CSV export → data/export/ (star/ = dims + 15-min fact for BI tools)

python -m utd19_dss.build                 # offline DSS build (~5 min) → data/dss/
python -m utd19_dss.evaluate              # DSS evaluation on June → reports/ (md, json, csv, png)
uvicorn utd19_dss.api:app --port 8000     # API + built dashboard at http://localhost:8000

cd frontend && npm install && npm run dev # dev UI on :5173, proxies /api → :8000
cd frontend && npm run build              # rebuilds frontend/dist (served by the API)

node docs/build_design_doc.js data/dss/meta.json docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx reports/dss_evaluation.json  # design doc

pytest tests/                             # all tests
pytest tests/test_dss.py::test_priority_renormalises_missing_criteria   # single test
```

`ruff` is in the dev extras, but there is no ruff config.

## DW pipeline (`utd19_dw`)

- `pipeline.run_pipeline()` has two modes producing the same star schema. **Full** (`--full`, raw `utd19_u.csv`): runs `sql/00_schema.sql`, then every `*.sql` in `10_staging`, `20_clean`, `30_dw`, `40_mart`, `50_checks`, **sorted by filename**. **Export** (`--from-export`, only `data/raw/luzern_jan_jun/detector_window_15min.csv.gz` present — the usual case on this machine): runs the explicit `EXPORT_STEPS` list, which mixes `sql/export_mode/*` with the shared dimension/mart files and skips everything that needs the 3-minute fact (`36_fact`, `40/41/42/44` marts). Each file runs inside `db.step()`, which writes a row (with the row count of the last table the file creates) to `etl.run_log`. Optional weather is loaded by Python (`load_weather`) into `stg.weather_daily` (empty table if the CSV is missing).
- Grain: `dw.fact_traffic_measurement` (3 min, full mode only) → `dw.fact_traffic_15min` (aggregate fact, additive measures: counts and sums; averages = sum/count). `mart.dss_detector_window` and the DQ snapshot `mart.detector_day_15min` read the 15-min fact, so downstream code doesn't care which mode loaded it.
- Calendar (`settings.yaml: calendar`) feeds `dim_date` via `{HOLIDAYS_IN}`/`{SPECIAL_DAYS_IN}`/`{DIM_DATE_START}`/`{DIM_DATE_END}`; keep it in sync with `dss.yaml: calendar`.
- Never create tables with bare `now()` (TIMESTAMPTZ breaks `.df()` without tzdata on Windows) — use `CAST(now() AS TIMESTAMP)`. In DuckDB `/` on integers is float division; use `//` for hour/slot buckets.
- SQL files are templates. `render_sql()` replaces `{CITY_IN}`, `{DATE_FILTER_SQL}`, `{FLOW_MAX}`, `{EXCLUDE_MASK}`, `{RAW_DATA_DIR}`, `{LIMIT_SQL}` and similar placeholders by plain string replacement, so other braces such as regex `{1,3}` are left alone. A new placeholder must be added to the `replacements` dict.
- Every SQL file is numbered (`NN_name.sql`); the number fixes run order inside its folder. `50_checks/50_reconciliation.sql` (full mode, RC-A…RC-H) and `export_mode/50_reconciliation.sql` (export mode) must all PASS; they check row conservation, FK orphans, fact grain uniqueness and dimension key uniqueness.
- Clean rule: values outside physical range (flow > FLOW_MAX, occupancy outside [0, 1], sentinels 99999 / 999.99) are set to NULL in the fact but keep their `dq_flag` bit; the occupancy scale (fraction vs percent) is inferred from non-error rows below 900 so sentinels can't flip it.
- Data quality is tracked as a bitmask. Each rule in `config/dq_rules.yaml` has a `bit_value`. Failing rows go to `etl.quarantine`. `settings.get_dq_mask(ids)` builds `{EXCLUDE_MASK}` from `data_warehouse.exclude_rules_in_mart` in `config/settings.yaml`. The ids listed there must match rule `id`s in `dq_rules.yaml`.
- `utd19_dw.db` opens a **module-level DuckDB connection** (`db = DBManager()`) to `data/work/utd19.duckdb` when imported. Importing `utd19_dw.pipeline`/`export`/`db`, including from tests, opens that file, and that can conflict with another process holding it.
- Paths and settings come from `config/settings.yaml`, which `.env` can override (`UTD_DATA_ROOT`, `UTD_WORK_DIR`, `UTD_EXPORT_DIR`, `UTD_SMOKE_ROWS`, `UTD_MEMORY_LIMIT`; see `.env.example`). Set `UTD_SMOKE_ROWS` to run on a small sample.

## DSS (`utd19_dss`)

All parameters are in `config/dss.yaml`, loaded as a plain dict by `utd19_dss.config.load_config()`. Paths in that file are relative to the repo root.

Data flow:
1. **Source** (`data.py`): reads `mart.dss_detector_window` (from `dw.fact_traffic_15min`) and detector attributes from `dw.dim_detector`. It opens the DW DuckDB **read-only** and closes it. If the DW is missing, it falls back to the CSVs in `data/raw/luzern_jan_jun/` (results are identical; `meta.profile.source` records which was used). Everything becomes a `Grid` of `[T, D]` arrays, where T = days × 96 slots and D = detectors.
2. **Build** (`build.py`, offline): K-means on days and on detectors, then a per-day-type baseline (`baseline.py`), criteria C1–C5 (`engine.py`), and DT / NB / MLP / Gradient Boosting models compared in `models.py` (best by PR-AUC on May; currently GB). C5 is the ML probability of an event within the next 30 minutes. Weights are tuned by grid search and thresholds are calibrated (`scoring.py`). The time split is fixed with no shuffling: train Jan–Apr, validate May (model, weight and threshold selection), then retrain on Jan–May and score June. Output goes to `data/dss/`: `meta.json`, `model.joblib`, `grid.joblib`, `baseline_final.npz`, `replay_batch.parquet`, etc.
3. **Live** (`live.py`, `LiveEngine`): loads the artifacts and "replays" June one 15-minute window at a time, seeing only past data. `POST /api/ingest` accepts a CSV of one window with the same columns as the mart. Both paths go through `_score_range`, which reuses `build._block`, so **build and live share the same computation core**. A change to criteria/feature logic must stay consistent across both. `tests/test_dss.py::test_live_matches_batch` checks that live scores match `replay_batch.parquet`. It is skipped if `data/dss/meta.json` doesn't exist.
4. **DW info** (`dwinfo.py`, `GET /api/dw/quality`): read-only view of `etl.*` tables, star schema columns and monthly coverage; opens the DW per request so the pipeline can rerun while the API is up.
5. **Goal seeking** (`scoring.threshold_curve` / `goal_seek`, `POST /api/goalseek`): uses `valid_scores.npz` (May) to find the High threshold meeting a precision, recall or capacity (alerts per window at p95) target, and checks it on replayed June windows.
6. **API** (`api.py`): a global `ENG` LiveEngine is created in the FastAPI lifespan, and a background `replay_loop` advances it while it is playing. Scored results and operator actions are stored in `data/work/dss_results.duckdb` (`store.py`). The API also serves `frontend/dist` (SPA fallback route). The API exits immediately if `python -m utd19_dss.build` hasn't been run.

Leakage guard: `build` makes two grids — `gridV` (`build_grid(..., hist_end=<first validation day>)`) for the validation phase (tiers, detector K-means, neighbour matrix, static features use Jan–Apr only) and `grid` (history to May) for the final phase. Keep that split when adding history-derived quantities.

Scoring semantics (`scoring.py`): `priority()` drops missing criteria (NaN) and renormalises the remaining weights. C1 and C2 are mandatory, and the score is NaN without them. The level labels are Vietnamese strings (`"Cao"`, `"Trung bình"`, `"Thấp"`, `"Không đủ dữ liệu"`) used as values throughout the API and frontend. Detector data-quality tiers are A/B/C/X; X (stuck or offline) is never scored and means maintenance is needed. Thresholds are not hand-set: `build` picks High = max-F1 and Medium = max-F2 threshold on the May validation set (`scoring.threshold_sweep` / `select_thresholds`, rule in `dss.yaml: scoring.threshold_rule`) and writes them to `meta.json`. `certainty` shown in the UI is the isotonic P(needs attention | score) curve fitted on May — distinct from `confidence`, which is data quality. Capacity: `thresholds` may carry `max_high` (from `dss.yaml: scoring.max_high_per_window`); `level()` then keeps only the top-N scores per window as `"Cao"` and demotes the rest to `"Trung bình"` (`overflow()`, action code `QUEUE`). So `level()` must be called on a whole window row (`[D]` or `[T, D]`), never on a single detector's score; when passing a partial thresholds dict, merge it with the current one so `max_high` isn't lost.

## Frontend

React 18 + Vite + Recharts + react-leaflet. Pages are in `frontend/src/pages/` (`Warehouse.jsx` = DW load/reconciliation/metadata view; `ModelPage.jsx` tab `dm` = decision model / architecture; goal seeking lives in `WhatIf.jsx`) and API calls in `frontend/src/api.js`. `frontend/dist` is committed: run `npm run build` after UI changes, because the Python API serves only the built output.

## Evaluation (`evaluate.py`)

Reads `data/dss/meta.json`, `replay_batch.parquet` and `valid_scores.npz` (all written by `build`). Strategies other than the deployed one get thresholds re-selected on May with the same F1/F2 rule, then everything is measured on June. Outputs go to `reports/`. Regenerate after every `build`.

## DW notes

- dq_flag bits in `sql/20_clean/22_clean_measurements.sql` must match `bit_value` in `config/dq_rules.yaml`; `tests/test_config.py::test_sql_dq_bits_match_rules` checks this.
- Rows with unparsable keys, interval outside [0, 86400) (when `interval_oor_mode: reject`) and duplicate keys go to `etl.quarantine`, so reconciliation RC-A (fact = staging − quarantine) holds.
- Luzern measures every 180 s: `dim_city.interval_length_s` and `dim_time_of_day` use 180 s steps.
- `tests/test_pipeline_smoke.py` runs the whole SQL pipeline on synthetic data in a temp dir via a subprocess.
