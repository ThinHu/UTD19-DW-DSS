# Kiểm thử ETL/DW và reconciliation

Kết quả quan sát ngày 04/11/2026 (Asia/Saigon): **30 passed, 2 skipped**, thời gian 26,80 giây.

Lệnh chạy:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/ -q
```

## Phạm vi và bằng chứng

| Nhóm | Trường hợp kiểm thử | Kỳ vọng/kết quả |
|---|---|---|
| End-to-end full | CSV → staging → clean → dimensions → fact 3/15 phút → mart → checks | Bảo toàn dòng, số khung, coverage, calendar, weather và metadata đúng fixture |
| End-to-end export | Export 15 phút → cùng schema/mart | Đúng grain/count, cách ly slot ngoài ngày và duplicate |
| Reconciliation nguồn | Sửa flow ở fact rồi dựng lại aggregate/mart | Downstream checks vẫn PASS nhưng DQ-SOURCE FAIL đúng 1 bản ghi |
| Sai aggregate | Cộng sai sum_flow_all | DQ-ROLLUP và DQ-MART-VALUES FAIL |
| Sai khóa/grain | Thêm duplicate fact, orphan detector, NULL dimension key | RC-G, DQ-FK15, DQ-DIM-KEYS phát hiện |
| Giá trị kỳ vọng độc lập | 5 số flow của D1 là 300,999,336,354,372 | Tổng 2361; không chỉ so hai query sao chép cùng công thức |
| Chất lượng số đo | NaN/Infinity, ngày không parse, interval lệch bước | Giá trị thành NULL/có cờ hoặc quarantine đúng rule |
| Chất lượng export | Count âm/vượt count cha, count thiếu, slot thập phân, mean ngoài miền/Infinity | Dòng lỗi bị cách ly, ngày ngoài cấu hình bị lọc |
| Occupancy và sentinel | Nguồn percent=5%, sentinel 99999/999,99 ở dòng error | Scale percent, occupancy hợp lệ 0,05; sentinel thành NULL và giữ cờ |
| Rollover và inferred dimension | Interval=86400, detector thiếu hồ sơ | Chuyển sang ngày sau/time=0, detector is_inferred |
| Rollback checks | Cố tình làm check FAIL giữa lần nạp thứ hai | Dữ liệu và load_info trước đó giữ nguyên, lịch sử FAILED vẫn còn |
| Rollback SQL | Cố tình truy vấn bảng không tồn tại giữa ETL | Rollback dữ liệu, lưu step FAILED và exception |
| Idempotency/đổi mode | Full → full → export → full | Không nhân dữ liệu, xóa bảng full lỗi thời, views/indexes vẫn hoạt động |
| Đánh giá read-only | Chạy validate/assess trên fixture | Đúng số lượng, tỷ lệ DQ tính tay và daily rollup không sai khác |
| Benchmark | 8 workload, rewrite date filter, index trên TEMP table | SQL chạy được, các lượt trả kết quả nhất quán trong sai số số thực; không đặt ngưỡng ms dễ gây flaky |

## Dữ liệu thật

`reports/dw_assessment.md` và JSON đi kèm ghi kết quả trên DW Luzern 01/01–30/06/2015:
13.138.969 dòng fact 3 phút, 2.633.638 dòng fact 15 phút; **24/24 checks PASS**.
Đối chiếu daily weighted rollup trên 181 ngày không có khác biệt theo ngưỡng đã công bố.
DW được mở read-only khi đánh giá; index thử nghiệm chỉ tồn tại trên bản sao TEMP.

## Giới hạn

- Hai test DSS bị skip vì chưa có artifacts `meta.json` và `valid_scores.npz` từ DSS build;
  không có test ETL/DW mới bị skip.
- Báo cáo không chứng minh cảm biến đo đúng ngoài thực tế hoặc tất cả nguồn UTD19/thành phố đều được hỗ trợ.
- Full/export dùng cùng schema nhưng nguồn export không giữ đầy đủ bitmask gốc; không khẳng định khôi phục mọi chính sách loại dòng.
- Quarantine/checks snapshot của DW cũ giữ trạng thái lần nạp cũ; validate/assess tính lại theo SQL hiện tại.
- Rollover đã kiểm thử trên ngày ở giữa kỳ; chưa thay đổi quy tắc lọc khoảng ngày ở biên kỳ.
- Performance đo warm-cache tuần tự; chưa có cold-cache, concurrency, SLA hoặc benchmark tải dữ liệu tăng trưởng.
- Thay đổi checks/testing được ghi tại đây để bàn giao cho Hữu theo CLAUDE.md; không tự gửi tin nhắn.
