CREATE OR REPLACE TABLE dw.dim_city AS
SELECT CAST(1 AS SMALLINT) AS city_key, 
       'luzern' AS citycode, 
       'Luzern' AS city_name, 
       'Switzerland' AS country, 
       'Europe/Zurich' AS timezone,
       CAST(900 AS SMALLINT) AS interval_length_s, 
       'fraction' AS occupancy_scale
UNION ALL BY NAME
SELECT CAST(0 AS SMALLINT) AS city_key, 'unknown' AS citycode, 'Unknown' AS city_name, 'Unknown' AS country, 'Unknown' AS timezone, 'fraction' AS occupancy_scale;