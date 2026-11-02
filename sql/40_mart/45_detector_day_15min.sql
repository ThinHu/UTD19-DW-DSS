-- Snapshot chất lượng theo detector × ngày (periodic snapshot), lấy từ fact 15 phút.
-- Khung hợp lệ: ≥ 3/5 khoảng đo không lỗi, occupancy trong [0, 1], flow trong [0, FLOW_MAX], không kẹt
-- (occ ≥ 0,95 và flow = 0) — cùng luật chất lượng với DSS (config/dss.yaml: data_quality).
CREATE OR REPLACE TABLE mart.detector_day_15min AS
WITH w AS (
    SELECT detector_key, date_key, n_intervals, n_err,
           sum_occ_clean  / NULLIF(n_occ_clean, 0)  AS occ_w,
           sum_flow_clean / NULLIF(n_flow_clean, 0) AS flow_w,
           least(n_occ_clean, n_flow_clean) AS n_clean
    FROM dw.fact_traffic_15min
), v AS (
    SELECT *, (n_clean >= 3 AND occ_w BETWEEN 0 AND 1 AND flow_w BETWEEN 0 AND {FLOW_MAX}
               AND NOT (occ_w >= 0.95 AND flow_w = 0)) AS is_valid
    FROM w
)
SELECT detector_key, date_key,
       count(*) AS n_windows,
       sum(CAST(is_valid AS INTEGER)) AS n_valid_windows,
       round(sum(n_err) * 100.0 / NULLIF(sum(n_intervals), 0), 2) AS error_pct,
       round(avg(occ_w) FILTER (WHERE is_valid), 4) AS mean_occ,
       round(avg(flow_w) FILTER (WHERE is_valid), 1) AS mean_flow
FROM v
GROUP BY detector_key, date_key;
