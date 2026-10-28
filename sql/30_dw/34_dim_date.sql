CREATE OR REPLACE TABLE dw.dim_date AS
WITH cal AS (
    SELECT CAST(g AS DATE) AS full_date 
    FROM generate_series(DATE '2015-01-01', DATE '2017-12-31', INTERVAL 1 DAY) AS t(g)
)
SELECT CAST(strftime(full_date, '%Y%m%d') AS INTEGER) AS date_key, 
       full_date, 
       strftime(full_date, '%Y-%m-%d') AS day_raw,
       CAST(year(full_date) AS SMALLINT) AS year, 
       CAST(month(full_date) AS TINYINT) AS month, 
       CAST(day(full_date) AS TINYINT) AS day_of_month,
       CAST(isodow(full_date) AS TINYINT) AS day_of_week, 
       dayname(full_date) AS day_name, 
       (isodow(full_date) >= 6) AS is_weekend, 
       FALSE AS is_public_holiday
FROM cal
UNION ALL BY NAME SELECT 0 AS date_key, 'unknown' AS day_raw, FALSE AS is_weekend, FALSE AS is_public_holiday;