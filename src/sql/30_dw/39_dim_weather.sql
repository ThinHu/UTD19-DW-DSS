-- dim_weather: thời tiết theo ngày ở Luzern (nguồn ngoài, tùy chọn — python -m utd19_dw.weather).
-- Một dòng cho mỗi ngày của dim_date (khóa = date_key, "outrigger" của chiều thời gian).
-- Ngày không có dữ liệu thời tiết nhận nhóm 'Không có dữ liệu' để OLAP vẫn slice được.
CREATE OR REPLACE TABLE dw.dim_weather AS
WITH w AS (
    SELECT TRY_CAST("date" AS DATE) AS full_date,
           TRY_CAST(temperature_2m_mean AS DOUBLE) AS temp_mean_c,
           TRY_CAST(precipitation_sum AS DOUBLE) AS precip_mm,
           TRY_CAST(snowfall_sum AS DOUBLE) AS snow_cm,
           TRY_CAST(precipitation_hours AS DOUBLE) AS precip_hours
    FROM stg.weather_daily
)
SELECT d.date_key,
       w.temp_mean_c, w.precip_mm, w.snow_cm, w.precip_hours,
       CASE WHEN w.full_date IS NULL THEN 'Không có dữ liệu'
            WHEN coalesce(w.snow_cm, 0) >= 1 THEN 'Tuyết'
            WHEN coalesce(w.precip_mm, 0) >= 10 THEN 'Mưa to'
            WHEN coalesce(w.precip_mm, 0) >= 1 THEN 'Mưa'
            ELSE 'Khô' END AS weather_class,
       CASE WHEN w.full_date IS NULL THEN NULL
            WHEN w.temp_mean_c < 0 THEN 'Dưới 0 °C' WHEN w.temp_mean_c < 10 THEN '0–10 °C'
            WHEN w.temp_mean_c < 20 THEN '10–20 °C' ELSE '≥ 20 °C' END AS temp_band,
       (w.full_date IS NOT NULL) AS has_weather
FROM dw.dim_date d
LEFT JOIN w ON w.full_date = d.full_date
WHERE d.date_key > 0;
