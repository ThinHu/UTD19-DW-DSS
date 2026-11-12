"""Truy vấn OLAP chỉ đọc trên fact giao thông 15 phút.

Các biểu thức GROUP BY được chọn từ danh sách cố định; mọi giá trị lọc là
tham số DuckDB. Thước đo trung bình luôn được tính từ tổng và số mẫu sạch.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path


PERIODS = {
    "all": ("'all'", "'Toàn kỳ'"),
    "year": ("CAST(year AS VARCHAR)", "CAST(year AS VARCHAR)"),
    "quarter": ("CAST(year AS VARCHAR) || '-Q' || CAST(quarter AS VARCHAR)", "'Q' || CAST(quarter AS VARCHAR) || '/' || CAST(year AS VARCHAR)"),
    "month": ("year_month", "year_month"),
    "day": ("CAST(full_date AS VARCHAR)", "CAST(full_date AS VARCHAR)"),
    "date": ("CAST(full_date AS VARCHAR)", "CAST(full_date AS VARCHAR)"),
    "iso_week": ("CAST(year AS VARCHAR) || '-W' || lpad(CAST(iso_week AS VARCHAR), 2, '0')", "'Tuần ' || CAST(iso_week AS VARCHAR)"),
    "day_of_week": ("CAST(day_of_week AS VARCHAR)", "day_name_vn"),
    "day_type": ("day_type", "day_type_label"),
    "daypart": ("CAST(daypart_order AS VARCHAR)", "daypart"),
    "hour": ("CAST(hour AS VARCHAR)", "hour_label"),
    "slot": ("CAST(slot_key AS VARCHAR)", "slot_label"),
    "peak": ("CAST(is_peak AS VARCHAR)", "CASE WHEN is_peak THEN 'Cao điểm' ELSE 'Ngoài cao điểm' END"),
    "road_group": ("road_group", "road_group"),
    "road_class": ("fclass", "fclass_description"),
    "road_name": ("coalesce(nullif(road_name, ''), 'Không xác định')", "coalesce(nullif(road_name, ''), 'Không xác định')"),
    "road": ("coalesce(nullif(road_name, ''), 'Không xác định')", "coalesce(nullif(road_name, ''), 'Không xác định')"),
    "detector": ("detid", "detid || CASE WHEN road_name IS NULL OR road_name = '' THEN '' ELSE ' · ' || road_name END"),
}
ROADS = {
    "all": ("'all'", "'Toàn mạng'"),
    "group": ("road_group", "road_group"),
    "class": ("fclass", "fclass_description"),
    "detector": ("detid", "detid"),
}
GROUPS = {**PERIODS, **{k: v for k, v in ROADS.items() if k not in {"all", "detector"}}}


class OlapService:
    def __init__(self, db_path: str | Path, flow_max: float = 3500):
        self.db_path = Path(db_path)
        self.flow_max = flow_max

    @contextmanager
    def _connection(self):
        if not self.db_path.is_file():
            raise FileNotFoundError(f"Chưa có kho dữ liệu {self.db_path}")
        import duckdb

        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            yield con
        finally:
            con.close()

    def options(self) -> dict:
        with self._connection() as con:
            start, end = con.execute("""
                SELECT CAST(min(d.full_date) AS VARCHAR), CAST(max(d.full_date) AS VARCHAR)
                FROM dw.fact_traffic_15min f JOIN dw.dim_date d USING (date_key)
            """).fetchone()
            groups = [r[0] for r in con.execute("""
                SELECT DISTINCT r.road_group FROM dw.dim_detector x
                JOIN dw.dim_road_class r USING (road_class_key)
                WHERE x.detector_key > 0 AND x.is_current
                ORDER BY 1
            """).fetchall()]
            classes = [dict(zip(("fclass", "description", "road_group"), r)) for r in con.execute("""
                SELECT DISTINCT r.fclass, r.fclass_description, r.road_group
                FROM dw.dim_detector x
                JOIN dw.dim_road_class r USING (road_class_key)
                WHERE x.detector_key > 0 AND x.is_current
                ORDER BY 3, 1
            """).fetchall()]
            detectors = [dict(zip(("detid", "road", "lat", "long", "lanes", "speed_limit_kmh", "fclass", "road_group"), r))
                         for r in con.execute("""
                SELECT DISTINCT x.detid, x.road, x.lat, x."long", x.lanes, x.speed_limit_kmh, r.fclass, r.road_group
                FROM dw.dim_detector x
                LEFT JOIN dw.dim_road_class r USING (road_class_key)
                WHERE x.detector_key > 0 AND x.is_current
                ORDER BY x.detid
            """).fetchall()]
            load = con.execute("SELECT mode FROM etl.load_info LIMIT 1").fetchone()
        return {"start": start, "end": end, "road_groups": groups,
                "road_classes": classes, "detectors": detectors,
                "roads": sorted({d["road"] for d in detectors if d["road"]}),
                "load_mode": load[0] if load else None}

    def query(self, *, period: str = "month", road: str = "all",
              group_by: str | None = None, split_by: str | None = None,
              start: str | None = None, end: str | None = None,
              day_type: str | None = None, day_of_week: int | None = None,
              daypart: str | None = None, peak: bool | None = None,
              year: int | None = None, quarter: int | None = None,
              month: int | None = None, date_value: str | None = None,
              hour: int | None = None, hour_start: int | None = None,
              hour_end: int | None = None, road_name: str | None = None,
              road_group: str | None = None, fclass: str | None = None,
              detid: str | None = None) -> dict:
        if period not in PERIODS or road not in ROADS:
            raise ValueError("Chiều phân tích không hợp lệ")
        group_by = group_by or period
        split_by = split_by or road
        if group_by not in GROUPS or split_by not in GROUPS:
            raise ValueError("Chiều phân tích không hợp lệ")
        if day_type and day_type not in {"WD", "SAT", "SUN"}:
            raise ValueError("Loại ngày không hợp lệ")
        if day_of_week is not None and day_of_week not in range(1, 8):
            raise ValueError("Thứ trong tuần không hợp lệ")
        if peak is not None and not isinstance(peak, bool):
            raise ValueError("Bộ lọc cao điểm không hợp lệ")
        if quarter is not None and quarter not in range(1, 5) or month is not None and month not in range(1, 13):
            raise ValueError("Quý hoặc tháng không hợp lệ")
        if any(value is not None and value not in range(24) for value in (hour, hour_start, hour_end)):
            raise ValueError("Giờ không hợp lệ")
        if hour_start is not None and hour_end is not None and hour_start > hour_end:
            raise ValueError("Giờ bắt đầu phải trước hoặc bằng giờ kết thúc")
        try:
            for value in (start, end, date_value):
                if value:
                    date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Ngày phải có dạng YYYY-MM-DD") from exc
        if start and end and start > end:
            raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc")

        where, params = ["TRUE"], []
        for clause, value in (
            ("d.full_date >= CAST(? AS DATE)", start),
            ("d.full_date <= CAST(? AS DATE)", end),
            ("d.full_date = CAST(? AS DATE)", date_value),
            ("d.day_of_week = ?", day_of_week),
            ("d.day_type = ?", day_type),
            ("t.daypart = ?", daypart),
            ("t.is_peak = ?", peak),
            ("d.year = ?", year),
            ("d.quarter = ?", quarter),
            ("d.month = ?", month),
            ("t.hour = ?", hour),
            ("t.hour >= ?", hour_start),
            ("t.hour <= ?", hour_end),
            ("x.road = ?", road_name),
            ("r.road_group = ?", road_group),
            ("r.fclass = ?", fclass),
            ("x.detid = ?", detid),
        ):
            if value is not None and value != "":
                where.append(clause)
                params.append(value)

        cte = f"""
            WITH measures AS (
                SELECT f.detector_key, f.slot_key, d.full_date, d.year, d.quarter,
                       d.month, d.year_month, d.iso_week, d.day_of_week, d.day_name_vn,
                       d.day_type, d.day_type_label, t.daypart, t.daypart_order,
                       t.hour, t.hour_label, t.slot_label, t.is_peak,
                       r.road_group, r.fclass, r.fclass_description, x.detid,
                       x.road AS road_name,
                       f.n_intervals, f.n_err, f.n_occ_clean, f.n_flow_clean,
                       f.sum_occ_clean, f.sum_flow_clean,
                       f.sum_occ_clean / NULLIF(f.n_occ_clean, 0) AS occ_w,
                       f.sum_flow_clean / NULLIF(f.n_flow_clean, 0) AS flow_w
                FROM dw.fact_traffic_15min f
                JOIN dw.dim_date d USING (date_key)
                JOIN dw.dim_time_slot t USING (slot_key)
                JOIN dw.dim_detector x USING (detector_key)
                JOIN dw.dim_road_class r USING (road_class_key)
                WHERE {' AND '.join(where)}
            ), base AS (
                SELECT *,
                       (least(n_occ_clean, n_flow_clean) >= 3
                        AND occ_w BETWEEN 0 AND 1
                        AND flow_w BETWEEN 0 AND ?
                        AND NOT (occ_w >= 0.95 AND flow_w = 0)) AS valid_window
                FROM measures
            )
        """
        # Cùng luật khung hợp lệ với mart.detector_day_15min.
        args = [*params, self.flow_max]
        measures = """
            count(*) AS observed_windows,
            count(*) FILTER (WHERE valid_window) AS valid_windows,
            count(DISTINCT detector_key) AS detectors,
            count(DISTINCT detector_key) FILTER (WHERE valid_window) AS valid_detectors,
            coalesce(sum(n_occ_clean) FILTER (WHERE valid_window), 0) AS clean_occ_samples,
            coalesce(sum(n_flow_clean) FILTER (WHERE valid_window), 0) AS clean_flow_samples,
            round(100.0 * sum(sum_occ_clean) FILTER (WHERE valid_window)
                  / NULLIF(sum(n_occ_clean) FILTER (WHERE valid_window), 0), 2) AS avg_occupancy_pct,
            round(sum(sum_flow_clean) FILTER (WHERE valid_window)
                  / NULLIF(sum(n_flow_clean) FILTER (WHERE valid_window), 0), 2) AS avg_flow,
            round(100.0 * count(*) FILTER (WHERE valid_window)
                  / NULLIF(count(*), 0), 2) AS valid_coverage_pct,
            round(100.0 * sum(n_err) / NULLIF(sum(n_intervals), 0), 2) AS error_pct
        """
        p_key, p_label = GROUPS[group_by]
        r_key, r_label = GROUPS[split_by]
        grouped = (cte + f"""
            SELECT {p_key} AS group_key, {p_label} AS group_label,
                   {r_key} AS split_key, {r_label} AS split_label, {measures}
            FROM base GROUP BY 1, 2, 3, 4 ORDER BY 1, 3 LIMIT 5001
        """)
        summary_sql = cte + f"SELECT {measures} FROM base"
        with self._connection() as con:
            cur = con.execute(grouped, args)
            columns = [col[0] for col in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            if len(rows) > 5000:
                raise ValueError("Kết quả có hơn 5.000 nhóm; hãy thu hẹp khoảng ngày hoặc bộ lọc")
            cur = con.execute(summary_sql, args)
            summary = dict(zip((col[0] for col in cur.description), cur.fetchone()))
        for row in rows:
            row.update(period_key=row["group_key"], period_label=row["group_label"],
                       road_key=row["split_key"], road_label=row["split_label"])
        return {"period": period, "road": road, "group_by": group_by,
                "split_by": split_by, "rows": rows, "summary": summary}
