-- dim_time_slot: chiều thời gian ở hạt 15 phút (96 khung/ngày) cho fact tổng hợp dw.fact_traffic_15min.
-- Cùng phân cấp với dim_time_of_day (Buổi → Giờ → Khung) nên roll-up nhất quán giữa hai mức hạt.
CREATE OR REPLACE TABLE dw.dim_time_slot AS
SELECT CAST(s AS SMALLINT) AS slot_key,
       CAST(s // 4 AS TINYINT) AS hour,
       CAST((s % 4) * 15 AS TINYINT) AS minute,
       printf('%02d:%02d', s // 4, (s % 4) * 15) AS slot_label,
       printf('%02d:00–%02d:59', s // 4, s // 4) AS hour_label,
       CASE WHEN s // 4 < 6 THEN 'Đêm' WHEN s // 4 < 10 THEN 'Cao điểm sáng' WHEN s // 4 < 15 THEN 'Giữa ngày'
            WHEN s // 4 < 19 THEN 'Cao điểm chiều' ELSE 'Tối' END AS daypart,
       CASE WHEN s // 4 < 6 THEN 1 WHEN s // 4 < 10 THEN 2 WHEN s // 4 < 15 THEN 3
            WHEN s // 4 < 19 THEN 4 ELSE 5 END AS daypart_order,
       (s // 4 BETWEEN 7 AND 8) OR (s // 4 BETWEEN 16 AND 18) AS is_peak
FROM generate_series(0, 95) AS t(s);
