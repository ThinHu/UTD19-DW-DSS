-- dim_city: chiều thành phố (khóa 0 = unknown). Luzern đo mỗi 180 giây, occupancy theo thang phân số 0–1.
CREATE OR REPLACE TABLE dw.dim_city AS
SELECT CAST(1 AS SMALLINT) AS city_key,
       'luzern' AS citycode,
       'Luzern' AS city_name,
       'Switzerland' AS country,
       'Europe/Zurich' AS timezone,
       CAST(180 AS SMALLINT) AS interval_length_s,  -- UTD19 Luzern đo mỗi 3 phút
       'fraction' AS occupancy_scale
UNION ALL BY NAME
SELECT CAST(0 AS SMALLINT) AS city_key, 'unknown' AS citycode, 'Unknown' AS city_name, 'Unknown' AS country, 'Unknown' AS timezone, 'fraction' AS occupancy_scale;
