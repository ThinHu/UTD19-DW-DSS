CREATE OR REPLACE TABLE stg.measurements_raw AS
SELECT row_number() OVER () AS _row_id,
       lower(trim(city)) AS city,
       CAST(detid AS VARCHAR) AS detid,
       CAST(day AS VARCHAR) AS day,
       CAST("interval" AS VARCHAR) AS "interval",
       CAST(flow AS VARCHAR) AS flow,
       CAST(occ AS VARCHAR) AS occ,
       CAST(speed AS VARCHAR) AS speed,
       CAST(error AS VARCHAR) AS error
FROM read_csv('{DATA_RAW_DIR}/utd19_u.csv', header=true, all_varchar=true)
WHERE lower(trim(city)) IN ({CITY_IN})
{DATE_FILTER_SQL}
{LIMIT_SQL};