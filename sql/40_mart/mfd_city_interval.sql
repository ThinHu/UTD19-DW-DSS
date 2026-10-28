CREATE OR REPLACE TABLE mart.mfd_city_interval AS
WITH base AS (
    SELECT
        dt.city_key,
        c.city_name,
        f.date_key,
        f.time_key AS interval_seconds,
        f.flow_veh_h_lane AS flow,
        f.occupancy,
        COALESCE(dt.monitored_lane_length_km, CAST(dt.lanes AS DOUBLE), 1.0) AS weight
    FROM dw.fact_traffic_measurement f
    JOIN dw.dim_detector dt ON f.detector_key = dt.detector_key
    JOIN dw.dim_city c ON dt.city_key = c.city_key
    WHERE (f.dq_flag & {EXCLUDE_MASK}) = 0
)
SELECT
    city_key,
    city_name,
    date_key,
    interval_seconds,
    count(*) AS active_detectors,
    ROUND(SUM(flow * weight) / NULLIF(SUM(weight), 0), 2) AS network_weighted_flow,
    ROUND(SUM(occupancy * weight) / NULLIF(SUM(weight), 0), 4) AS network_weighted_density
FROM base
GROUP BY city_key, city_name, date_key, interval_seconds;
