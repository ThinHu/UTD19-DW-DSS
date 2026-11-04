"""Kỳ vọng DQ độc lập và phát hiện các DW hỏng có chủ đích."""
import pytest
from test_etl_reliability import _run
from test_pipeline_smoke import _make_raw

from utd19_dw.assess import percent, percentile, results_match


def test_statistics_and_float_comparison():
    assert percentile([1, 2, 3, 4, 5], .95) == pytest.approx(4.8)
    assert percent(1, 4) == 25
    assert percent(0, 0) is None
    assert results_match([(1, None, 0.1)], [(1, None, 0.1 + 1e-12)])
    assert not results_match([(1, 1.0)], [(1, 2.0)])
    assert not results_match([(1,)], [(1,), (2,)])


def test_profile_and_benchmark_known_fixture(tmp_path):
    _make_raw(tmp_path / 'raw')
    _run(tmp_path, """
        from utd19_dw.pipeline import run_pipeline
        from utd19_dw.assess import assess_database, markdown_report
        run_pipeline(False)
        report = assess_database(repeats=3)
        assert report['status'] == 'PASS'
        quality = report['quality']
        s = quality['summary']
        assert quality['staged_rows'] == 1924
        assert quality['rejected_rows'] == 4
        assert s['intervals'] == 1920
        assert s['error_intervals'] == 1
        assert s['flow_present'] == s['occupancy_present'] == 1919
        assert s['valid_windows'] == s['windows'] == 384
        assert s['calendar_days'] == 181
        assert s['observed_detectors'] == 2
        assert s['expected_intervals_observed_roster'] == 173760
        assert s['sensor_error_pct'] == 0.0521
        assert s['flow_missing_pct'] == 0.0521
        assert report['daily_rollup_comparison']['differences'] == 0
        assert len(report['benchmarks']) == 8
        assert report['rewrite_same_results']
        assert report['index_experiment']['same_results']
        assert all(len(b['samples_ms']) == 3 for b in report['benchmarks'])
        assert all(b['median_ms'] > 0 and b['explain_analyze'] for b in report['benchmarks'])
        assert 'Data Quality' in markdown_report(report)
        from utd19_dw.validate import validate_database
        # Hàm đánh giá không ghi lại kết quả kiểm tra vào DW.
        assert validate_database()['status'] == 'PASS'
    """)


def test_source_reconciliation_detects_consistent_downstream_corruption(tmp_path):
    _make_raw(tmp_path / 'raw')
    _run(tmp_path, """
        from utd19_dw import pipeline as p
        from utd19_dw.db import db
        from utd19_dw.validate import validate_database
        p.run_pipeline(False)
        # Sửa fact gốc rồi dựng lại aggregate/mart: checks downstream cũ vẫn PASS.
        db.execute("UPDATE dw.fact_traffic_measurement SET flow_veh_h_lane=flow_veh_h_lane+10 WHERE detector_key=1 AND date_key=20150105 AND time_key=0")
        for script in ['30_dw/38_fact_traffic_15min.sql','40_mart/43_dss_detector_window.sql']:
            p.run_sql_file(script)
        db.close()
        checks = {c['check_id']:c for c in validate_database()['checks']}
        assert checks['DQ-ROLLUP']['status'] == 'PASS'
        assert checks['DQ-MART-VALUES']['status'] == 'PASS'
        assert checks['DQ-SOURCE']['status'] == 'FAIL'
        assert checks['DQ-SOURCE']['actual'] == 1
    """)


def test_reconciliation_detects_orphan_duplicate_and_null_dimension_key(tmp_path):
    _make_raw(tmp_path / 'raw')
    _run(tmp_path, """
        from utd19_dw.pipeline import run_pipeline
        from utd19_dw.db import db
        from utd19_dw.validate import validate_database
        run_pipeline(False)
        db.execute("INSERT INTO dw.fact_traffic_15min SELECT * FROM dw.fact_traffic_15min LIMIT 1")
        db.close()
        checks = {c['check_id']:c for c in validate_database()['checks']}
        assert checks['RC-G']['status'] == 'FAIL'
        db.execute("DELETE FROM dw.fact_traffic_15min WHERE detector_key=1 AND date_key=20150105 AND slot_key=0")
        # Xóa cả bản trùng; tập khóa thiếu vẫn được rollup phát hiện.
        db.execute("UPDATE dw.fact_traffic_15min SET detector_key=999999 WHERE detector_key=2 AND date_key=20150105 AND slot_key=0")
        db.execute("DROP INDEX dw.idx_date_key")
        db.execute("INSERT INTO dw.dim_date SELECT * REPLACE(NULL AS date_key) FROM dw.dim_date WHERE date_key=20150101")
        db.close()
        report = validate_database()
        checks = {c['check_id']:c for c in report['checks']}
        assert checks['DQ-FK15']['status'] == 'FAIL'
        assert checks['DQ-DIM-KEYS']['status'] == 'FAIL'
        assert checks['DQ-ROLLUP']['status'] == 'FAIL'
    """)
