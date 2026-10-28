CREATE OR REPLACE TABLE mart.detector_day_coverage AS
SELECT *, least(1.0, n_rows * 1.0 / expected_rows) AS coverage_ratio FROM (
    SELECT f.detector_key, d.city_key, f.date_key, count(*) AS n_rows, 
           min(f.time_key) AS first_time_key, max(f.time_key) AS time_key,
           CAST(96 AS BIGINT) AS expected_rows,
           sum(CAST(f.has_flow AS INTEGER)) AS n_flow, 
           sum(CAST(f.has_occupancy AS INTEGER)) AS n_occ,
           sum(CASE WHEN f.error_flag = 1 THEN 1 ELSE 0 END) AS n_error
    FROM dw.fact_traffic_measurement f 
    JOIN dw.dim_detector d USING (detector_key)
    GROUP BY f.detector_key, d.city_key, f.date_key
);