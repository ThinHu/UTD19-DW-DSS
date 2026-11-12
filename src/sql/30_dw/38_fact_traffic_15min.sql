-- Fact tổng hợp (aggregate fact) hạt detector × ngày × khung 15 phút, gộp từ fact gốc 3 phút.
-- Kho giữ hai mức hạt (Inmon: dual granularity; Kimball: aggregate fact): hạt 3 phút cho truy vết,
-- hạt 15 phút cho OLAP và DSS (nhanh hơn ~5 lần, đủ chi tiết cho điều phối).
-- Chỉ lưu thước đo cộng được; trung bình = tổng / số đếm khi roll-up lên giờ, ngày, tuyến đường...
CREATE OR REPLACE TABLE dw.fact_traffic_15min AS
SELECT f.detector_key,
       f.date_key,
       CAST(f.time_key // 900 AS SMALLINT) AS slot_key,
       CAST(count(*) AS SMALLINT) AS n_intervals,
       CAST(sum(CASE WHEN f.error_flag = 1 THEN 1 ELSE 0 END) AS SMALLINT) AS n_err,
       CAST(count(f.occupancy) AS SMALLINT) AS n_occ,
       CAST(count(f.flow_veh_h_lane) AS SMALLINT) AS n_flow,
       CAST(sum(CASE WHEN f.flow_veh_h_lane = 0 THEN 1 ELSE 0 END) AS SMALLINT) AS n_flow0,
       CAST(count(f.occupancy) FILTER (WHERE coalesce(f.error_flag, 0) = 0) AS SMALLINT) AS n_occ_clean,
       CAST(count(f.flow_veh_h_lane) FILTER (WHERE coalesce(f.error_flag, 0) = 0) AS SMALLINT) AS n_flow_clean,
       sum(f.occupancy) AS sum_occ_all,
       sum(f.flow_veh_h_lane) AS sum_flow_all,
       sum(f.occupancy) FILTER (WHERE coalesce(f.error_flag, 0) = 0) AS sum_occ_clean,
       sum(f.flow_veh_h_lane) FILTER (WHERE coalesce(f.error_flag, 0) = 0) AS sum_flow_clean,
       'fact_3min' AS load_source
FROM dw.fact_traffic_measurement f
WHERE f.detector_key > 0 AND f.time_key >= 0
GROUP BY f.detector_key, f.date_key, f.time_key // 900
ORDER BY date_key, detector_key, slot_key;
