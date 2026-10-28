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

CREATE OR REPLACE TABLE clean.city_params AS
SELECT city, 
       quantile_cont(occ_raw, 0.99) FILTER (WHERE isfinite(occ_raw)) AS occ_p99,
       CASE WHEN quantile_cont(occ_raw, 0.99) FILTER (WHERE isfinite(occ_raw)) > 1.5 THEN 'percent' ELSE 'fraction' END AS occupancy_scale
FROM clean.measurements_typed GROUP BY city;

CREATE OR REPLACE TABLE clean.measurements AS
WITH ranked AS (
    SELECT t.*, p.occupancy_scale,
           count(*) OVER w AS dup_n,
           row_number() OVER (PARTITION BY t.city, t.detid, t.day_date, t.interval_raw ORDER BY _row_id DESC) AS rn
    FROM clean.measurements_typed t JOIN clean.city_params p USING (city)
    WHERE day_date IS NOT NULL AND detid IS NOT NULL
    WINDOW w AS (PARTITION BY t.city, t.detid, t.day_date, t.interval_raw)
), cl AS (
    SELECT *, 
           CASE WHEN flow_raw < 0 OR NOT isfinite(flow_raw) THEN NULL ELSE flow_raw END AS flow_clean,
           CASE WHEN occ_raw < 0 OR NOT isfinite(occ_raw) THEN NULL
                WHEN occupancy_scale = 'percent' THEN occ_raw / 100.0 ELSE occ_raw END AS occ_clean
    FROM ranked WHERE rn = 1
)
SELECT city, detid, day_date AS day_adj, interval_raw AS interval_adj, 
       coalesce(error_flag, 0) AS error_flag, 
       CAST(flow_clean AS FLOAT) AS flow_clean, 
       CAST(occ_clean AS FLOAT) AS occ_clean,
       dup_n, 
       CAST(
         (CASE WHEN flow_raw < 0 THEN 1 ELSE 0 END) +
         (CASE WHEN flow_raw > {FLOW_MAX} THEN 2 ELSE 0 END) +
         (CASE WHEN occ_raw < 0 THEN 4 ELSE 0 END) +
         (CASE WHEN occ_clean > 1 THEN 8 ELSE 0 END) +
         (CASE WHEN dup_n > 1 THEN 1024 ELSE 0 END)
       AS INTEGER) AS dq_flag, 
       _row_id
FROM cl;