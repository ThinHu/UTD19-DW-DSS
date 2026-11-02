# DSS v5 — Ưu tiên điều phối giao thông Luzern

Hướng dẫn cài đặt, chạy và kết quả: xem [README.md](README.md) (mục 3.2 và 4).
Thiết kế: `docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx`. Đánh giá: `reports/dss_evaluation.md`.

| Module | Vai trò |
|---|---|
| `utd19_dss/data.py` | Nạp mart DW / CSV, luật chất lượng, tier A/B/C/X, lưới [thời gian × detector] |
| `utd19_dss/baseline.py` | K-means loại ngày & cụm detector; baseline μ/σ theo loại ngày × khung × detector |
| `utd19_dss/engine.py` | Tiêu chí C1–C4, nhãn sự kiện, đặc trưng học máy (dùng chung cho build và live) |
| `utd19_dss/models.py` | Decision Tree, Naive Bayes, Neural Network, Gradient Boosting; chỉ số đánh giá |
| `utd19_dss/scoring.py` | Priority Score, mức, bảng quyết định, tối ưu trọng số, quét/chọn ngưỡng, độ chắc chắn |
| `utd19_dss/build.py` | Bước offline: chọn mô hình/trọng số/ngưỡng trên T5, huấn luyện lại, chấm T6 → `data/dss/` |
| `utd19_dss/evaluate.py` | Đánh giá trên T6 → `reports/` |
| `utd19_dss/live.py`, `store.py`, `api.py` | Engine live, lưu DuckDB, REST API + phục vụ giao diện |
| `utd19_dss/dwinfo.py` | Đọc nhật ký ETL, đối soát, cách ly, siêu dữ liệu từ DW cho trang “Kho dữ liệu & ETL” |
