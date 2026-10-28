CREATE OR REPLACE TABLE mart.mfd_city_interval AS
SELECT c.citycode, f.date_key, f.time_key,
       sum(f.flow_veh_h_lane * w.weight) / NULLIF(sum(CASE WHEN f.flow_veh_h_lane IS NOT NULL THEN w.weight END), 0) AS flow_w,
       sum(f.occupancy * w.weight) / NULLIF(sum(CASE WHEN f.occupancy IS NOT NULL THEN w.weight END), 0) AS occ_w,
       count(*) AS n_detectors, 
       sum(CAST(f.has_flow AS INTEGER)) AS n_flow, 
       sum(CAST(f.has_occupancy AS INTEGER)) AS n_occ
FROM dw.fact_traffic_measurement f
JOIN (
    SELECT detector_key, city_key,
           CASE WHEN coalesce(monitored_lane_length_km, 0) > 0 THEN monitored_lane_length_km * coalesce(lanes, 1)
                ELSE coalesce(lanes, 1.0) END AS weight
    FROM dw.dim_detector WHERE detector_key > 0
) w USING (detector_key)
JOIN dw.dim_city c ON c.city_key = w.city_key
JOIN mart.detector_day_coverage cov ON cov.detector_key = f.detector_key AND cov.date_key = f.date_key AND cov.coverage_ratio >= {COVERAGE_MIN}
WHERE (f.dq_flag & {EXCLUDE_MASK}) = 0
GROUP BY c.citycode, f.date_key, f.time_key;