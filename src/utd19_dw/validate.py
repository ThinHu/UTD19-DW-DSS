"""Kiểm chứng DW có sẵn bằng kết nối read-only; chỉ tạo bảng kiểm tạm."""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from utd19_dw.config import settings
from utd19_dw.pipeline import SQL_DIR, render_sql


def validate_database(db_path=None):
    path = Path(db_path or settings.DB_PATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Không có DW: {path}")
    with tempfile.TemporaryDirectory(prefix="utd19_validate_") as scratch, duckdb.connect(str(path), read_only=True) as con:
        con.execute("SET threads=?", [settings.DUCKDB_THREADS])
        con.execute("SET memory_limit=?", [os.environ.get("UTD_MEMORY_LIMIT", settings.DUCKDB_MEMORY)])
        con.execute("SET temp_directory=?", [scratch])
        load = con.execute("SELECT mode, source, date_start, date_end, loaded_at FROM etl.load_info").fetchone()
        mode = load[0]
        if mode not in ("full_3min", "export_15min"):
            raise ValueError(f"Chế độ DW không hỗ trợ: {mode}")
        reconciliation = "50_checks/50_reconciliation.sql" if mode == "full_3min" else "export_mode/50_reconciliation.sql"
        jobs = [reconciliation, "60_validation/60_common.sql"]
        if mode == "full_3min":
            jobs.extend(["60_validation/61_full.sql", "60_validation/62_source.sql"])
        for name in jobs:
            sql = render_sql((SQL_DIR / name).read_text(encoding="utf-8"))
            sql = sql.replace("CREATE OR REPLACE TABLE etl.reconciliation", "CREATE OR REPLACE TEMP TABLE validation_reconciliation")
            sql = sql.replace("CREATE OR REPLACE TABLE etl.validation_results", "CREATE OR REPLACE TEMP TABLE validation_results")
            sql = sql.replace("INSERT INTO etl.validation_results", "INSERT INTO validation_results")
            con.execute(sql)
        cursor = con.execute("SELECT * FROM validation_reconciliation UNION ALL SELECT * FROM validation_results ORDER BY check_id")
        checks = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
        tables = ["dw.dim_detector", "dw.fact_traffic_15min", "mart.dss_detector_window", "etl.quarantine"]
        if mode == "full_3min":
            tables.append("dw.fact_traffic_measurement")
        counts = {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in tables}
        quarantine = con.execute("SELECT rule_id, count(*) FROM etl.quarantine GROUP BY 1 ORDER BY 1").fetchall()
        dates = con.execute("SELECT min(date_key), max(date_key) FROM dw.fact_traffic_15min").fetchone()
    return {"database": str(path), "mode": mode, "source": load[1], "loaded_at": load[4],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if checks and all(c["status"] == "PASS" for c in checks) else "FAIL",
            "row_counts": counts, "date_key_range": dates, "quarantine_by_rule": dict(quarantine), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description="Kiểm chứng DW mà không nạp lại nguồn")
    parser.add_argument("--db", type=Path, default=settings.DB_PATH)
    parser.add_argument("--report", type=Path, help="Ghi báo cáo JSON")
    args = parser.parse_args()
    report = validate_database(args.db)
    result = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(result + "\n", encoding="utf-8")
    print(result)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
