"""Đọc thông tin kiểm soát của kho dữ liệu (nhật ký ETL, đối soát, cách ly, siêu dữ liệu, lược đồ sao)
để hiển thị trên trang "Kho dữ liệu & ETL" của dashboard. Chỉ đọc; mở DW theo từng yêu cầu để không giữ khóa tệp.
"""
from __future__ import annotations

from contextlib import contextmanager

from .config import resolve


class DwInfo:
    def __init__(self, cfg: dict):
        self.db_path = resolve(cfg, cfg["source"]["dw_db"])

    @property
    def available(self) -> bool:
        if not self.db_path.exists():
            return False
        try:
            with self._con() as con:
                con.execute("SELECT 1 FROM etl.reconciliation LIMIT 1")
            return True
        except Exception:
            return False

    @contextmanager
    def _con(self):
        import duckdb
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            yield con
        finally:
            con.close()

    def quality(self) -> dict:
        q = {}
        with self._con() as con:
            def df(sql):
                try:
                    cur = con.execute(sql)
                except Exception:      # bảng chưa có (ví dụ DW dựng bằng phiên bản pipeline cũ)
                    return []
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
            q["load_info"] = (df("SELECT mode, source, date_start, date_end, CAST(loaded_at AS VARCHAR) AS loaded_at FROM etl.load_info") or [None])[0]
            q["reconciliation"] = df("SELECT check_id, description, expected, actual, status FROM etl.reconciliation ORDER BY 1")
            q["run_log"] = df("SELECT step, seconds, rows_out, note FROM etl.run_log ORDER BY logged_at")
            q["quarantine"] = df("SELECT source, rule_id, count(*) AS n FROM etl.quarantine GROUP BY 1, 2 ORDER BY 3 DESC")
            q["catalog"] = df("SELECT layer, object_name, object_role, grain, source, transformation, description, "
                              "row_count, column_count FROM etl.metadata_catalog")
            q["star"] = df("""SELECT table_name, list(column_name ORDER BY column_index) AS columns
                              FROM duckdb_columns() WHERE schema_name = 'dw'
                              AND table_name IN ('fact_traffic_15min', 'fact_traffic_measurement', 'dim_date', 'dim_time_slot',
                                                 'dim_detector', 'dim_road_class', 'dim_weather', 'dim_link', 'dim_city')
                              GROUP BY 1 ORDER BY 1""")
            q["coverage_by_month"] = df("""SELECT dd.year_month AS month,
                                                  round(100.0 * sum(n_valid_windows) / sum(n_windows), 1) AS valid_pct,
                                                  round(avg(error_pct), 2) AS error_pct
                                           FROM mart.detector_day_15min s JOIN dw.dim_date dd USING (date_key)
                                           GROUP BY 1 ORDER BY 1""")
        return q
