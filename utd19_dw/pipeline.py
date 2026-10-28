import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
from utd19_dw.config import settings, BASE_DIR
from utd19_dw.db import db

SQL_DIR = BASE_DIR / "sql"

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
        "OCC_PERCENT_THRESHOLD": str(getattr(settings, "OCC_PERCENT_THRESHOLD", 1.5))
    }
    
    rendered = sql_content
    for key, val in replacements.items():
        rendered = rendered.replace(f"{{{key}}}", val)
    return rendered

def run_sql_directory(dir_name: str):
    target_dir = SQL_DIR / dir_name
    if not target_dir.exists():
        return

    sql_files = sorted(target_dir.glob("*.sql"))
    for sql_file in sql_files:
        with open(sql_file, "r", encoding="utf-8") as f:
            raw_sql = f.read()
        
        formatted_sql = render_sql(raw_sql)
        step_name = f"{dir_name}/{sql_file.stem}"

        # Bỏ table_guess gán cứng tên file để tránh đếm sai tên bảng làm crash db.step()
        with db.step(step_name):
            db.execute(formatted_sql)

def run_pipeline():
    print("=== CHẠY TOÀN BỘ PIPELINE ETL ===")
    stages = [
        "00_schema.sql",
        "10_staging",
        "20_clean",
        "30_dw",
        "40_mart",
        "50_checks"
    ]
    
    for stage in stages:
        stage_path = SQL_DIR / stage
        if not stage_path.exists() and stage == "00_schema.sql":
            alt_path = SQL_DIR / "00_schemas.sql"
            if alt_path.exists():
                stage_path = alt_path

        if stage_path.is_file():
            with open(stage_path, "r", encoding="utf-8") as f:
                with db.step(stage):
                    db.execute(render_sql(f.read()))
        else:
            run_sql_directory(stage)

if __name__ == "__main__":
    run_pipeline()