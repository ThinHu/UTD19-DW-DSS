-- Làm sạch bản xuất khung 15 phút: ép kiểu, cách ly dòng không đọc được / slot ngoài [0, 95] / trùng khóa.
CREATE OR REPLACE TABLE clean._win_ranked AS
WITH typed AS (
    SELECT _row_id,
           'luzern' AS city,
           NULLIF(trim(detid), '') AS detid,
           trim("day") AS day_raw,
           TRY_CAST(trim("day") AS DATE) AS day_date,
           CASE WHEN TRY_CAST(slot AS DOUBLE) = trunc(TRY_CAST(slot AS DOUBLE)) THEN TRY_CAST(slot AS INTEGER) END AS slot,
           CASE WHEN TRY_CAST(n AS DOUBLE) = trunc(TRY_CAST(n AS DOUBLE)) THEN TRY_CAST(n AS INTEGER) END AS n, CASE WHEN TRY_CAST(n_err AS DOUBLE) = trunc(TRY_CAST(n_err AS DOUBLE)) THEN TRY_CAST(n_err AS INTEGER) END AS n_err,
           CASE WHEN TRY_CAST(n_occ AS DOUBLE) = trunc(TRY_CAST(n_occ AS DOUBLE)) THEN TRY_CAST(n_occ AS INTEGER) END AS n_occ, CASE WHEN TRY_CAST(n_flow AS DOUBLE) = trunc(TRY_CAST(n_flow AS DOUBLE)) THEN TRY_CAST(n_flow AS INTEGER) END AS n_flow,
           CASE WHEN TRY_CAST(n_flow0 AS DOUBLE) = trunc(TRY_CAST(n_flow0 AS DOUBLE)) THEN TRY_CAST(n_flow0 AS INTEGER) END AS n_flow0,
           CASE WHEN TRY_CAST(n_occ_clean AS DOUBLE) = trunc(TRY_CAST(n_occ_clean AS DOUBLE)) THEN TRY_CAST(n_occ_clean AS INTEGER) END AS n_occ_clean, CASE WHEN TRY_CAST(n_flow_clean AS DOUBLE) = trunc(TRY_CAST(n_flow_clean AS DOUBLE)) THEN TRY_CAST(n_flow_clean AS INTEGER) END AS n_flow_clean,
           TRY_CAST(mean_occ_all AS DOUBLE) AS mean_occ_all, TRY_CAST(mean_flow_all AS DOUBLE) AS mean_flow_all,
           TRY_CAST(mean_occ_clean AS DOUBLE) AS mean_occ_clean, TRY_CAST(mean_flow_clean AS DOUBLE) AS mean_flow_clean
    FROM stg.window_15min_raw
)
SELECT *,
       row_number() OVER (PARTITION BY detid, day_date, slot ORDER BY _row_id DESC) AS rn,
       CASE WHEN detid IS NULL OR day_date IS NULL OR slot IS NULL OR n IS NULL THEN 'RULE_PARSE'
            WHEN slot < 0 OR slot > 95 THEN 'RULE_INTERVAL_OOR'
            WHEN NOT aggregates_valid THEN 'RULE_AGGREGATE_INVALID' END AS reject_rule
FROM (
    SELECT *, coalesce(
        n BETWEEN 1 AND 5 AND n_err BETWEEN 0 AND n
        AND n_occ BETWEEN 0 AND n AND n_flow BETWEEN 0 AND n
        AND n_flow0 BETWEEN 0 AND n_flow
        AND n_occ_clean BETWEEN 0 AND least(n_occ, n - n_err)
        AND n_flow_clean BETWEEN 0 AND least(n_flow, n - n_err)
        AND ((n_occ = 0 AND mean_occ_all IS NULL) OR (n_occ > 0 AND isfinite(mean_occ_all) AND mean_occ_all BETWEEN 0 AND 1))
        AND ((n_flow = 0 AND mean_flow_all IS NULL) OR (n_flow > 0 AND isfinite(mean_flow_all) AND mean_flow_all BETWEEN 0 AND {FLOW_MAX}))
        AND ((n_occ_clean = 0 AND mean_occ_clean IS NULL) OR (n_occ_clean > 0 AND isfinite(mean_occ_clean) AND mean_occ_clean BETWEEN 0 AND 1))
        AND ((n_flow_clean = 0 AND mean_flow_clean IS NULL) OR (n_flow_clean > 0 AND isfinite(mean_flow_clean) AND mean_flow_clean BETWEEN 0 AND {FLOW_MAX}))
        , FALSE) AS aggregates_valid
    FROM typed
);

INSERT INTO etl.quarantine
SELECT 'window_15min', reject_rule, city, detid, day_raw, slot, _row_id,
       CASE reject_rule WHEN 'RULE_PARSE' THEN 'Không đọc được detector / ngày / slot / n'
                        ELSE 'Slot ngoài [0, 95] (khoảng đo 86400 s bị cuộn sang ngày sau)' END
FROM clean._win_ranked WHERE reject_rule IS NOT NULL;

INSERT INTO etl.quarantine
SELECT 'window_15min', 'RULE_DUPLICATE', city, detid, day_raw, slot, _row_id, 'Trùng (detid, day, slot) — giữ dòng nạp sau cùng'
FROM clean._win_ranked WHERE reject_rule IS NULL AND rn > 1;

CREATE OR REPLACE TABLE clean.window_15min AS
SELECT * EXCLUDE (rn, reject_rule, aggregates_valid) FROM clean._win_ranked WHERE reject_rule IS NULL AND rn = 1;
DROP TABLE clean._win_ranked;

-- Danh sách (city, detid) có số đo — để dim_detector sinh khóa cho detector thiếu hồ sơ (is_inferred)
CREATE OR REPLACE TABLE clean.measurements AS SELECT DISTINCT city, detid FROM clean.window_15min;
