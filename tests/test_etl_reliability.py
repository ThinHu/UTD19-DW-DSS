"""Kiểm tra rollback, lịch sử, đổi chế độ và các dữ liệu lỗi có chủ đích."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd
from test_pipeline_smoke import _make_raw

ROOT = Path(__file__).resolve().parent.parent


def _run(tmp_path, code):
    env = {**os.environ, "UTD_DATA_ROOT": str(tmp_path / "raw"),
           "UTD_WORK_DIR": str(tmp_path / "work"), "UTD_SMOKE_ROWS": "",
           "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", textwrap.dedent(code)],
                            check=False, cwd=ROOT, env=env, capture_output=True, text=True,
                            encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-6000:]


def test_rollback_history_and_mode_switch(tmp_path):
    _make_raw(tmp_path / "raw")
    _run(tmp_path, """
        import shutil
        from utd19_dw import pipeline as p
        from utd19_dw.db import db
        from utd19_dw.config import settings
        assert db._con is None  # import không giữ khóa DW
        first = p.run_pipeline(False)
        # Kỳ vọng độc lập: flow của D1 ở slot đầu là 300,999,336,354,372.
        row = db.execute("SELECT n_intervals,n_flow,sum_flow_all FROM dw.fact_traffic_15min f JOIN dw.dim_detector d USING(detector_key) WHERE d.detid='D1' AND date_key=20150105 AND slot_key=0").fetchone()
        assert row == (5,5,2361.0)
        # D2: flow vượt ngưỡng thành NULL; occupancy lỗi không đóng góp vào count.
        row = db.execute("SELECT n_err,n_flow,n_occ,n_flow_clean,n_occ_clean,sum_flow_clean FROM dw.fact_traffic_15min f JOIN dw.dim_detector d USING(detector_key) WHERE d.detid='D2' AND date_key=20150105 AND slot_key=0").fetchone()
        assert row == (1,4,4,4,3,1190.0)
        snapshot = db.execute("SELECT count(*), sum(flow_veh_h_lane) FROM dw.fact_traffic_measurement").fetchall()
        loaded = db.execute("SELECT loaded_at FROM etl.load_info").fetchone()
        original = p.run_sql_file
        def corrupt_checks(rel):
            original(rel)
            if rel == '60_validation/61_full.sql':
                db.execute("UPDATE etl.validation_results SET status='FAIL', actual=1 WHERE check_id='DQ-ROLLUP'")
        p.run_sql_file = corrupt_checks
        try:
            p.run_pipeline(False)
        except RuntimeError as exc:
            assert 'DQ-ROLLUP' in str(exc)
        else:
            raise AssertionError('Pipeline phải báo lỗi khi check FAIL')
        assert db.execute("SELECT count(*), sum(flow_veh_h_lane) FROM dw.fact_traffic_measurement").fetchall() == snapshot
        assert db.execute("SELECT loaded_at FROM etl.load_info").fetchone() == loaded
        assert db.execute("SELECT count(*) FROM etl.check_history WHERE status='FAIL'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM etl.validation_results WHERE status='FAIL'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM etl.runs WHERE status='FAILED'").fetchone()[0] == 1
        p.run_sql_file = original
        second = p.run_pipeline(False)
        assert first != second
        assert db.execute("SELECT count(*), sum(flow_veh_h_lane) FROM dw.fact_traffic_measurement").fetchall() == snapshot
        assert db.execute("SELECT count(DISTINCT run_id) FROM etl.run_log").fetchone()[0] == 3
        exp = settings.EXPORT_SRC_DIR
        exp.mkdir()
        db.query("SELECT * FROM mart.dss_detector_window").to_csv(exp / 'detector_window_15min.csv.gz', index=False)
        shutil.copy(settings.RAW_DATA_DIR / 'detectors_luzern.csv', exp / 'detector_location_profile.csv')
        p.run_pipeline(True)
        assert db.count('dw.fact_traffic_measurement') is None
        assert db.count('mart.congestion_kpi') is None
        assert db.count('dw.v_traffic_15min') == 384
        assert db.execute("SELECT count(*) FROM etl.v_quality_checks WHERE status <> 'PASS'").fetchone()[0] == 0
        # Chuyển lại full sau khi đã tạo view/index phải hoạt động.
        p.run_pipeline(False)
        assert db.count('dw.fact_traffic_measurement') == 1920
        db.close()
        from utd19_dw.validate import validate_database
        report = validate_database()
        assert report['status'] == 'PASS'
        assert report['row_counts']['dw.fact_traffic_measurement'] == 1920
    """)


def test_raw_invalid_keys_alignment_and_nonfinite(tmp_path):
    raw = tmp_path / "raw"
    _make_raw(raw)
    path = raw / "utd19_u.csv"
    # Append chuỗi nguyên bản để NaN/Inf không bị pandas chuyển thành ô rỗng.
    with path.open("a", encoding="utf-8") as stream:
        stream.write('luzern,invalid,0,D1,100,0.1,0,\n')
        stream.write('luzern,2015-01-05,1,D1,100,0.1,0,\n')
        stream.write('luzern,2015-01-05,720,D1,NaN,Infinity,0,\n')
    _run(tmp_path, """
        from utd19_dw.pipeline import run_pipeline
        from utd19_dw.db import db
        run_pipeline(False)
        rules = dict(db.execute("SELECT rule_id,count(*) FROM etl.quarantine GROUP BY 1").fetchall())
        assert rules['RULE_PARSE'] == 1
        assert rules['RULE_INTERVAL_ALIGNMENT'] == 1
        row = db.execute("SELECT flow_veh_h_lane, occupancy, dq_flag FROM dw.fact_traffic_measurement f JOIN dw.dim_detector d USING(detector_key) WHERE d.detid='D1' AND date_key=20150105 AND time_key=720").fetchone()
        assert row[0] is None and row[1] is None and row[2] & 64
        db.close()
    """)


def test_export_rejects_invalid_aggregates_and_filters_dates(tmp_path):
    raw = tmp_path / 'raw'
    exp = raw / 'luzern_jan_jun'
    exp.mkdir(parents=True)
    columns = ['detid','day','slot','n','n_err','n_occ','n_flow','n_flow0',
               'n_occ_clean','n_flow_clean','mean_occ_all','mean_flow_all','mean_occ_clean','mean_flow_clean']
    good = ['D1','2015-01-05',0,5,0,5,5,0,5,5,0.1,400,0.1,400]
    rows = [good]
    for index, value in [(3,-1),(4,6),(5,6),(7,6),(10,1.1),(11,float('inf')),(8,6),(2,1.5),(6,None)]:
        row = good.copy()
        row[2] = len(rows)
        row[index] = value
        rows.append(row)
    outside = good.copy()
    outside[1] = '2016-01-01'
    rows.append(outside)
    pd.DataFrame(rows, columns=columns).to_csv(exp / 'detector_window_15min.csv.gz', index=False)
    pd.DataFrame({'detid':['D1'], 'long':[8.3], 'lat':[47.05]}).to_csv(exp / 'detector_location_profile.csv', index=False)
    _run(tmp_path, """
        from utd19_dw.pipeline import run_pipeline
        from utd19_dw.db import db
        run_pipeline(True)
        assert db.count('dw.fact_traffic_15min') == 1
        assert db.count('stg.window_15min_raw') == 10
        assert db.count('etl.quarantine') == 9
        assert db.execute("SELECT count(*) FROM etl.quarantine WHERE rule_id='RULE_AGGREGATE_INVALID'").fetchone()[0] == 8
        db.close()
    """)


def test_rollup_check_detects_wrong_sum(tmp_path):
    _make_raw(tmp_path / 'raw')
    _run(tmp_path, """
        from utd19_dw.pipeline import run_pipeline, run_sql_file, assert_checks
        from utd19_dw.db import db
        run_pipeline(False)
        db.execute("UPDATE dw.fact_traffic_15min SET sum_flow_all=sum_flow_all+10 WHERE detector_key=1 AND date_key=20150105 AND slot_key=0")
        run_sql_file('60_validation/60_common.sql')
        run_sql_file('60_validation/61_full.sql')
        checks = dict(db.execute("SELECT check_id,status FROM etl.validation_results").fetchall())
        assert checks['DQ-ROLLUP'] == 'FAIL'
        assert checks['DQ-MART-VALUES'] == 'FAIL'
        try:
            assert_checks()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Sai tổng phải bị phát hiện')
        db.close()
        from utd19_dw.validate import validate_database
        assert validate_database()['status'] == 'FAIL'
    """)


def test_rollover_percent_scale_inferred_detector_and_sql_failure(tmp_path):
    raw = tmp_path / 'raw'
    _make_raw(raw)
    path = raw / 'utd19_u.csv'
    frame = pd.read_csv(path)
    frame['occ'] = 5.0
    frame.to_csv(path, index=False)
    with path.open('a', encoding='utf-8') as stream:
        stream.write('luzern,2015-01-05,86400,INFERRED,100,5,0,\n')
        stream.write('luzern,2015-01-05,900,D1,99999,999.99,1,\n')
    _run(tmp_path, """
        from utd19_dw import pipeline as p
        from utd19_dw.config import settings
        from utd19_dw.db import db
        settings.INTERVAL_OOR_MODE = 'rollover'
        p.run_pipeline(False)
        row = db.execute("SELECT f.date_key,f.time_key,d.is_inferred,round(f.occupancy,3) FROM dw.fact_traffic_measurement f JOIN dw.dim_detector d USING(detector_key) WHERE d.detid='INFERRED'").fetchone()
        assert row[:3] == (20150106,0,True) and abs(row[3]-0.05)<1e-7
        row = db.execute("SELECT flow_veh_h_lane,occupancy,dq_flag FROM dw.fact_traffic_measurement f JOIN dw.dim_detector d USING(detector_key) WHERE d.detid='D1' AND date_key=20150105 AND time_key=900").fetchone()
        assert row[0] is None and row[1] is None and row[2] & 20 == 20
        assert db.execute("SELECT occupancy_scale FROM clean.city_params").fetchone()[0]=='percent'
        before = db.execute("SELECT count(*) FROM dw.fact_traffic_measurement").fetchone()
        original = p.run_sql_file
        def fail_sql(rel):
            if rel=='30_dw/36_fact_traffic_measurement.sql':
                with db.step('injected_sql_failure'):
                    db.execute('SELECT * FROM nonexistent_table_for_test')
            original(rel)
        p.run_sql_file=fail_sql
        try:
            p.run_pipeline(False)
        except Exception as exc:
            assert 'nonexistent_table_for_test' in str(exc)
        else:
            raise AssertionError('Lỗi SQL phải làm pipeline thất bại')
        assert db.execute("SELECT count(*) FROM dw.fact_traffic_measurement").fetchone()==before
        assert db.execute("SELECT count(*) FROM etl.run_log WHERE step='injected_sql_failure' AND status='FAILED'").fetchone()[0]==1
        db.close()
    """)
