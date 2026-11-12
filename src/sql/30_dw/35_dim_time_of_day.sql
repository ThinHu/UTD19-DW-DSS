-- dim_time_of_day: hạt 3 phút (khớp time_key của fact gốc), phân cấp Buổi → Giờ → Khung 15 phút → Khoảng 3 phút.
CREATE OR REPLACE TABLE dw.dim_time_of_day AS
SELECT CAST(t AS INTEGER) AS time_key,
       CAST(t // 3600 AS TINYINT) AS hour,
       CAST((t % 3600) // 60 AS TINYINT) AS minute,
       CAST(t % 60 AS TINYINT) AS second,
       CAST(t // 900 AS SMALLINT) AS slot_15m,
       printf('%02d:%02d:%02d', t // 3600, (t % 3600) // 60, t % 60) AS time_label,
       CASE WHEN t // 3600 < 6 THEN 'Đêm' WHEN t // 3600 < 10 THEN 'Cao điểm sáng' WHEN t // 3600 < 15 THEN 'Giữa ngày'
            WHEN t // 3600 < 19 THEN 'Cao điểm chiều' ELSE 'Tối' END AS daypart
FROM generate_series(0, 86399, 180) AS s(t)   -- 480 khoảng đo 3 phút mỗi ngày
UNION ALL BY NAME SELECT -1 AS time_key, 'unknown' AS time_label, 'Không xác định' AS daypart;
