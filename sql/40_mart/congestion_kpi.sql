CREATE OR REPLACE TABLE mart.congestion_kpi AS
SELECT
    dt.city_key,
    c.city_name,
    f.date_key,
    CAST(f.time_key / 3600 AS INTEGER) AS hour_of_day,
    count(*) AS total_samples,
    ROUND(AVG(f.flow_veh_h_lane), 2) AS avg_flow,
    ROUND(AVG(f.occupancy), 4) AS avg_occupancy,
    ROUND(100.0 * COUNT(CASE WHEN f.occupancy > 0.30 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS congestion_sample_pct
FROM dw.fact_traffic_measurement f
JOIN dw.dim_detector dt ON f.detector_key = dt.detector_key
JOIN dw.dim_city c ON dt.city_key = c.city_key
WHERE (f.dq_flag & {EXCLUDE_MASK}) = 0
GROUP BY dt.city_key, c.city_name, f.date_key, CAST(f.time_key / 3600 AS INTEGER);
