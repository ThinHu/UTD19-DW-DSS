-- Đối soát cho chế độ nạp từ bản xuất (hạt 15 phút).
CREATE OR REPLACE TABLE etl.reconciliation AS
WITH checks AS (
    SELECT 'RC-A' AS check_id, 'Toàn vẹn dòng: fact 15 phút = staging − cách ly' AS description,
           (SELECT count(*) FROM stg.window_15min_raw) -
           (SELECT count(*) FROM etl.quarantine WHERE source = 'window_15min') AS expected,
           (SELECT count(*) FROM dw.fact_traffic_15min) AS actual
    UNION ALL
    SELECT 'RC-B', 'Toàn vẹn khóa detector (không orphan)', 0,
           (SELECT count(*) FROM dw.fact_traffic_15min f ANTI JOIN dw.dim_detector d USING (detector_key))
    UNION ALL
    SELECT 'RC-C', 'Toàn vẹn khóa ngày (không orphan)', 0,
           (SELECT count(*) FROM dw.fact_traffic_15min f ANTI JOIN dw.dim_date d USING (date_key))
    UNION ALL
    SELECT 'RC-D', 'Toàn vẹn khóa khung 15 phút (không orphan)', 0,
           (SELECT count(*) FROM dw.fact_traffic_15min f ANTI JOIN dw.dim_time_slot s USING (slot_key))
    UNION ALL
    SELECT 'RC-E', 'Mart DSS khớp fact 15 phút (số dòng)',
           (SELECT count(*) FROM dw.fact_traffic_15min),
           (SELECT count(*) FROM mart.dss_detector_window)
    UNION ALL
    SELECT 'RC-G', 'Đúng hạt: không trùng (detector, ngày, khung) trong fact 15 phút', 0,
           (SELECT count(*) FROM (SELECT 1 FROM dw.fact_traffic_15min GROUP BY detector_key, date_key, slot_key HAVING count(*) > 1))
    UNION ALL
    SELECT 'RC-H', 'Khóa thay thế của các chiều là duy nhất', 0,
           (SELECT count(*) - count(DISTINCT detector_key) FROM dw.dim_detector WHERE is_current) +
           (SELECT count(*) - count(DISTINCT date_key) FROM dw.dim_date) +
           (SELECT count(*) - count(DISTINCT slot_key) FROM dw.dim_time_slot) +
           (SELECT count(*) - count(DISTINCT road_class_key) FROM dw.dim_road_class)
)
SELECT check_id, description, expected, actual,
       CASE WHEN expected = actual THEN 'PASS' ELSE 'FAIL' END AS status,
       CAST(now() AS TIMESTAMP) AS checked_at
FROM checks;
