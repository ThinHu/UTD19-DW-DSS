-- Fact tổng hợp hạt 15 phút nạp từ bản xuất. Cùng cấu trúc với sql/30_dw/38_fact_traffic_15min.sql
-- (bản gộp từ fact 3 phút), nên các mart và DSS phía sau không phân biệt hai chế độ nạp.
-- Lưu các thước đo CỘNG ĐƯỢC (số đếm, tổng); trung bình được tính lại khi roll-up = tổng / số đếm.
CREATE OR REPLACE TABLE dw.fact_traffic_15min AS
SELECT dm.detector_key,
       CAST(strftime(w.day_date, '%Y%m%d') AS INTEGER) AS date_key,
       CAST(w.slot AS SMALLINT) AS slot_key,
       CAST(w.n AS SMALLINT) AS n_intervals,
       CAST(coalesce(w.n_err, 0) AS SMALLINT) AS n_err,
       CAST(coalesce(w.n_occ, 0) AS SMALLINT) AS n_occ,
       CAST(coalesce(w.n_flow, 0) AS SMALLINT) AS n_flow,
       CAST(coalesce(w.n_flow0, 0) AS SMALLINT) AS n_flow0,
       CAST(coalesce(w.n_occ_clean, 0) AS SMALLINT) AS n_occ_clean,
       CAST(coalesce(w.n_flow_clean, 0) AS SMALLINT) AS n_flow_clean,
       w.mean_occ_all * w.n_occ AS sum_occ_all,
       w.mean_flow_all * w.n_flow AS sum_flow_all,
       w.mean_occ_clean * w.n_occ_clean AS sum_occ_clean,
       w.mean_flow_clean * w.n_flow_clean AS sum_flow_clean,
       'export_15min' AS load_source
FROM clean.window_15min w
JOIN etl.detector_map dm ON dm.city = w.city AND dm.detid = w.detid
ORDER BY date_key, detector_key, slot_key;
