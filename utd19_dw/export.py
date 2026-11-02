"""Xuất kho dữ liệu ra Parquet/CSV (data/export/) để dùng ở công cụ khác (Power BI, Tableau, pandas...).

    python -m utd19_dw.export

- star/: lược đồ sao (các chiều + fact 15 phút) dạng Parquet, giữ nguyên khóa thay thế để nối lại.
- fact_traffic_measurement/: fact gốc 3 phút, phân vùng theo city_key (chỉ có ở chế độ nạp đầy đủ).
- <mart>.parquet / .csv: các data mart và bảng kiểm soát ETL.
"""
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

STAR = ["dw.dim_city", "dw.dim_road_class", "dw.dim_link", "dw.dim_detector", "dw.dim_date",
        "dw.dim_time_of_day", "dw.dim_time_slot", "dw.dim_weather", "dw.fact_traffic_15min"]
MARTS = ["mart.dss_detector_window", "mart.detector_day_15min", "mart.detector_day_coverage",
         "mart.mfd_city_interval", "mart.city_kpi", "mart.congestion_kpi",
         "etl.metadata_catalog", "etl.reconciliation", "etl.run_log", "etl.load_info"]


class DataExporter:
    def __init__(self, export_dir: Path = None):
        self.export_dir = export_dir or settings.EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _exists(table: str) -> bool:
        return db.count(table) is not None

    def export_star(self):
        out = self.export_dir / "star"
        out.mkdir(parents=True, exist_ok=True)
        for t in STAR:
            if not self._exists(t):
                continue
            print(f"Xuất {t} ...", end=" ", flush=True)
            db.execute(f"COPY {t} TO '{(out / (t.split('.')[1] + '.parquet')).as_posix()}' (FORMAT PARQUET)")
            print("xong")

    def export_fact_measurements(self):
        if not self._exists("dw.fact_traffic_measurement"):
            print("Bỏ qua dw.fact_traffic_measurement (không có ở chế độ nạp từ bản xuất).")
            return
        print("Xuất dw.fact_traffic_measurement (phân vùng theo city_key) ...", end=" ", flush=True)
        out = self.export_dir / "fact_traffic_measurement"
        out.mkdir(parents=True, exist_ok=True)
        db.execute(f"""
            COPY (SELECT f.*, coalesce(d.city_key, 0) AS city_key
                  FROM dw.fact_traffic_measurement f LEFT JOIN dw.dim_detector d USING (detector_key))
            TO '{out.as_posix()}' (FORMAT PARQUET, PARTITION_BY (city_key), OVERWRITE_OR_IGNORE true)""")
        print("xong")

    def export_marts(self):
        for m in MARTS:
            if not self._exists(m):
                continue
            name = m.replace(".", "_") if m.startswith("etl.") else m.split(".")[1]
            print(f"Xuất {m} ...", end=" ", flush=True)
            db.execute(f"COPY {m} TO '{(self.export_dir / f'{name}.parquet').as_posix()}' (FORMAT PARQUET)")
            db.execute(f"COPY {m} TO '{(self.export_dir / f'{name}.csv').as_posix()}' (HEADER, DELIMITER ',')")
            print("xong")

    def run_all(self):
        print("=== XUẤT KHO DỮ LIỆU ===")
        self.export_star()
        self.export_fact_measurements()
        self.export_marts()
        print(f"-> Đã xuất vào: {self.export_dir}")


def run_export():
    DataExporter().run_all()


if __name__ == "__main__":
    run_export()
