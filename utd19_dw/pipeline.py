import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import re
from utd19_dw.config import settings, BASE_DIR
from utd19_dw.db import db

SQL_DIR = BASE_DIR / "sql"

def _date_list(days) -> str:
    """Danh sách ngày cho mệnh đề IN; rỗng thì trả về NULL để IN (NULL) luôn sai."""
    return ", ".join(f"DATE '{d}'" for d in days) if days else "NULL"


def render_sql(sql_content: str) -> str:
    """Thay thế các biến động vào mẫu SQL một cách an toàn."""
    city_in = ", ".join(f"'{c}'" for c in settings.CITIES)
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
        "DATA_RAW_DIR": settings.RAW_DATA_DIR.as_posix(),
        "RAW_DATA_DIR": settings.RAW_DATA_DIR.as_posix(),  # Alias dự phòng
        "OCC_PERCENT_THRESHOLD": str(getattr(settings, "OCC_PERCENT_THRESHOLD", 1.5)),
        "HOLIDAYS_IN": _date_list(settings.HOLIDAYS),
        "SPECIAL_DAYS_IN": _date_list(settings.SPECIAL_DAYS),
        "DIM_DATE_START": str(settings.START_DATE or "2015-01-01"),
        "DIM_DATE_END": str(settings.DIM_DATE_END or settings.END_DATE or "2015-12-31"),
        "EXPORT_SRC_DIR": settings.EXPORT_SRC_DIR.as_posix(),
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
    made = re.findall(r"CREATE\s+OR\s+REPLACE\s+TABLE\s+([a-z_]+\.[a-z_0-9]+)\s+AS", sql, flags=re.I)
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
                       f"SELECT * FROM read_csv('{path.as_posix()}', header=true, all_varchar=true)")
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


def run_pipeline(from_export: bool | None = None):
    """Chạy ETL. from_export=None: tự chọn — có utd19_u.csv thì chạy đầy đủ, không thì nạp từ bản xuất."""
    raw = settings.RAW_DATA_DIR / "utd19_u.csv"
    if from_export is None:
        from_export = not raw.exists()
    run_sql_file("00_schema.sql")
    if from_export:
        src = settings.EXPORT_SRC_DIR / "detector_window_15min.csv.gz"
        if not src.exists():
            raise SystemExit(f"Không có {raw} lẫn bản xuất {src}")
        print(f"=== PIPELINE ETL — CHẾ ĐỘ NẠP TỪ BẢN XUẤT 15 PHÚT ({src.parent.name}) ===")
        record_load("export_15min", src.as_posix())
        for step in EXPORT_STEPS:
            load_weather() if step == "@weather" else run_sql_file(step)
    else:
        print("=== PIPELINE ETL — CHẾ ĐỘ ĐẦY ĐỦ (utd19_u.csv, hạt 3 phút) ===")
        record_load("full_3min", raw.as_posix())
        run_sql_directory("10_staging")
        load_weather()
        for stage in ["20_clean", "30_dw", "40_mart", "50_checks"]:
            run_sql_directory(stage)
    print(db.query("SELECT check_id, status, expected, actual FROM etl.reconciliation ORDER BY 1").to_string(index=False))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ETL kho dữ liệu UTD19")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--from-export", action="store_true", help="nạp từ bản xuất khung 15 phút (không cần utd19_u.csv)")
    g.add_argument("--full", action="store_true", help="bắt buộc chạy đầy đủ từ utd19_u.csv")
    a = ap.parse_args()
    run_pipeline(True if a.from_export else (False if a.full else None))
