# OLAP giao thông Luzern

## Phạm vi và schema

Module OLAP đọc `dw.fact_traffic_15min` ở hạt **detector × ngày × khung 15 phút**. Fact nối `dw.dim_date` qua `date_key`, `dw.dim_time_slot` qua `slot_key`, `dw.dim_detector` qua `detector_key`; detector nối `dw.dim_road_class` qua `road_class_key`. Thời tiết, Priority Score, khuyến nghị và quyết định can thiệp không tham gia module này.

Giao diện dùng một biểu đồ drill **năm → tháng → ngày → giờ → khung 15 phút**. Date và Time vẫn là hai dimension riêng trong kho; thao tác drill lọc kỳ đã chọn trước khi nhóm theo chiều tiếp theo. Dữ liệu xuất hiện tại hạt 15 phút nên không thể hiển thị từng phút. API vẫn giữ chiều quý và phân loại đường để tương thích, nhưng dashboard không dùng các cấp này trong biểu đồ thời gian.

## Measures và độ tin cậy

| Chỉ số | Công thức / ý nghĩa |
|---|---|
| Occupancy trung bình | `100 × SUM(sum_occ_clean) / SUM(n_occ_clean)` trên **khung hợp lệ**, đơn vị %. |
| Flow trung bình | `SUM(sum_flow_clean) / SUM(n_flow_clean)` trên **khung hợp lệ**, đơn vị xe/giờ/làn. |
| Cảm biến có dữ liệu hợp lệ | Số detector có ít nhất một khung 15 phút hợp lệ trong phạm vi ngày và đường đã lọc / tất cả detector hiện hành thuộc đường đã chọn, kể cả detector không có fact trong khoảng ngày. Với toàn mạng, mẫu số là toàn bộ detector hiện hành trong dimension. |
| Độ phủ dữ liệu hợp lệ | `100 × số khung 15 phút hợp lệ / số khung 15 phút có dữ liệu` trong phạm vi lọc. Ngày hoặc detector không có fact không được tính là khung không hợp lệ. |
| Tỷ lệ khoảng đo lỗi | `100 × SUM(n_err) / SUM(n_intervals)` trên toàn bộ khoảng đo trong slice, hiển thị ở chi tiết cảm biến, bảng phân tích và phần Data Quality. |

Khung hợp lệ có ít nhất 3 mẫu sạch cho cả occupancy và flow; occupancy trung bình trong `[0,1]`, flow trung bình trong `[0,FLOW_MAX]`; loại trường hợp occupancy ≥ 0,95 đồng thời flow = 0. `FLOW_MAX` theo `config/settings.yaml` là 3500. Cấu hình DSS hiện dùng 3000. Tỷ lệ lỗi tính theo **khoảng đo**; tỷ lệ khung hợp lệ tính theo **khung 15 phút**, nên hai tỷ lệ có mẫu số khác nhau.

Tổng flow trong fact là **tổng của các tốc độ dòng** để tính trung bình; không được diễn giải thành tổng lượt xe qua mạng. Ngày không có fact là thiếu quan sát, không phải flow bằng 0. Quy tắc khung hợp lệ kiểm tra chất lượng dữ liệu theo điều kiện kho, không xác nhận cảm biến đúng trong thực tế.

## Tương tác và ánh xạ OLAP

| Giao diện | Khái niệm OLAP |
|---|---|
| Bộ lọc chính: khoảng ngày và đường | Slice dữ liệu cho summary, biểu đồ, heatmap và bảng phân tích. Bản đồ giữ mọi marker; đường chọn được zoom và làm nổi bật. |
| Bấm điểm trên một biểu đồ năm → tháng → ngày → giờ → 15 phút | Drill-down theo kỳ/thời gian được chọn; breadcrumb cho phép roll-up. |
| Heatmap thứ trong tuần × giờ | Phân tích chéo Date × Time; chọn Occupancy hoặc Flow, rê chuột hoặc bật số trong ô để xem giá trị. |
| Chọn detector trên bản đồ, danh sách hoặc bảng | Dùng cùng một lựa chọn; marker được làm nổi bật, ô thông tin hiện cạnh bản đồ, biểu đồ thời gian và heatmap cập nhật bên dưới. |
| Bảng phân tích đa chiều | Sau bản đồ, chọn nhóm theo ngày trong tuần, daypart, đường, nhóm đường, loại đường hoặc detector; backend tổng hợp lại theo khoảng ngày và đường đang lọc. Khi đã lọc một đường, ẩn các lựa chọn nhóm theo đường, nhóm đường và loại đường; nếu đang ở một nhóm đó thì chuyển về ngày trong tuần. Bấm tiêu đề cột để sắp xếp nhóm hoặc các giá trị tăng/giảm; dòng detector có thể bấm để chọn detector. |
| Data Quality | Phần thu gọn sau bảng, hiển thị tỷ lệ khung hợp lệ, tỷ lệ khoảng đo lỗi, số mẫu sạch và số detector có bản ghi. |

Map dùng tọa độ của detector để cung cấp bối cảnh không gian, không tạo hierarchy địa lý. Nền bản đồ được chuyển sang thang xám để điểm cảm biến rõ hơn.

## API

- `GET /api/olap/options`: khoảng ngày, nhóm/loại đường, tên đường và hồ sơ **mọi detector hiện hành** để chọn, vẽ bản đồ và tính mẫu số của chỉ số detector hợp lệ.
- `GET /api/olap/query`: `group_by` và `split_by` chọn hai trục nhóm từ danh sách cố định. Hỗ trợ `year`, `quarter`, `month`, `day`, `iso_week`, `day_of_week`, `day_type`, `daypart`, `hour`, `slot`, `peak`, `road_group`, `road_class`, `road_name`, `detector`; `all` cho trục không nhóm. Filter gồm `start`, `end`, `day_of_week`, `day_type`, `daypart`, `peak`, `year`, `quarter`, `month`, `date_value`, `hour`, `hour_start`, `hour_end`, `road_name`, `road_group`, `fclass`, `detid`.

Các biểu thức nhóm đến từ allowlist phía server; giá trị filter là tham số DuckDB. Truy vấn trả tối đa 5.000 nhóm. Tham số cũ `period`/`road` được giữ để tương thích.

```bash
.venv/bin/python -m utd19_dw.pipeline --from-export
.venv/bin/python -m utd19_dss.build
cd src/frontend && npm ci && npm run build
cd ../.. && .venv/bin/python -m uvicorn utd19_dss.api:app --port 8000
```

Mở `http://localhost:8000` và chọn mục **Phân tích OLAP** thứ hai trên sidebar. API hiện khởi tạo DSS khi chạy, nên cần build DSS một lần dù phần OLAP không dùng các chỉ số DSS.
Sidebar chính có thứ tự Overview → OLAP → Map → Alerts → ML → What-if → Data Warehouse & ETL. Danh sách detector hiện có vẫn mở được từ trang Map.

## Giới hạn

Dữ liệu hiện có là Luzern từ tháng 1 đến tháng 6/2015. Số detector có dữ liệu thay đổi theo thời gian; mẫu số detector hợp lệ là số detector hiện hành thuộc đường đã chọn và không giảm khi rút ngắn khoảng ngày. Bản xuất 15 phút không giữ fact gốc 3 phút hoặc hình học đoạn đường. Bản đồ nền OSM cần Internet; marker và thông tin đường/tọa độ vẫn lấy từ kho dữ liệu. Không suy rộng các xu hướng này sang giai đoạn hoặc thành phố khác nếu chưa bổ sung dữ liệu.
