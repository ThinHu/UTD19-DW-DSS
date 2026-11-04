# Đánh giá ETL/DW, Data Quality và Query Performance

Thời điểm (UTC): 2026-11-04T08:18:02.200229+00:00

DW: `D:\Học kì 261\DW&DSS\UTD19-DW-DSS\data\work\utd19.duckdb`. Chế độ: `full_3min`.

## Correctness và reconciliation

Correctness: **PASS**; DQ được mô tả riêng, chưa đặt ngưỡng chấp nhận; performance chưa có SLA.  24/24 checks PASS.

| Bảng | Số dòng |
|---|---:|
| dw.dim_detector | 159 |
| dw.fact_traffic_15min | 2,633,638 |
| mart.dss_detector_window | 2,633,638 |
| etl.quarantine | 27,454 |
| dw.fact_traffic_measurement | 13,138,969 |

Đối soát gồm bảo toàn dòng, FK/grain/khóa chiều, clean → fact theo từng bản ghi và khóa nghiệp vụ, fact 3 → 15 phút theo từng nhóm, giá trị mart DSS và miền giá trị.

## Data Quality

Khoảng đánh giá: 2015-01-01–2015-06-30 (181 ngày).

| Chỉ tiêu | Giá trị |
|---|---:|
| Quarantine / staging | 27,454 / 13,166,423 (0.2085%) |
| Detector có số đo | 158 |
| Độ phủ khoảng đo | 95.716% |
| Độ hiện diện khung 15 phút | 95.9288% |
| Khung hợp lệ / khung hiện diện | 66.2412% |
| Khung hợp lệ / khung kỳ vọng | 63.5444% |
| Khoảng đo có error_flag | 35.7478% |
| Thiếu flow sau làm sạch | 0.8661% |
| Thiếu occupancy sau làm sạch | 0.4683% |

Coverage dùng detector từng có số đo × toàn bộ ngày cấu hình; không suy ra lịch vận hành cảm biến. Flag có thể chồng lấp. Quarantine dùng staging đã lọc city/ngày, không dùng toàn bộ CSV.

Khung hợp lệ theo mart.detector_day_15min: ít nhất 3 khoảng clean, mean trong miền và không thuộc trạng thái occ ≥ 0,95 với flow = 0. Đây là định nghĩa DQ của DW hiện tại.

### Theo tháng

| Tháng | Khoảng đo | Lỗi cảm biến (%) | Flow có trọng số | Occupancy có trọng số |
|---|---:|---:|---:|---:|
| 2015-01 | 2,346,079 | 39.3168 | 321.4239 | 0.063832 |
| 2015-02 | 2,119,067 | 39.0961 | 318.474 | 0.064213 |
| 2015-03 | 2,283,786 | 34.4604 | 334.9197 | 0.073208 |
| 2015-04 | 2,112,352 | 34.4118 | 330.0632 | 0.071538 |
| 2015-05 | 2,172,120 | 31.1361 | 333.5031 | 0.076887 |
| 2015-06 | 2,105,565 | 35.8957 | 334.3394 | 0.075557 |

### Cờ DQ thực sự được gán trên fact 3 phút

| Rule | Số dòng | % fact |
|---|---:|---:|
| RULE_NULL_FLOW | 0 | 0.0 |
| RULE_NEGATIVE_FLOW | 0 | 0.0 |
| RULE_FLOW_MAX | 113,800 | 0.8661 |
| RULE_OCC_OOR | 61,535 | 0.4683 |
| RULE_DUPLICATE | 0 | 0.0 |
| RULE_NONFINITE | 0 | 0.0 |

Các rule quarantine không phải cờ giữ trong fact; RULE_SPEED_OOR chưa áp dụng cho nguồn này. Không diễn giải chúng là đã kiểm tra và có 0 lỗi.

### Detector có tỷ lệ error_flag cao nhất

| Detector | Khoảng đo | Error (%) | Coverage (%) |
|---|---:|---:|---:|
| ig11FD100_D37 | 86,544 | 100.0 | 99.6133 |
| ig11FD100_D39 | 86,544 | 100.0 | 99.6133 |
| ig11FD100_D4 | 79,764 | 100.0 | 91.8094 |
| ig11FD100_D44 | 86,544 | 100.0 | 99.6133 |
| ig11FD103_D6 | 86,596 | 100.0 | 99.6731 |
| ig11FD104_D42 | 86,614 | 100.0 | 99.6938 |
| ig11FD104_D43 | 86,614 | 100.0 | 99.6938 |
| ig11FD104_D44 | 86,614 | 100.0 | 99.6938 |
| ig11FD105_D7 | 86,614 | 100.0 | 99.6938 |
| ig11FD109_D16 | 86,587 | 100.0 | 99.6628 |
| ig11FD110_D33 | 86,614 | 100.0 | 99.6938 |
| ig11FD111_D26 | 86,615 | 100.0 | 99.695 |
| ig11FD116_D34 | 86,615 | 100.0 | 99.695 |
| ig11FD117_D12 | 86,614 | 100.0 | 99.6938 |
| ig11FD117_D20 | 86,614 | 100.0 | 99.6938 |

Hồ sơ detector: `{"detectors": 158, "inferred": 0, "location_issues": 0, "geometry_issues": 0, "unmatched_links": 0}`.

## Hiệu năng truy vấn

Python 3.13.5; DuckDB 2.0.0; Windows-11-10.0.22631-SP0; threads=4; memory_limit=3.7 GiB; DB=685.3 MiB.

Mỗi truy vấn có 1 lượt đầu rồi 15 lượt đo tuần tự; đo execute + fetchall. Đây là warm-cache, một client; chưa đo tải đồng thời hoặc cold-cache. p95 dùng nội suy tuyến tính; mẫu nhỏ chỉ mang tính mô tả.

| Query | Nội dung | Dòng trả về | Median (ms) | p95 (ms) |
|---|---|---:|---:|---:|
| Q1 | Tra cứu detector/ngày | 96 | 1.958 | 2.096 |
| Q2 | Tổng hợp ngày từ fact 15 phút | 181 | 15.751 | 18.220 |
| Q3 | Join chiều và rollup tháng/loại đường | 24 | 37.872 | 41.835 |
| Q4 | Cửa sổ DSS toàn thành phố | 147 | 1.790 | 2.267 |
| Q5 | DQ theo tháng | 6 | 3.076 | 3.411 |
| Q6 | View theo tháng/detector | 2880 | 8.426 | 11.410 |
| Q7 | Tổng hợp ngày từ fact 3 phút | 181 | 129.404 | 144.829 |
| Q8 | View cùng tập kết quả, lọc khoảng date_key | 2880 | 7.183 | 9.281 |

Trong lần đo này, rollup ngày từ fact 15 phút nhanh hơn fact 3 phút 8.22 lần (median, Q7/Q2). Hai truy vấn dùng cùng định nghĩa error_flag=0 và mean có trọng số; đối chiếu giá trị: `{'dates_compared': 181, 'differences': 0, 'max_flow_error': 0.0, 'max_occupancy_error': 0.0}`.

Đổi bộ lọc date_key//100 sang BETWEEN trên cột date_key: Q6/Q8=1.17 lần theo median; cùng tập kết quả: True.

### Thử index trên bản sao tạm

Candidate: `INDEX(detector_key,date_key)`; copy table=193.495ms; build index=350.577ms.

Median trước/sau: 2.079/2.006ms; ratio=1.04; index scan quan sát được: False; kết quả giống nhau: True.

Một thứ tự before→after trên bảng tạm, không phải cold-cache/concurrent benchmark; chi phí RAM/index và tốc độ ETL chưa được benchmark.

Kết quả này chưa đủ để thêm index fact mặc định; phải xét plan và nhiều workload, không chỉ một lần đo thời gian.

Lần ETL thành công gần nhất: 93.438s (lịch sử một lần chạy, không phải benchmark nhiều lần).

| Bước tốn thời gian nhất | Giây |
|---|---:|
| 10_staging/12_stg_measurements | 70.854 |
| 20_clean/22_clean_measurements | 13.004 |
| 30_dw/36_fact_traffic_measurement | 2.784 |
| 30_dw/38_fact_traffic_15min | 1.240 |
| 60_validation/61_full | 0.847 |

## Nhận định và giới hạn

- Checks PASS xác nhận các bất biến được kiểm thử; không chứng minh cảm biến đo đúng ngoài thực tế.
- Tỷ lệ error_flag và độ phủ cần được xem riêng: khung hiện diện vẫn có thể không dùng được cho DSS.
- Unique indexes hiện tại bảo vệ khóa dimension; thử nghiệm fact index chỉ diễn ra trên bảng tạm, DW nguồn không đổi.
- Coverage giả định detector đã xuất hiện hoạt động toàn kỳ; detector mới/lịch bảo trì có thể làm tỷ lệ thấp mà không phải lỗi ETL.
- SQL, tham số, từng mẫu thời gian, EXPLAIN ANALYZE và toàn bộ checks nằm trong JSON cùng tên.
