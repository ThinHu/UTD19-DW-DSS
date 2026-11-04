# Vận hành và kiểm chứng Data Warehouse

Phạm vi hiện tại: UTD19 Luzern, 01/01–30/06/2015. Hai chế độ full/export dùng chung fact 15 phút và mart DSS.
Dimension detector là snapshot có cột dự phòng SCD2; chưa lưu lịch sử thay đổi thuộc tính.

## Môi trường và lệnh chạy (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -X utf8 -m pip install -e ".[dev,dss]"
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/ -q

# Dựng vào thư mục riêng để kiểm chứng nguồn thật.
$env:UTD_WORK_DIR = 'data/work_validation'
.\.venv\Scripts\python.exe -X utf8 -m utd19_dw.pipeline --full
.\.venv\Scripts\python.exe -X utf8 -m utd19_dw.validate --report reports/dw_validation.json

# Sau khi đánh giá báo cáo, chạy vào đường dẫn DW mặc định.
Remove-Item Env:UTD_WORK_DIR
.\.venv\Scripts\python.exe -X utf8 -m utd19_dw.pipeline --full
```

`UTD_SMOKE_ROWS` giới hạn số dòng staging sau lọc; một lần chạy smoke vẫn thay toàn bộ nội dung DW đích,
vì vậy luôn đặt `UTD_WORK_DIR` riêng. `--from-export` cần hai file export và hồ sơ detector trong
`data/raw/luzern_jan_jun/`. Nguồn gốc cần `utd19_u.csv`, `*detector*.csv`, `*link*.csv`.

## Tính nguyên tử và lịch sử

Pipeline kiểm tra nguồn/cấu hình trước khi nạp; transaction bao trùm dữ liệu staging → clean → DW → mart,
quarantine, checks, views/indexes và load_info. Chỉ commit sau khi mọi check PASS. Nếu lỗi, DW của lần nạp
trước được giữ lại; lần chạy đầu tiên lỗi chưa tạo được DW phục vụ truy vấn.

- `etl.runs`: RUNNING/SUCCESS/FAILED, run_id, nguồn, thời điểm và lỗi.
- `etl.run_log`: từng bước, run_id, trạng thái, số dòng đầu ra, thời lượng. Step logs trong transaction
  được giữ trong bộ nhớ và ghi sau commit/rollback; file `WORK_DIR/logs/<run_id>.log` ghi ngay trong khi chạy.
- `etl.check_history`: kết quả kiểm tra theo run_id, bao gồm check FAIL trước rollback.
- `etl.load_info`: nguồn và thời điểm của bộ dữ liệu commit thành công gần nhất.
- `etl.quarantine`: các dòng bị loại của bộ dữ liệu hiện tại, không phải lịch sử tất cả lần chạy.

Khi đổi full → export, pipeline bỏ fact 3 phút và các mart chỉ dành cho full trong cùng transaction.
Mọi nguồn CSV được đọc với quote/escape tường minh; lỗi cấu trúc CSV gây thất bại, không bị bỏ qua âm thầm.
Kết nối DW mở khi được sử dụng và đóng sau pipeline; import module không mở tệp.

Transaction cần đủ RAM và dung lượng spill/disk; cấu hình qua duckdb.memory_limit, duckdb.threads và
UTD_MEMORY_LIMIT. Khi tiến trình bị kill hoặc mất điện, log file có thể còn, run status có thể còn RUNNING;
không có cơ chế tự kết luận FAILED cho các lần chạy bị ngắt cứng.

## Hợp đồng DQ

- Ngày/khóa không parse được, interval không hữu hạn/ngoài ngày/lệch bước 180 giây: quarantine.
- Trùng khóa: giữ dòng nạp sau cùng, cách ly các dòng còn lại.
- Flow âm/vượt FLOW_MAX/không hữu hạn; occupancy ngoài [0,1]/không hữu hạn: chuyển NULL và giữ cờ DQ.
- Occupancy được chuẩn hóa theo thang suy từ dữ liệu thành phố; đây là heuristic cần xem lại khi đổi nguồn.
- Export: n trong [1,5]; các count là số nguyên, không âm và không vượt count cha; count clean không vượt
  số khoảng không lỗi. Count dương cần mean hữu hạn trong miền vật lý; count bằng 0 cần mean NULL.
- Ngày hợp lệ ngoài cấu hình được lọc khỏi staging; ngày không parse được vẫn được giữ để cách ly.
- Rule id và bit phải duy nhất; rule không tồn tại trong cấu hình exclusion gây lỗi ngay.

`*_clean` trong fact 15 phút/mart DSS nghĩa là khoảng không có error_flag, trên các giá trị đã làm sạch.
Các mart MFD/KPI dùng EXCLUDE_MASK để loại cả dòng theo bit DQ. Hai định nghĩa phục vụ mục đích khác nhau;
không dùng thay thế nhau. Nguồn export không giữ đủ bitmask gốc để khôi phục mọi chính sách loại dòng.

## Kiểm chứng và truy vấn

`python -m utd19_dw.validate --db <file.duckdb> --report <report.json>` mở database read-only,
tính lại checks vào bảng tạm và trả exit code 1 nếu FAIL. Không tin vào kết quả check đã lưu trước đó.
Báo cáo gồm số dòng, khoảng ngày, quarantine và kết quả RC/DQ. Ngưỡng FLOW_MAX lấy từ cấu hình hiện tại.

Các check bao gồm bảo toàn số dòng, FK/grain, count/sum hợp lệ, tính đúng của toàn bộ giá trị mart DSS,
và đối soát từng nhóm giữa fact 3 phút và 15 phút. Sai số rollup: 1e-7 + 1e-7 × |giá trị kỳ vọng|.
Kết quả PASS xác nhận những bất biến đã kiểm tra, không chứng minh cảm biến đo đúng ngoài thực tế.

Views:

- `dw.v_traffic_15min`: fact kèm detector/city/ngày và mean từ sum/count.
- `etl.v_quality_checks`: RC và DQ của bộ dữ liệu hiện tại.
- `etl.v_quarantine_summary`: số dòng cách ly theo nguồn/rule.

Khi tổng hợp lên ngày/tháng, dùng SUM(sum_flow_clean)/NULLIF(SUM(n_flow_clean),0), không AVG(mean).
Unique indexes trên khóa city/link/detector/date/slot/road_class bảo vệ join. Chưa tạo index fact lớn;
cần benchmark workload cụ thể trước khi bổ sung, chưa có tuyên bố tăng tốc truy vấn.

## Phối hợp nhóm

Thay đổi DW checks/testing cần được thông báo cho Hữu theo CLAUDE.md. Tài liệu này và báo cáo kiểm chứng
là nội dung bàn giao; agent không tự gửi tin nhắn cho thành viên nhóm.

## Đánh giá Data Quality và Query Performance

```powershell
.\.venv\Scripts\python.exe -X utf8 -m utd19_dw.assess --repeats 15
# Hoặc chỉ định DW khác:
.\.venv\Scripts\python.exe -X utf8 -m utd19_dw.assess --db data/work_validation/utd19.duckdb --repeats 15 --report-dir reports/validation_run
```

Lệnh tạo `dw_assessment.md` và `dw_assessment.json` trong report-dir. Nguồn DW được mở read-only.
Benchmark index dùng TEMP table được hủy khi đóng kết nối; không tạo index trong DW nguồn.
Đánh giá gồm 8 workload (7 nếu DW chỉ có export), 1 lượt đầu + N lượt đo cho mỗi query, SQL/params,
median/p95, kết quả EXPLAIN ANALYZE, đối chiếu rollup ngày, thử viết lại bộ lọc ngày và index A/B.
Q7 là truy vấn fact 3 phút nên chỉ có ở chế độ full.

Correctness PASS không đồng nghĩa chất lượng dữ liệu đạt một SLA. Báo cáo DQ hiện là mô tả, chưa áp
ngưỡng chấp nhận nghiệp vụ; performance đo warm-cache, một client, không đo concurrent/cold-cache.
Tỷ lệ cờ DQ trên fact dùng số dòng fact làm mẫu số. Tỷ lệ quarantine dùng staging đã lọc city/ngày.
Coverage dùng detector từng có số đo × toàn kỳ cấu hình, không suy ra lịch vận hành thực tế.
Không cộng tỷ lệ flag vì một dòng có thể mang nhiều cờ. RULE_SPEED_OOR chưa áp dụng cho nguồn này.

Kiểm tra mới `DQ-SOURCE` so sánh từng bản ghi clean → fact theo khóa nghiệp vụ, gồm giá trị, error/DQ
flags và has_flow/has_occupancy; kỳ vọng không dùng etl.detector_map. `DQ-F3-DOMAIN` kiểm tra error
flag, miền số đo và bước thời gian. `DQ-DIM-KEYS` kiểm tra NULL/duplicate trên mọi dimension.
Những check này chạy cả trong ETL mới và trong validate/assess read-only. Kết quả audit của lần ETL
cũ không được tự cập nhật; validate/assess tính lại trực tiếp theo code hiện tại.

Xem `reports/dw_testing.md` cho phạm vi kiểm thử và `reports/dw_assessment.md` cho số liệu lần đo.
