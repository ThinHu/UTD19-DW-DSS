import logging
import re
import uuid

from utd19_dw.config import BASE_DIR, settings
from utd19_dw.db import db

SQL_DIR = BASE_DIR / "sql"

def _sql_text(value):
    return str(value).replace("'", "''")


def _date_list(days) -> str:
    """Danh sách ngày cho mệnh đề IN; rỗng thì trả về NULL để IN (NULL) luôn sai."""
    return ", ".join(f"DATE '{d}'" for d in days) if days else "NULL"


def render_sql(sql_content: str) -> str:
    """Thay thế các biến động vào mẫu SQL một cách an toàn."""
    city_in = ", ".join(f"'{_sql_text(c)}'" for c in settings.CITIES)
    limit_sql = f"LIMIT {settings.SMOKE_ROWS}" if settings.SMOKE_ROWS else ""
    exclude_mask = settings.get_dq_mask(settings.EXCLUDE_RULES_IN_MART)
    
    date_filter_sql = ""
    if settings.START_DATE and settings.END_DATE:
        date_filter_sql = f"AND TRY_CAST(day AS DATE) >= DATE '{settings.START_DATE}' AND TRY_CAST(day AS DATE) <= DATE '{settings.END_DATE}'"
    elif settings.START_DATE:
        date_filter_sql = f"AND TRY_CAST(day AS DATE) >= DATE '{settings.START_DATE}'"
    elif settings.END_DATE:
        date_filter_sql = f"AND TRY_CAST(day AS DATE) <= DATE '{settings.END_DATE}'"

    replacements = {
        "CITY_IN": city_in,
        "LIMIT_SQL": limit_sql,
        "DATE_FILTER_SQL": date_filter_sql,
        "START_DATE": str(settings.START_DATE or ""),
        "END_DATE": str(settings.END_DATE or ""),
        "FLOW_MAX": str(settings.FLOW_MAX),
        "COVERAGE_MIN": str(settings.COVERAGE_MIN),
        "INTERVAL_OOR_MODE": f"'{settings.INTERVAL_OOR_MODE}'",
        "EXCLUDE_MASK": str(exclude_mask),
        "DATA_RAW_DIR": _sql_text(settings.RAW_DATA_DIR.as_posix()),
        "RAW_DATA_DIR": _sql_text(settings.RAW_DATA_DIR.as_posix()),  # Alias dự phòng
        "OCC_PERCENT_THRESHOLD": str(getattr(settings, "OCC_PERCENT_THRESHOLD", 1.5)),
        "HOLIDAYS_IN": _date_list(settings.HOLIDAYS),
        "SPECIAL_DAYS_IN": _date_list(settings.SPECIAL_DAYS),
        "DIM_DATE_START": str(settings.START_DATE or "2015-01-01"),
        "DIM_DATE_END": str(settings.DIM_DATE_END or settings.END_DATE or "2015-12-31"),
        "EXPORT_SRC_DIR": _sql_text(settings.EXPORT_SRC_DIR.as_posix()),
    }
    
    rendered = sql_content
    for key, val in replacements.items():
        rendered = rendered.replace(f"{{{key}}}", val)
    return rendered

def run_sql_file(rel: str):
    path = SQL_DIR / rel
    with open(path, "r", encoding="utf-8") as f:
        sql = render_sql(f.read())
    # Bảng chính của bước = bảng cuối cùng được tạo trong tệp → ghi số dòng vào etl.run_log
    made = re.findall(r"CREATE\s+OR\s+REPLACE\s+TABLE\s+([a-z_]+\.[a-z_0-9]+)\s+AS", sql, flags=re.IGNORECASE)
    with db.step(rel.replace(".sql", ""), table=made[-1] if made else None):
        db.execute(sql)


def run_sql_directory(dir_name: str):
    target_dir = SQL_DIR / dir_name
    if not target_dir.exists():
        return
    for sql_file in sorted(target_dir.glob("*.sql")):
        run_sql_file(f"{dir_name}/{sql_file.name}")


def load_weather():
    """Nạp thời tiết ngày (nguồn ngoài, tùy chọn) vào stg.weather_daily; không có tệp thì tạo bảng rỗng."""
    path = settings.WEATHER_CSV
    with db.step("10_staging/weather_daily", table="stg.weather_daily",
                 note=str(path) if path.exists() else "không có tệp thời tiết (bỏ qua)"):
        if path.exists():
            db.execute(f"CREATE OR REPLACE TABLE stg.weather_daily AS "
                       f"SELECT * FROM read_csv('{_sql_text(path.as_posix())}', header=true, all_varchar=true)")
        else:
            db.execute("CREATE OR REPLACE TABLE stg.weather_daily (\"date\" VARCHAR, temperature_2m_mean VARCHAR, "
                       "precipitation_sum VARCHAR, snowfall_sum VARCHAR, precipitation_hours VARCHAR)")


def record_load(mode: str, source: str):
    db.execute("CREATE OR REPLACE TABLE etl.load_info AS SELECT ? AS mode, ? AS source, "
               "? AS date_start, ? AS date_end, CAST(now() AS TIMESTAMP) AS loaded_at",
               [mode, source, str(settings.START_DATE), str(settings.END_DATE)])


# Chế độ nạp từ bản xuất 15 phút: dùng lại mọi SQL chiều/mart không phụ thuộc fact 3 phút.
EXPORT_STEPS = [
    "export_mode/10_stg_export.sql",
    "@weather",
    "20_clean/20_clean_detectors.sql",
    "20_clean/21_clean_links.sql",
    "export_mode/22_clean_window.sql",
    "30_dw/30_dim_city.sql",
    "30_dw/31_dim_road_class.sql",
    "30_dw/32_dim_link.sql",
    "30_dw/33_dim_detector.sql",
    "30_dw/34_dim_date.sql",
    "30_dw/35_dim_time_of_day.sql",
    "30_dw/37_dim_time_slot.sql",
    "export_mode/38_fact_traffic_15min.sql",
    "30_dw/39_dim_weather.sql",
    "40_mart/43_dss_detector_window.sql",
    "40_mart/45_detector_day_15min.sql",
    "export_mode/50_reconciliation.sql",
    "50_checks/51_metadata_catalog.sql",
]


def assert_checks():
    """Không chấp nhận bảng kiểm rỗng hoặc bất kỳ kết quả khác PASS."""
    for table in ("etl.reconciliation", "etl.validation_results"):
        rows = db.execute(f"SELECT check_id, status FROM {table}").fetchall()
        failed = [check for check, status in rows if status != "PASS"]
        if not rows or failed:
            raise RuntimeError(f"Kiểm tra DW thất bại: {table}: {failed or 'không có kết quả'}")


def run_pipeline(from_export: bool | None = None):
    """Thay toàn bộ dữ liệu trong một transaction; lịch sử chạy lưu ngoài transaction."""
    settings.validate()
    raw = settings.RAW_DATA_DIR / "utd19_u.csv"
    if from_export is None:
        from_export = not raw.exists()
    src = settings.EXPORT_SRC_DIR / "detector_window_15min.csv.gz" if from_export else raw
    required = [src]
    if from_export:
        if settings.CITIES != ["luzern"]:
            raise ValueError("Bản xuất hiện tại chỉ hỗ trợ thành phố luzern")
        required.append(settings.EXPORT_SRC_DIR / "detector_location_profile.csv")
    else:
        for pattern in ("*detector*.csv", "*link*.csv"):
            if not list(settings.RAW_DATA_DIR.glob(pattern)):
                raise FileNotFoundError(f"Thiếu nguồn {pattern} trong {settings.RAW_DATA_DIR}")
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Không có nguồn {path}")

    run_id = str(uuid.uuid4())
    mode = "export_15min" if from_export else "full_3min"
    log_dir = settings.WORK_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / f"{run_id}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("utd19_dw")
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    db.run_id = run_id
    transaction = False
    checks = []
    try:
        # Khởi tạo audit trước transaction để lịch sử còn nguyên khi rollback dữ liệu.
        db.execute(render_sql((SQL_DIR / "00_schema.sql").read_text(encoding="utf-8")))
        db.execute("INSERT INTO etl.runs VALUES (?, ?, ?, 'RUNNING', CAST(now() AS TIMESTAMP), NULL, NULL)",
                   [run_id, mode, src.as_posix()])
        db.pending_logs = []
        db.execute("BEGIN TRANSACTION")
        transaction = True
        db.execute("DELETE FROM etl.quarantine")
        if from_export:
            for table in ("dw.fact_traffic_measurement", "mart.detector_day_coverage",
                          "mart.mfd_city_interval", "mart.city_kpi", "mart.congestion_kpi"):
                db.execute(f"DROP TABLE IF EXISTS {table}")
            for step in EXPORT_STEPS:
                load_weather() if step == "@weather" else run_sql_file(step)
        else:
            run_sql_directory("10_staging")
            load_weather()
            for stage in ("20_clean", "30_dw", "40_mart", "50_checks"):
                run_sql_directory(stage)
        run_sql_file("60_validation/60_common.sql")
        if not from_export:
            run_sql_file("60_validation/61_full.sql")
            run_sql_file("60_validation/62_source.sql")
        for table in ("etl.reconciliation", "etl.validation_results"):
            checks.extend(db.execute(f"SELECT check_id, description, expected, actual, status, checked_at FROM {table}").fetchall())
        assert_checks()
        run_sql_file("70_access/70_views_indexes.sql")
        record_load(mode, src.as_posix())
        db.execute("COMMIT")
        transaction = False
    except BaseException as exc:
        if transaction:
            db.execute("ROLLBACK")
        db.flush_logs()
        for row in checks:
            db.execute("INSERT INTO etl.check_history VALUES (?, ?, ?, ?, ?, ?, ?)", [run_id, *row])
        db.execute("UPDATE etl.runs SET status='FAILED', finished_at=CAST(now() AS TIMESTAMP), error=? WHERE run_id=?",
                   [str(exc)[:4000], run_id])
        logger.exception("Lần nạp %s thất bại; dữ liệu đã rollback", run_id)
        raise
    else:
        db.flush_logs()
        for row in checks:
            db.execute("INSERT INTO etl.check_history VALUES (?, ?, ?, ?, ?, ?, ?)", [run_id, *row])
        db.execute("UPDATE etl.runs SET status='SUCCESS', finished_at=CAST(now() AS TIMESTAMP) WHERE run_id=?", [run_id])
        logger.info("Lần nạp %s thành công (%s)", run_id, mode)
        print(f"ETL SUCCESS run_id={run_id} mode={mode}")
        print(db.query("SELECT check_id, status, expected, actual FROM etl.check_history WHERE run_id = '" + run_id + "' ORDER BY 1").to_string(index=False))
        return run_id
    finally:
        db.pending_logs = None
        db.run_id = None
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(old_level)
        db.close()


if __name__ == "__main__":
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ETL kho dữ liệu UTD19")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--from-export", action="store_true", help="nạp từ bản xuất khung 15 phút (không cần utd19_u.csv)")
    g.add_argument("--full", action="store_true", help="bắt buộc chạy đầy đủ từ utd19_u.csv")
    a = ap.parse_args()
    run_pipeline(True if a.from_export else (False if a.full else None))
