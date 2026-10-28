CREATE OR REPLACE TABLE dw.dim_time_of_day AS
SELECT CAST(t AS INTEGER) AS time_key, 
       CAST(t // 3600 AS TINYINT) AS hour, 
       CAST((t % 3600) // 60 AS TINYINT) AS minute, 
       CAST(t % 60 AS TINYINT) AS second,
       printf('%02d:%02d:%02d', t // 3600, (t % 3600) // 60, t % 60) AS time_label,
       CASE WHEN t // 3600 < 6 THEN 'Night' WHEN t // 3600 < 10 THEN 'Morning peak' WHEN t // 3600 < 15 THEN 'Midday'
            WHEN t // 3600 < 19 THEN 'Afternoon peak' ELSE 'Evening' END AS daypart
FROM generate_series(0, 86399, 900) AS s(t)
UNION ALL BY NAME SELECT -1 AS time_key, 'unknown' AS time_label, 'Unknown' AS daypart;