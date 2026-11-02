"""Chạy trọn pipeline DW (staging → clean → dw → mart → checks) trên dữ liệu giả lập nhỏ.

Chạy trong tiến trình con với UTD_* trỏ vào thư mục tạm, để không đụng data/work/utd19.duckdb thật
(utd19_dw.db mở kết nối DuckDB ngay khi import).
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _make_raw(raw: Path):
    raw.mkdir(parents=True)
    rows = []
    for day in ["2015-01-05", "2015-01-06"]:
        for det in ["D1", "D2"]:
            for t in range(0, 86400, 180):
                rows.append(("luzern", day, t, det, 300.0 + (t % 900) / 10, 0.05, 0, None))
    rows.append(("luzern", "2015-01-05", 180, "D1", 999.0, 0.05, 0, None))     # trùng khóa → quarantine
    rows.append(("luzern", "2015-01-05", 86400, "D1", 100.0, 0.05, 0, None))   # interval ngoài ngày → quarantine
    # Hai dòng sửa lại số đo đã có (nạp sau → được giữ, bản cũ vào quarantine), mang lỗi để kiểm tra cờ DQ
    rows.append(("luzern", "2015-01-05", 360, "D2", 5000.0, 0.05, 1, None))    # flow > FLOW_MAX → cờ RULE_FLOW_MAX
    rows.append(("luzern", "2015-01-05", 540, "D2", 200.0, 1.7, 0, None))      # occ > 1 → cờ RULE_OCC_OOR
    rows.append(("hamburg", "2015-01-05", 0, "H1", 100.0, 0.1, 0, None))       # thành phố khác → bị lọc ở staging
    pd.DataFrame(rows, columns=["city", "day", "interval", "detid", "flow", "occ", "error", "speed"]).to_csv(raw / "utd19_u.csv", index=False)
    pd.DataFrame({"detid": ["D1", "D2"], "citycode": "luzern", "long": [8.30, 8.31], "lat": [47.05, 47.06],
                  "lanes": [1, 2], "length": [0.1, 0.2], "pos": [0.05, 0.1], "fclass": "primary", "road": ["A", "B"],
                  "limit": [50, 50], "linkid": [1, 2]}).to_csv(raw / "detectors_luzern.csv", index=False)
    pd.DataFrame({"linkid": [1, 1, 2, 2], "order": [1, 2, 1, 2], "piece": 1, "group": 1, "citycode": "luzern",
                  "long": [8.30, 8.301, 8.31, 8.311], "lat": [47.05, 47.051, 47.06, 47.061]}).to_csv(raw / "links_luzern.csv", index=False)
    (raw / "external").mkdir()
    pd.DataFrame({"date": ["2015-01-05", "2015-01-06"], "temperature_2m_mean": [-2.0, 3.5], "precipitation_sum": [0.0, 12.0],
                  "snowfall_sum": [0.0, 0.0], "precipitation_hours": [0, 9]}).to_csv(raw / "external" / "weather_luzern_daily.csv", index=False)


def test_pipeline_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    _make_raw(raw)
    env = {**os.environ, "UTD_DATA_ROOT": str(raw), "UTD_WORK_DIR": str(tmp_path / "work"),
           "UTD_EXPORT_DIR": str(tmp_path / "export"), "UTD_SMOKE_ROWS": "", "PYTHONIOENCODING": "utf-8"}
    code = textwrap.dedent("""
        from utd19_dw.pipeline import run_pipeline
        from utd19_dw.db import db
        run_pipeline()
        q = lambda s: db.con.execute(s).fetchall()
        print("RECON", q("SELECT check_id, status FROM etl.reconciliation ORDER BY 1"))
        print("QUAR", q("SELECT rule_id, count(*) FROM etl.quarantine GROUP BY 1 ORDER BY 1"))
        print("FACT", q("SELECT count(*), sum(CASE WHEN dq_flag & 4 > 0 THEN 1 ELSE 0 END), sum(CASE WHEN dq_flag & 16 > 0 THEN 1 ELSE 0 END) FROM dw.fact_traffic_measurement"))
        print("OOR", q("SELECT count(*) FROM dw.fact_traffic_measurement WHERE dq_flag & 20 > 0 AND (flow_veh_h_lane > 3500 OR occupancy > 1)"))
        print("TIME_ORPHAN", q("SELECT count(*) FROM dw.fact_traffic_measurement f ANTI JOIN dw.dim_time_of_day t USING (time_key)"))
        print("COVER", q("SELECT min(coverage_ratio), max(coverage_ratio) FROM mart.detector_day_coverage"))
        print("MFD_COLS", [c[0] for c in db.con.execute("SELECT * FROM mart.mfd_city_interval LIMIT 0").description])
        print("DSS", q("SELECT count(*), max(n), min(slot), max(slot) FROM mart.dss_detector_window"))
        print("KPI", q("SELECT count(*), max(hour_of_day) FROM mart.congestion_kpi"))
        print("F15", q("SELECT count(*), sum(n_intervals) FROM dw.fact_traffic_15min"))
        print("WEATHER", q("SELECT weather_class FROM dw.dim_weather WHERE date_key IN (20150105, 20150106) ORDER BY date_key"))
        print("HOLIDAY", q("SELECT day_type, is_public_holiday FROM dw.dim_date WHERE date_key = 20150101"))
        print("LINKLEN", q("SELECT round(min(geometry_length_km), 3) FROM dw.dim_link WHERE link_key > 0"))
        print("SNAP", q("SELECT count(*), sum(n_windows) FROM mart.detector_day_15min"))
        print("META", q("SELECT count(*) FROM etl.metadata_catalog WHERE object_name = 'dw.fact_traffic_15min'"))
    """)
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-3000:]
    out = {l.split(" ", 1)[0]: l.split(" ", 1)[1] for l in r.stdout.splitlines() if l.split(" ", 1)[0].isupper() and " " in l}
    assert out["RECON"] == "[('RC-A', 'PASS'), ('RC-B', 'PASS'), ('RC-C', 'PASS'), ('RC-D', 'PASS'), ('RC-E', 'PASS'), ('RC-F', 'PASS'), ('RC-G', 'PASS'), ('RC-H', 'PASS')]"
    assert out["QUAR"] == "[('RULE_DUPLICATE', 3), ('RULE_INTERVAL_OOR', 1)]"
    assert out["FACT"] == "[(1920, 1, 1)]"
    assert out["OOR"] == "[(0,)]"                     # giá trị vượt ngưỡng bị đặt NULL, chỉ còn cờ            # 2 ngày × 2 detector × 480 khoảng đo
    assert out["TIME_ORPHAN"] == "[(0,)]"
    assert out["COVER"] == "[(1.0, 1.0)]"
    assert "flow_w" in out["MFD_COLS"] and "occ_w" in out["MFD_COLS"]
    assert out["DSS"] == "[(384, 5, 0, 95)]"         # 2 × 2 × 96 khung 15 phút, mỗi khung 5 khoảng đo
    assert out["KPI"] == "[(48, 23)]"                # 2 ngày × 24 giờ; trước khi sửa / → // sẽ ra 50 dòng và giờ 24
    assert out["F15"] == "[(384, 1920)]"             # fact tổng hợp khớp fact gốc
    assert out["WEATHER"] == "[('Khô',), ('Mưa to',)]"
    assert out["HOLIDAY"] == "[('SUN', True)]"       # 01/01 là ngày lễ → loại ngày như Chủ nhật
    assert out["LINKLEN"] != "[(0.5,)]" and out["LINKLEN"] != "[(None,)]"   # độ dài thật, không gán cứng
    assert out["META"] == "[(1,)]"
    assert out["SNAP"] == "[(4, 384)]"               # 2 detector × 2 ngày, đủ 96 khung mỗi ngày


def test_pipeline_from_export(tmp_path):
    """Chế độ nạp từ bản xuất 15 phút: dựng cùng lược đồ sao, mart DSS và đối soát."""
    raw = tmp_path / "raw"
    exp = raw / "luzern_jan_jun"
    exp.mkdir(parents=True)
    rows = []
    for day in ["2015-01-05", "2015-01-06"]:
        for det in ["D1", "D2"]:
            for s in range(96):
                rows.append((det, day, s, 5, 1, 5, 5, 0, 4, 4, 0.1, 400.0, 0.1, 410.0))
    rows.append(("D1", "2015-01-05", 96, 1, 0, 1, 1, 0, 1, 1, 0.1, 400.0, 0.1, 400.0))     # slot 96 → cách ly
    rows.append(("D1", "2015-01-05", 3, 5, 0, 5, 5, 0, 5, 5, 0.2, 500.0, 0.2, 500.0))      # trùng → giữ dòng sau
    pd.DataFrame(rows, columns=["detid", "day", "slot", "n", "n_err", "n_occ", "n_flow", "n_flow0", "n_occ_clean",
                                "n_flow_clean", "mean_occ_all", "mean_flow_all", "mean_occ_clean", "mean_flow_clean"]
                 ).to_csv(exp / "detector_window_15min.csv.gz", index=False)
    pd.DataFrame({"detid": ["D1", "D2"], "long": [8.30, 8.31], "lat": [47.05, 47.06], "road": ["A", None],
                  "fclass": ["primary", "tertiary"], "linkid": ["1.0", "2.0"], "pos": [0.1, 0.2], "limit": [50, 0]}
                 ).to_csv(exp / "detector_location_profile.csv", index=False)
    env = {**os.environ, "UTD_DATA_ROOT": str(raw), "UTD_WORK_DIR": str(tmp_path / "work"),
           "UTD_EXPORT_DIR": str(tmp_path / "export"), "UTD_SMOKE_ROWS": "", "PYTHONIOENCODING": "utf-8"}
    code = textwrap.dedent("""
        from utd19_dw.pipeline import run_pipeline
        from utd19_dw.db import db
        run_pipeline()
        q = lambda s: db.con.execute(s).fetchall()
        print("MODE", q("SELECT mode FROM etl.load_info"))
        print("RECON", q("SELECT check_id, status FROM etl.reconciliation ORDER BY 1"))
        print("QUAR", q("SELECT rule_id, count(*) FROM etl.quarantine GROUP BY 1 ORDER BY 1"))
        print("DSS", q("SELECT count(*), round(max(mean_occ_clean), 3) FROM mart.dss_detector_window"))
        print("GROUP", q("SELECT road_group FROM dw.dim_detector JOIN dw.dim_road_class USING (road_class_key) WHERE detid = 'D2'"))
    """)
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-3000:]
    out = {l.split(" ", 1)[0]: l.split(" ", 1)[1] for l in r.stdout.splitlines() if l.split(" ", 1)[0].isupper() and " " in l}
    assert out["MODE"] == "[('export_15min',)]"
    assert out["RECON"] == "[('RC-A', 'PASS'), ('RC-B', 'PASS'), ('RC-C', 'PASS'), ('RC-D', 'PASS'), ('RC-E', 'PASS'), ('RC-G', 'PASS'), ('RC-H', 'PASS')]"
    assert out["QUAR"] == "[('RULE_DUPLICATE', 1), ('RULE_INTERVAL_OOR', 1)]"
    assert out["DSS"] == "[(384, 0.2)]"
    assert out["GROUP"] == "[('Đường gom',)]"
