-- dim_date: phân cấp Năm → Quý → Tháng → Tuần ISO → Ngày, cộng các thuộc tính lịch dùng cho OLAP và DSS.
-- day_type (WD/SAT/SUN) là cùng quy tắc với baseline của DSS: lễ được xếp như Chủ nhật.
CREATE OR REPLACE TABLE dw.dim_date AS
WITH cal AS (
    SELECT CAST(g AS DATE) AS full_date
    FROM generate_series(DATE '{DIM_DATE_START}', DATE '{DIM_DATE_END}', INTERVAL 1 DAY) AS t(g)
), attr AS (
    SELECT full_date,
           full_date IN ({HOLIDAYS_IN})     AS is_public_holiday,
           full_date IN ({SPECIAL_DAYS_IN}) AS is_special_day
    FROM cal
)
SELECT CAST(strftime(full_date, '%Y%m%d') AS INTEGER) AS date_key,
       full_date,
       strftime(full_date, '%Y-%m-%d') AS day_raw,
       CAST(year(full_date) AS SMALLINT) AS year,
       CAST(quarter(full_date) AS TINYINT) AS quarter,
       'Q' || quarter(full_date) || '/' || year(full_date) AS quarter_label,
       CAST(month(full_date) AS TINYINT) AS month,
       'Tháng ' || month(full_date) AS month_name,
       strftime(full_date, '%Y-%m') AS year_month,
       CAST(weekofyear(full_date) AS TINYINT) AS iso_week,
       CAST(day(full_date) AS TINYINT) AS day_of_month,
       CAST(isodow(full_date) AS TINYINT) AS day_of_week,
       dayname(full_date) AS day_name,
       ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'][isodow(full_date)] AS day_name_vn,
       (isodow(full_date) >= 6) AS is_weekend,
       is_public_holiday,
       is_special_day,
       CASE WHEN is_public_holiday OR isodow(full_date) = 7 THEN 'SUN'
            WHEN isodow(full_date) = 6 THEN 'SAT' ELSE 'WD' END AS day_type,
       CASE WHEN is_public_holiday OR isodow(full_date) = 7 THEN 'Chủ nhật / Lễ'
            WHEN isodow(full_date) = 6 THEN 'Thứ Bảy' ELSE 'Ngày làm việc' END AS day_type_label
FROM attr
UNION ALL BY NAME
SELECT 0 AS date_key, 'unknown' AS day_raw, 'Unknown' AS day_type, 'Không xác định' AS day_type_label,
       FALSE AS is_weekend, FALSE AS is_public_holiday, FALSE AS is_special_day;
