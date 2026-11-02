-- Làm sạch bản xuất khung 15 phút: ép kiểu, cách ly dòng không đọc được / slot ngoài [0, 95] / trùng khóa.
CREATE OR REPLACE TABLE clean._win_ranked AS
WITH typed AS (
    SELECT _row_id,
           'luzern' AS city,
           NULLIF(trim(detid), '') AS detid,
           trim("day") AS day_raw,
           TRY_CAST(trim("day") AS DATE) AS day_date,
           TRY_CAST(slot AS INTEGER) AS slot,
           TRY_CAST(n AS INTEGER) AS n, TRY_CAST(n_err AS INTEGER) AS n_err,
           TRY_CAST(n_occ AS INTEGER) AS n_occ, TRY_CAST(n_flow AS INTEGER) AS n_flow,
           TRY_CAST(n_flow0 AS INTEGER) AS n_flow0,
           TRY_CAST(n_occ_clean AS INTEGER) AS n_occ_clean, TRY_CAST(n_flow_clean AS INTEGER) AS n_flow_clean,
           TRY_CAST(mean_occ_all AS DOUBLE) AS mean_occ_all, TRY_CAST(mean_flow_all AS DOUBLE) AS mean_flow_all,
           TRY_CAST(mean_occ_clean AS DOUBLE) AS mean_occ_clean, TRY_CAST(mean_flow_clean AS DOUBLE) AS mean_flow_clean
    FROM stg.window_15min_raw
)
SELECT *,
       row_number() OVER (PARTITION BY detid, day_date, slot ORDER BY _row_id DESC) AS rn,
       CASE WHEN detid IS NULL OR day_date IS NULL OR slot IS NULL OR n IS NULL THEN 'RULE_PARSE'
            WHEN slot < 0 OR slot > 95 THEN 'RULE_INTERVAL_OOR' END AS reject_rule
FROM typed;

INSERT INTO etl.quarantine
SELECT 'window_15min', reject_rule, city, detid, day_raw, slot, _row_id,
       CASE reject_rule WHEN 'RULE_PARSE' THEN 'Không đọc được detector / ngày / slot / n'
                        ELSE 'Slot ngoài [0, 95] (khoảng đo 86400 s bị cuộn sang ngày sau)' END
FROM clean._win_ranked WHERE reject_rule IS NOT NULL;

INSERT INTO etl.quarantine
SELECT 'window_15min', 'RULE_DUPLICATE', city, detid, day_raw, slot, _row_id, 'Trùng (detid, day, slot) — giữ dòng nạp sau cùng'
FROM clean._win_ranked WHERE reject_rule IS NULL AND rn > 1;

CREATE OR REPLACE TABLE clean.window_15min AS
SELECT * EXCLUDE (rn, reject_rule) FROM clean._win_ranked WHERE reject_rule IS NULL AND rn = 1;
DROP TABLE clean._win_ranked;

-- Danh sách (city, detid) có số đo — để dim_detector sinh khóa cho detector thiếu hồ sơ (is_inferred)
CREATE OR REPLACE TABLE clean.measurements AS SELECT DISTINCT city, detid FROM clean.window_15min;
