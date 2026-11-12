-- Làm sạch số đo: ép kiểu, chuẩn hóa thang occupancy, xử lý interval ngoài ngày, cách ly dòng lỗi,
-- khử trùng lặp và gắn bitmask chất lượng (bit khớp config/dq_rules.yaml).
CREATE OR REPLACE TABLE clean.measurements_typed AS
SELECT _row_id,
       lower(trim(city)) AS city,
       NULLIF(regexp_replace(trim(detid), '\.0$', ''), '') AS detid,
       trim(day) AS day_raw,
       TRY_CAST(trim(day) AS DATE) AS day_date,
       TRY_CAST("interval" AS DOUBLE) AS interval_raw,
       TRY_CAST(flow AS DOUBLE) AS flow_raw,
       TRY_CAST(occ AS DOUBLE) AS occ_raw,
       TRY_CAST(error AS TINYINT) AS error_flag
FROM stg.measurements_raw;

-- Thang occupancy (phân số 0–1 hay phần trăm 0–100) suy từ p99 của các khoảng đo KHÔNG lỗi và bỏ sentinel (≥ 900),
-- để giá trị 999,99 trong khoảng đo lỗi không làm cả thành phố bị hiểu nhầm là thang phần trăm.
CREATE OR REPLACE TABLE clean.city_params AS
SELECT city,
       quantile_cont(occ_raw, 0.99) FILTER (WHERE isfinite(occ_raw) AND occ_raw < 900 AND coalesce(error_flag, 0) = 0) AS occ_p99,
       CASE WHEN quantile_cont(occ_raw, 0.99) FILTER (WHERE isfinite(occ_raw) AND occ_raw < 900 AND coalesce(error_flag, 0) = 0) > {OCC_PERCENT_THRESHOLD}
            THEN 'percent' ELSE 'fraction' END AS occupancy_scale
FROM clean.measurements_typed GROUP BY city;

-- interval_oor_mode = 'rollover': interval trong [86400, 172800) chuyển sang ngày hôm sau; 'reject': cách ly
CREATE OR REPLACE TABLE clean._meas_ranked AS
WITH adj AS (
    SELECT t.*, p.occupancy_scale,
           CASE WHEN {INTERVAL_OOR_MODE} = 'rollover' AND t.interval_raw >= 86400 AND t.interval_raw < 172800
                THEN t.day_date + 1 ELSE t.day_date END AS day_adj,
           CASE WHEN {INTERVAL_OOR_MODE} = 'rollover' AND t.interval_raw >= 86400 AND t.interval_raw < 172800
                THEN t.interval_raw - 86400 ELSE t.interval_raw END AS interval_adj
    FROM clean.measurements_typed t JOIN clean.city_params p USING (city)
)
SELECT *,
       count(*) OVER w AS dup_n,
       row_number() OVER (PARTITION BY city, detid, day_adj, interval_adj ORDER BY _row_id DESC) AS rn,
       CASE WHEN day_adj IS NULL OR detid IS NULL OR interval_adj IS NULL THEN 'RULE_PARSE'
            WHEN NOT isfinite(interval_adj) OR interval_adj < 0 OR interval_adj >= 86400 THEN 'RULE_INTERVAL_OOR'
            WHEN interval_adj % 180 <> 0 THEN 'RULE_INTERVAL_ALIGNMENT' END AS reject_rule
FROM adj
WINDOW w AS (PARTITION BY city, detid, day_adj, interval_adj);

INSERT INTO etl.quarantine
SELECT 'measurements', reject_rule, city, detid, day_raw, interval_raw, _row_id,
       CASE reject_rule WHEN 'RULE_PARSE' THEN 'Không đọc được ngày / detector / interval'
                        ELSE 'Interval ngoài [0, 86400) giây' END
FROM clean._meas_ranked WHERE reject_rule IS NOT NULL;

INSERT INTO etl.quarantine
SELECT 'measurements', 'RULE_DUPLICATE', city, detid, day_raw, interval_raw, _row_id,
       'Trùng (city, detid, day, interval) — giữ dòng nạp sau cùng'
FROM clean._meas_ranked WHERE reject_rule IS NULL AND rn > 1;

CREATE OR REPLACE TABLE clean.measurements AS
WITH cl AS (
    SELECT *,
           CASE WHEN flow_raw < 0 OR NOT isfinite(flow_raw) OR flow_raw > {FLOW_MAX} THEN NULL ELSE flow_raw END AS flow_clean,
           CASE WHEN occ_raw < 0 OR NOT isfinite(occ_raw) THEN NULL
                WHEN occupancy_scale = 'percent' THEN occ_raw / 100.0 ELSE occ_raw END AS occ_clean
    FROM clean._meas_ranked
    WHERE reject_rule IS NULL AND rn = 1
)
SELECT city, detid, day_adj, interval_adj,
       coalesce(error_flag, 0) AS error_flag,
       CAST(flow_clean AS FLOAT) AS flow_clean,
       CAST(CASE WHEN occ_clean > 1 THEN NULL ELSE occ_clean END AS FLOAT) AS occ_clean,
       dup_n,
       CAST(
         (CASE WHEN flow_raw IS NULL THEN 1 ELSE 0 END) +                      -- RULE_NULL_FLOW
         (CASE WHEN flow_raw < 0 THEN 2 ELSE 0 END) +                          -- RULE_NEGATIVE_FLOW
         (CASE WHEN flow_raw > {FLOW_MAX} THEN 4 ELSE 0 END) +                 -- RULE_FLOW_MAX
         (CASE WHEN occ_raw < 0 OR occ_clean > 1 THEN 16 ELSE 0 END) +         -- RULE_OCC_OOR
         (CASE WHEN (flow_raw IS NOT NULL AND NOT isfinite(flow_raw)) OR (occ_raw IS NOT NULL AND NOT isfinite(occ_raw)) THEN 64 ELSE 0 END) + -- RULE_NONFINITE
         (CASE WHEN dup_n > 1 THEN 1024 ELSE 0 END)                            -- RULE_DUPLICATE (đã giữ 1 dòng)
       AS INTEGER) AS dq_flag,
       _row_id
FROM cl;

DROP TABLE clean._meas_ranked;
