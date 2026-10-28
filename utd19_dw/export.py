import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
from utd19_dw.config import settings
from utd19_dw.db import db

class DataExporter:
    def __init__(self, export_dir: Path = None):
        self.export_dir = export_dir or settings.EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _safe_count(self, table_name: str):
        """Hàm đếm số dòng an toàn, trả về None nếu bảng không tồn tại."""
        try:
            return db.count(table_name)
        except Exception:
            return None

    def export_fact_measurements(self):
        """Xuất bảng Fact ra Parquet, phân vùng theo city_key."""
        print("Exporting dw.fact_traffic_measurement to Parquet (Partitioned)...", end=" ", flush=True)
        fact_out_dir = self.export_dir / "fact_traffic_measurement"
        fact_out_dir.mkdir(parents=True, exist_ok=True)
        
        if self._safe_count("dw.fact_traffic_measurement") is None:
            print("Table dw.fact_traffic_measurement does not exist, skipping.")
            return

        # Bỏ EXCLUDE (city_key) vì bảng fact nguyên thủy f không có cột city_key
        sql = f"""
        COPY (
            SELECT f.*, COALESCE(d.city_key, 0) AS city_key 
            FROM dw.fact_traffic_measurement f
            LEFT JOIN dw.dim_detector d USING (detector_key)
        ) TO '{fact_out_dir.as_posix()}' (
            FORMAT PARQUET,
            PARTITION_BY (city_key),
            OVERWRITE_OR_IGNORE true
        );
        """
        db.execute(sql)
        print("Done!")

    def export_marts(self):
        """Xuất các Data Marts sang CSV và Parquet phục vụ DSS."""
        marts = [
            "mart.mfd_city_interval",
            "mart.congestion_kpi",
            "mart.detector_day_coverage",
            "mart.city_kpi"
        ]
        for m in marts:
            if self._safe_count(m) is None:
                continue

            tbl_name = m.split(".")[1]
            print(f"Exporting {m}...", end=" ", flush=True)
            db.execute(f"COPY {m} TO '{(self.export_dir / f'{tbl_name}.parquet').as_posix()}' (FORMAT PARQUET);")
            db.execute(f"COPY {m} TO '{(self.export_dir / f'{tbl_name}.csv').as_posix()}' (HEADER, DELIMITER ',');")
            print("Done!")

    def run_all(self):
        print("=== BẮT ĐẦU QUY TRÌNH XUẤT DỮ LIỆU DSS ===")
        self.export_fact_measurements()
        self.export_marts()
        print(f"-> All data exported to: {self.export_dir}")

def run_export():
    exporter = DataExporter()
    exporter.run_all()

if __name__ == "__main__":
    run_export()