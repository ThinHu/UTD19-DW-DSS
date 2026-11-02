-- Kho siêu dữ liệu (metadata repository, Chương 2): siêu dữ liệu nghiệp vụ (ý nghĩa, hạt, nguồn, biến đổi)
-- nối với siêu dữ liệu kỹ thuật lấy từ catalog của DuckDB (số dòng, số cột). Chỉ liệt kê đối tượng đang tồn tại.
CREATE OR REPLACE TABLE etl.metadata_catalog AS
WITH biz(schema_name, table_name, layer, object_role, grain, source, transformation, description) AS (VALUES
  ('stg',  'measurements_raw',      'Staging', 'Bảng nguồn',  '1 dòng nguồn',                    'utd19_u.csv',                         'Nạp nguyên dạng chuỗi, lọc thành phố & khoảng ngày', 'Số đo 3 phút thô của UTD19'),
  ('stg',  'window_15min_raw',      'Staging', 'Bảng nguồn',  '1 dòng nguồn',                    'detector_window_15min.csv.gz',        'Nạp nguyên dạng chuỗi', 'Bản xuất khung 15 phút (chế độ --from-export)'),
  ('stg',  'detectors_raw',         'Staging', 'Bảng nguồn',  '1 detector',                      'detectors*.csv / location profile',  'Nạp nguyên dạng chuỗi, bổ sung cột thiếu', 'Thuộc tính detector thô'),
  ('stg',  'weather_daily',         'Staging', 'Nguồn ngoài', '1 ngày',                          'Open-Meteo archive (tùy chọn)',       'Nạp nguyên dạng', 'Thời tiết ngày ở Luzern'),
  ('clean','measurements',          'Clean',   'Bảng sạch',   'detector × ngày × 3 phút',        'stg.measurements_raw',               'Ép kiểu, chuẩn hóa occupancy, cách ly lỗi/trùng, bitmask DQ', 'Số đo đã làm sạch (chế độ --from-export: danh sách detector có số đo)'),
  ('clean','window_15min',          'Clean',   'Bảng sạch',   'detector × ngày × 15 phút',       'stg.window_15min_raw',               'Ép kiểu, cách ly slot ngoài phạm vi/trùng', 'Khung 15 phút đã làm sạch'),
  ('dw',   'fact_traffic_measurement','DW',    'Fact gốc',    'detector × ngày × khoảng 3 phút', 'clean.measurements',                 'Gán khóa thay thế', 'Fact giao thông hạt mịn nhất'),
  ('dw',   'fact_traffic_15min',    'DW',      'Fact tổng hợp','detector × ngày × khung 15 phút','fact gốc (hoặc bản xuất)',           'Gộp 5 khoảng đo, lưu thước đo cộng được', 'Fact phục vụ OLAP và DSS'),
  ('dw',   'dim_date',              'DW',      'Chiều',       '1 ngày',                          'Sinh lịch + danh sách ngày lễ',      'Năm→Quý→Tháng→Tuần→Ngày, loại ngày', 'Chiều thời gian (ngày)'),
  ('dw',   'dim_time_of_day',       'DW',      'Chiều',       '1 khoảng 3 phút',                 'Sinh',                               'Buổi→Giờ→Khung 15′→3′', 'Chiều thời gian trong ngày (hạt 3 phút)'),
  ('dw',   'dim_time_slot',         'DW',      'Chiều',       '1 khung 15 phút',                 'Sinh',                               'Buổi→Giờ→Khung', 'Chiều thời gian trong ngày (hạt 15 phút)'),
  ('dw',   'dim_detector',          'DW',      'Chiều',       '1 detector (SCD2-sẵn sàng)',      'clean.detectors',                    'Khóa thay thế, cờ chất lượng vị trí', 'Chiều cảm biến'),
  ('dw',   'dim_road_class',        'DW',      'Chiều',       '1 loại đường OSM',                'clean.detectors.fclass',             'Nhóm đường → loại đường', 'Chiều loại đường'),
  ('dw',   'dim_link',              'DW',      'Chiều',       '1 đoạn đường',                    'clean.links',                        'Hình học WKT, độ dài haversine', 'Chiều đoạn đường'),
  ('dw',   'dim_city',              'DW',      'Chiều',       '1 thành phố',                     'Cấu hình',                           '—', 'Chiều thành phố'),
  ('dw',   'dim_weather',           'DW',      'Chiều (outrigger)', '1 ngày',                    'stg.weather_daily',                  'Phân nhóm mưa/tuyết, dải nhiệt độ', 'Thời tiết theo ngày'),
  ('mart', 'dss_detector_window',   'Mart',    'Data mart DSS','detector × ngày × 15 phút',      'dw.fact_traffic_15min',              'Tính lại trung bình = tổng / số đếm', 'Đầu vào của engine DSS'),
  ('mart', 'detector_day_15min',    'Mart',    'Snapshot',    'detector × ngày',                 'dw.fact_traffic_15min',              'Số khung hợp lệ, % lỗi (luật DQ của DSS)', 'Độ phủ & chất lượng theo ngày'),
  ('mart', 'detector_day_coverage', 'Mart',    'Snapshot',    'detector × ngày',                 'fact gốc 3 phút',                    'Độ phủ so với 480 khoảng/ngày', 'Độ phủ dữ liệu'),
  ('mart', 'mfd_city_interval',     'Mart',    'Data mart',   'thành phố × ngày × 3 phút',       'fact gốc 3 phút',                    'Trung bình có trọng số theo chiều dài làn', 'Biểu đồ cơ bản vĩ mô (MFD)'),
  ('mart', 'congestion_kpi',        'Mart',    'Data mart',   'thành phố × ngày × giờ',          'fact gốc 3 phút',                    'Tỷ lệ mẫu occupancy > 30%', 'KPI tắc nghẽn theo giờ'),
  ('etl',  'run_log',               'ETL',     'Nhật ký',     '1 bước ETL',                      'Pipeline',                           '—', 'Lịch sử chạy ETL (history of extracts)'),
  ('etl',  'quarantine',            'ETL',     'Cách ly',     '1 dòng bị loại',                  'Bước clean',                         '—', 'Dòng lỗi bị cách ly kèm luật'),
  ('etl',  'reconciliation',        'ETL',     'Đối soát',    '1 phép kiểm',                     'Bước checks',                        '—', 'Kết quả đối soát toàn vẹn'),
  ('etl',  'load_info',             'ETL',     'Siêu dữ liệu','1 lần nạp',                       'Pipeline',                           '—', 'Chế độ nạp, nguồn, thời điểm')
)
SELECT b.layer, b.schema_name || '.' || b.table_name AS object_name, b.object_role, b.grain, b.source,
       b.transformation, b.description,
       t.estimated_size AS row_count, t.column_count,
       CAST(now() AS TIMESTAMP) AS refreshed_at
FROM biz b
JOIN duckdb_tables() t ON t.schema_name = b.schema_name AND t.table_name = b.table_name
ORDER BY CASE b.layer WHEN 'Staging' THEN 1 WHEN 'Clean' THEN 2 WHEN 'DW' THEN 3 WHEN 'Mart' THEN 4 ELSE 5 END, object_name;
