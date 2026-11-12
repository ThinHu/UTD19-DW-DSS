-- Mart phục vụ DSS: khung 15 phút theo detector × ngày × slot, lấy từ fact tổng hợp dw.fact_traffic_15min.
-- Cột giống hệt tệp detector_window_15min.csv.gz để engine DSS đọc trực tiếp từ DW.
--   *_all   : trung bình trên mọi khoảng đo có giá trị
--   *_clean : trung bình chỉ trên khoảng đo không bị gắn error (error_flag = 0)
CREATE OR REPLACE TABLE mart.dss_detector_window AS
SELECT d.detid,
       strftime(dd.full_date, '%Y-%m-%d') AS day,
       CAST(f.slot_key AS INTEGER)        AS slot,
       f.n_intervals AS n, f.n_err, f.n_occ, f.n_flow, f.n_flow0, f.n_occ_clean, f.n_flow_clean,
       f.sum_occ_all    / NULLIF(f.n_occ, 0)        AS mean_occ_all,
       f.sum_flow_all   / NULLIF(f.n_flow, 0)       AS mean_flow_all,
       f.sum_occ_clean  / NULLIF(f.n_occ_clean, 0)  AS mean_occ_clean,
       f.sum_flow_clean / NULLIF(f.n_flow_clean, 0) AS mean_flow_clean
FROM dw.fact_traffic_15min f
JOIN dw.dim_detector d USING (detector_key)
JOIN dw.dim_date dd    USING (date_key)
WHERE f.detector_key > 0;
