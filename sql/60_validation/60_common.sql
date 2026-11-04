-- Kiểm tra dữ liệu cho cả hai chế độ; mọi kết quả phải PASS.
CREATE OR REPLACE TABLE etl.validation_results AS
WITH checks AS (
SELECT 'DQ-EMPTY' AS check_id, 'Fact không rỗng' AS description, 0::BIGINT AS expected, (SELECT CASE WHEN count(*) > 0 THEN 0 ELSE 1 END FROM dw.fact_traffic_15min)::BIGINT AS actual
UNION ALL
SELECT 'DQ-FK15' AS check_id, 'Fact 15 phút có đủ khóa chiều' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.fact_traffic_15min f
LEFT JOIN dw.dim_detector d USING(detector_key)
LEFT JOIN dw.dim_date dd USING(date_key)
LEFT JOIN dw.dim_time_slot t USING(slot_key)
WHERE d.detector_key IS NULL OR dd.date_key IS NULL OR t.slot_key IS NULL
OR f.detector_key IS NULL OR f.date_key IS NULL OR f.slot_key IS NULL)::BIGINT AS actual
UNION ALL
SELECT 'DQ-COUNTS' AS check_id, 'Count tổng hợp hợp lệ' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.fact_traffic_15min WHERE NOT coalesce(
n_intervals BETWEEN 1 AND 5 AND n_err BETWEEN 0 AND n_intervals
AND n_occ BETWEEN 0 AND n_intervals AND n_flow BETWEEN 0 AND n_intervals
AND n_flow0 BETWEEN 0 AND n_flow
AND n_occ_clean BETWEEN 0 AND least(n_occ, n_intervals-n_err)
AND n_flow_clean BETWEEN 0 AND least(n_flow, n_intervals-n_err), FALSE))::BIGINT AS actual
UNION ALL
SELECT 'DQ-OCC' AS check_id, 'Tổng và count nhất quán: sum_occ_all' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.fact_traffic_15min WHERE NOT coalesce(
    (n_occ = 0 AND (sum_occ_all IS NULL OR sum_occ_all = 0)) OR
    (n_occ > 0 AND isfinite(sum_occ_all) AND sum_occ_all BETWEEN 0 AND n_occ * 1), FALSE))::BIGINT AS actual
UNION ALL
SELECT 'DQ-FLOW' AS check_id, 'Tổng và count nhất quán: sum_flow_all' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.fact_traffic_15min WHERE NOT coalesce(
    (n_flow = 0 AND (sum_flow_all IS NULL OR sum_flow_all = 0)) OR
    (n_flow > 0 AND isfinite(sum_flow_all) AND sum_flow_all BETWEEN 0 AND n_flow * {FLOW_MAX}), FALSE))::BIGINT AS actual
UNION ALL
SELECT 'DQ-OCC-CLEAN' AS check_id, 'Tổng và count nhất quán: sum_occ_clean' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.fact_traffic_15min WHERE NOT coalesce(
    (n_occ_clean = 0 AND (sum_occ_clean IS NULL OR sum_occ_clean = 0)) OR
    (n_occ_clean > 0 AND isfinite(sum_occ_clean) AND sum_occ_clean BETWEEN 0 AND n_occ_clean * 1), FALSE))::BIGINT AS actual
UNION ALL
SELECT 'DQ-FLOW-CLEAN' AS check_id, 'Tổng và count nhất quán: sum_flow_clean' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.fact_traffic_15min WHERE NOT coalesce(
    (n_flow_clean = 0 AND (sum_flow_clean IS NULL OR sum_flow_clean = 0)) OR
    (n_flow_clean > 0 AND isfinite(sum_flow_clean) AND sum_flow_clean BETWEEN 0 AND n_flow_clean * {FLOW_MAX}), FALSE))::BIGINT AS actual
UNION ALL
SELECT 'DQ-DIM-FK' AS check_id, 'Dimension detector tham chiếu đủ city/link/road class' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM dw.dim_detector d
LEFT JOIN dw.dim_city c USING(city_key)
LEFT JOIN dw.dim_link l USING(link_key)
LEFT JOIN dw.dim_road_class r USING(road_class_key)
WHERE c.city_key IS NULL OR l.link_key IS NULL OR r.road_class_key IS NULL)::BIGINT AS actual
UNION ALL
SELECT 'DQ-NATURAL-KEY' AS check_id, 'Mỗi detector có đúng một phiên bản hiện hành' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM (
SELECT city_key, detid FROM dw.dim_detector WHERE is_current GROUP BY city_key, detid HAVING count(*) <> 1))::BIGINT AS actual
UNION ALL
SELECT 'DQ-MART-GRAIN' AS check_id, 'Mart DSS không trùng grain' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM (
SELECT detid, day, slot FROM mart.dss_detector_window GROUP BY ALL HAVING count(*) > 1))::BIGINT AS actual
UNION ALL
SELECT 'DQ-MART-VALUES' AS check_id, 'Mart DSS khớp toàn bộ khóa/count/mean của fact' AS description, 0::BIGINT AS expected, (SELECT count(*) FROM
(SELECT f.*, d.detid, strftime(dd.full_date, '%Y-%m-%d') AS day FROM dw.fact_traffic_15min f
JOIN dw.dim_detector d USING(detector_key) JOIN dw.dim_date dd USING(date_key)) f
FULL OUTER JOIN mart.dss_detector_window m ON m.detid=f.detid AND m.day=f.day AND m.slot=f.slot_key
WHERE f.detector_key IS NULL OR m.detid IS NULL OR m.n IS DISTINCT FROM f.n_intervals OR m.n_err IS DISTINCT FROM f.n_err OR m.n_occ IS DISTINCT FROM f.n_occ OR m.n_flow IS DISTINCT FROM f.n_flow OR m.n_flow0 IS DISTINCT FROM f.n_flow0 OR m.n_occ_clean IS DISTINCT FROM f.n_occ_clean OR m.n_flow_clean IS DISTINCT FROM f.n_flow_clean OR m.mean_occ_all IS DISTINCT FROM (f.sum_occ_all/nullif(f.n_occ,0)) OR m.mean_flow_all IS DISTINCT FROM (f.sum_flow_all/nullif(f.n_flow,0)) OR m.mean_occ_clean IS DISTINCT FROM (f.sum_occ_clean/nullif(f.n_occ_clean,0)) OR m.mean_flow_clean IS DISTINCT FROM (f.sum_flow_clean/nullif(f.n_flow_clean,0)))::BIGINT AS actual
UNION ALL
SELECT 'DQ-DIM-KEYS', 'Mọi khóa chiều không NULL và duy nhất', 0, (SELECT count(*)-count(DISTINCT city_key) FROM dw.dim_city) + (SELECT count(*)-count(DISTINCT link_key) FROM dw.dim_link) + (SELECT count(*)-count(DISTINCT detector_key) FROM dw.dim_detector) + (SELECT count(*)-count(DISTINCT date_key) FROM dw.dim_date) + (SELECT count(*)-count(DISTINCT time_key) FROM dw.dim_time_of_day) + (SELECT count(*)-count(DISTINCT slot_key) FROM dw.dim_time_slot) + (SELECT count(*)-count(DISTINCT road_class_key) FROM dw.dim_road_class) + (SELECT count(*)-count(DISTINCT date_key) FROM dw.dim_weather)
UNION ALL
SELECT 'DQ-CALENDAR', 'Khóa ngày khớp ngày lịch', 0,
(SELECT count(*) FROM dw.dim_date WHERE date_key > 0 AND
 (full_date IS NULL OR date_key <> CAST(strftime(full_date,'%Y%m%d') AS INTEGER)))
)
SELECT *, CASE WHEN expected=actual THEN 'PASS' ELSE 'FAIL' END AS status,
CAST(now() AS TIMESTAMP) AS checked_at FROM checks;
