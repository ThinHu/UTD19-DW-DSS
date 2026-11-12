-- So sánh từng bản ghi theo khóa nghiệp vụ, không dùng detector_map để tính kỳ vọng.
INSERT INTO etl.validation_results
WITH actual AS (
    SELECT c.citycode AS city, d.detid, f.*
    FROM dw.fact_traffic_measurement f
    JOIN dw.dim_detector d USING(detector_key)
    JOIN dw.dim_city c USING(city_key)
), differences AS (
    SELECT 1 FROM clean.measurements s FULL OUTER JOIN actual f
    ON s.city=f.city AND s.detid=f.detid
       AND CAST(strftime(s.day_adj,'%Y%m%d') AS INTEGER)=f.date_key
       AND s.interval_adj=f.time_key
    WHERE s._row_id IS NULL OR f.detector_key IS NULL
       OR s.flow_clean IS DISTINCT FROM f.flow_veh_h_lane
       OR s.occ_clean IS DISTINCT FROM f.occupancy
       OR s.error_flag IS DISTINCT FROM f.error_flag
       OR s.dq_flag IS DISTINCT FROM f.dq_flag
       OR (s.flow_clean IS NOT NULL) IS DISTINCT FROM f.has_flow
       OR (s.occ_clean IS NOT NULL) IS DISTINCT FROM f.has_occupancy
       OR f.measurement_count IS DISTINCT FROM 1
)
SELECT 'DQ-SOURCE', 'Mọi giá trị clean khớp fact theo khóa nghiệp vụ',
0, count(*), CASE WHEN count(*)=0 THEN 'PASS' ELSE 'FAIL' END, CAST(now() AS TIMESTAMP)
FROM differences;

INSERT INTO etl.validation_results
SELECT 'DQ-F3-DOMAIN', 'Miền giá trị fact 3 phút, error flag và bước thời gian',
0, count(*), CASE WHEN count(*)=0 THEN 'PASS' ELSE 'FAIL' END, CAST(now() AS TIMESTAMP)
FROM dw.fact_traffic_measurement
WHERE NOT coalesce(error_flag IN (0,1) AND time_key BETWEEN 0 AND 86399 AND time_key % 180=0
AND (flow_veh_h_lane IS NULL OR (isfinite(flow_veh_h_lane) AND flow_veh_h_lane BETWEEN 0 AND {FLOW_MAX}))
AND (occupancy IS NULL OR (isfinite(occupancy) AND occupancy BETWEEN 0 AND 1)), FALSE);
