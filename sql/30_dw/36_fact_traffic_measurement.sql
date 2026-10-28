CREATE OR REPLACE TABLE dw.fact_traffic_measurement AS
SELECT dm.detector_key,
       CAST(strftime(m.day_adj, '%Y%m%d') AS INTEGER) AS date_key,
       CAST(m.interval_adj AS INTEGER) AS time_key,
       m.error_flag,
       m.flow_clean AS flow_veh_h_lane,
       m.occ_clean AS occupancy,
       (m.flow_clean IS NOT NULL) AS has_flow,
       (m.occ_clean IS NOT NULL) AS has_occupancy,
       CAST(1 AS TINYINT) AS measurement_count,
       m.dq_flag,
       CAST(1 AS INTEGER) AS load_batch_id
FROM clean.measurements m
JOIN etl.detector_map dm ON dm.city = m.city AND dm.detid = m.detid
ORDER BY date_key, detector_key, time_key;