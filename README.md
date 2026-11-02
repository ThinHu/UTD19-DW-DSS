# UTD19 Traffic Data Warehouse & Decision Support System (DSS)

Bài tập lớn CO4031 — Kho dữ liệu và Hệ hỗ trợ quyết định (HK261).
Kho dữ liệu giao thông đô thị trên bộ **UTD19 — Luzern (01/01–30/06/2015)** và hệ hỗ trợ ra quyết định
**ưu tiên theo dõi & điều phối giao thông** dựa trên kho dữ liệu đó. Công nghệ: DuckDB, Python, scikit-learn, FastAPI, React.

| Thành phần | Mô tả | Lệnh |
|---|---|---|
| Data Warehouse (`utd19_dw`, `sql/`) | ETL staging → clean → star schema (Kimball) → data mart, kiểm tra chất lượng, đối soát, kho siêu dữ liệu | `python -m utd19_dw.pipeline` |
| DSS engine (`utd19_dss`) | K-means, baseline, tiêu chí C1–C5, Gradient Boosting dự báo 30 phút, trọng số & ngưỡng tối ưu | `python -m utd19_dss.build` |
| Đánh giá DSS | So sánh chiến lược, ablation, quét ngưỡng, hiệu chỉnh, ổn định → `reports/` | `python -m utd19_dss.evaluate` |
| Backend + dashboard | FastAPI + React (nền sáng), phát lại tháng 6 như luồng live, what-if, goal seeking, trang kho dữ liệu & ETL | `uvicorn utd19_dss.api:app --port 8000` |
| Tài liệu thiết kế | `docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx` | `node docs/build_design_doc.js` |

## 1. Kết quả chính (tháng 6/2015 — dữ liệu chưa dùng khi dựng)

| Chỉ số | DSS v5.1 (giới hạn 10 Cao/khung) | v5.1 không giới hạn | v4 (trọng số kinh nghiệm) |
|---|---|---|---|
| Ngưỡng Cao / Trung bình | 40 / 30 (chọn theo F1 / F2 trên tháng 5) | 40 / 30 | 70 / 40 |
| Cảnh báo Cao mỗi khung (TB / tối đa) | 2,45 / 10 | 3,37 / 48 | 1,58 / — |
| Precision mức Cao | 76,8% | 70,5% | 58,3% |
| Recall mức Cao | 37,1% | 46,9% | 18,1% |
| — sự kiện đang diễn ra | 74,5% | 88,8% | 37,5% |
| — sự kiện sắp xảy ra (≤ 30 phút) | 7,2% | 13,3% | 2,6% |
| F1 mức Cao | 0.500 | 0.563 | 0.277 |
| Precision@10 | 39,9% | 39,9% | 34,5% |
| PR-AUC mô hình C5 | 0.342 | 0.342 | — (điểm luật: 0.170) |

Giới hạn năng lực ca trực (`config/dss.yaml: scoring.max_high_per_window`, mặc định 10 = top-K dùng khi tối ưu trọng số)
đổi một phần recall lấy precision và khối lượng việc chịu được ở giờ cao điểm; đặt 0 để bỏ giới hạn. Từ v5.1, giai đoạn
kiểm định chỉ dùng lịch sử T1–T4 cho tier, cụm detector và lân cận (tránh rò rỉ tháng 5), nên trọng số/ngưỡng khác bản v5 (35/25).

Báo cáo đầy đủ: [`reports/dss_evaluation.md`](reports/dss_evaluation.md) (bản Word: `reports/dss_evaluation.docx`).

## 2. Cấu trúc thư mục

```text
├── config/
│   ├── settings.yaml         # DW: thành phố, khoảng ngày, RAM, FLOW_MAX, luật loại khỏi mart
│   ├── dq_rules.yaml         # DW: bitmask luật chất lượng dữ liệu
│   └── dss.yaml              # DSS: chia dữ liệu, luật DQ, K-means, tiêu chí, ML, trọng số, quy tắc ngưỡng
├── sql/                      # ETL chạy theo thứ tự tên file trong từng thư mục
│   ├── 00_schema.sql         # schema stg, clean, dw, mart, etl (+ run_log, quarantine)
│   ├── 10_staging/           # nạp CSV thô
│   ├── 20_clean/             # ép kiểu, cách ly dòng lỗi/trùng, bitmask DQ
│   ├── 30_dw/                # dim_city, dim_road_class, dim_link, dim_detector, dim_date, dim_time_of_day, fact
│   ├── 40_mart/              # coverage, MFD, KPI, dss_detector_window, congestion_kpi, detector_day_15min
│   ├── 50_checks/            # đối soát toàn vẹn, kho siêu dữ liệu
│   └── export_mode/          # các bước riêng của chế độ nạp từ bản xuất 15 phút
├── utd19_dw/                 # pipeline (2 chế độ), profiling, export, weather (nguồn ngoài)
├── utd19_dss/                # DSS: data, baseline, engine, models, scoring, build, evaluate, live, store, dwinfo, api
├── frontend/                 # React + Vite; bản build sẵn ở frontend/dist (API phục vụ trực tiếp)
├── docs/                     # tài liệu thiết kế (.docx) + script sinh tài liệu
├── reports/                  # báo cáo đánh giá DSS, bảng CSV, biểu đồ
├── tests/                    # pytest: cấu hình, DB, pipeline end-to-end, đối soát, DSS
└── data/                     # (không đưa lên git) raw/, work/ (DuckDB), export/, dss/ (artifacts)
```

## 3. Cài đặt và chạy

Yêu cầu: Python ≥ 3.10. Node ≥ 18 chỉ cần khi sửa giao diện.

```bash
pip install -e .[dev,dss]
```

### 3.1. Data Warehouse

Pipeline có hai chế độ nạp, cùng ra một lược đồ sao (`python -m utd19_dw.pipeline` tự chọn):

| Chế độ | Khi nào | Nguồn | Fact |
|---|---|---|---|
| Đầy đủ (`--full`) | có `data/raw/utd19_u.csv` gốc (≈ 5 GB, mọi thành phố) | UTD19 gốc + `detectors*.csv`, `links*.csv` | `dw.fact_traffic_measurement` (3 phút) → gộp thành `dw.fact_traffic_15min` |
| Bản xuất (`--from-export`) | chỉ có bản xuất trong `data/raw/luzern_jan_jun/` (kèm repo) | `detector_window_15min.csv.gz` + hồ sơ detector | `dw.fact_traffic_15min` (15 phút) |

```bash
python -m utd19_dw.profiling      # khảo sát nguồn (chế độ đầy đủ)
python -m utd19_dw.weather        # (tùy chọn) tải thời tiết ngày Luzern → data/raw/external/ → dw.dim_weather
python -m utd19_dw.pipeline       # ETL → data/work/utd19.duckdb (~15 giây ở chế độ bản xuất)
python -m utd19_dw.export         # Parquet/CSV → data/export/
```

Lược đồ: fact `fact_traffic_15min` (thước đo cộng được: số đếm, tổng) với các chiều `dim_date` (Năm → Quý → Tháng → Tuần → Ngày, loại ngày, ngày lễ),
`dim_time_slot` (Buổi → Giờ → Khung 15′), `dim_detector` (SCD2-sẵn sàng) → `dim_road_class` (Nhóm đường → Loại đường), `dim_weather` (outrigger theo ngày).
Kiểm soát: `etl.run_log` (số dòng mỗi bước), `etl.quarantine`, `etl.reconciliation` (RC-A…RC-H: bảo toàn số dòng, khóa ngoại không orphan, đúng hạt fact, khóa chiều duy nhất), `etl.metadata_catalog` (siêu dữ liệu nghiệp vụ + kỹ thuật), `etl.load_info`.
DSS đọc `mart.dss_detector_window` và `dw.dim_detector`; các chiều và fact 15 phút sẵn sàng cho lớp OLAP/dashboard phân tích.

Chạy thử nhanh trên một phần dữ liệu: đặt `UTD_SMOKE_ROWS=100000` trong `.env` (xem `.env.example`).

### 3.2. DSS

DSS đọc `mart.dss_detector_window` và `dw.dim_detector` từ DW (chạy 3.1 trước); chỉ khi chưa có DW mới đọc thẳng
bản xuất CSV trong `data/raw/luzern_jan_jun/`. Dòng `nguồn:` khi build cho biết đang đọc từ đâu. Kết quả build từ DW
và từ CSV trùng khớp (mart tái tạo đúng bản xuất đến độ chính xác float32).

```bash
python -m utd19_dss.build         # ~5 phút: K-means, baseline, huấn luyện & chọn mô hình, trọng số, ngưỡng → data/dss/
python -m utd19_dss.evaluate      # đánh giá trên tháng 6 → reports/
uvicorn utd19_dss.api:app --port 8000
```

Mở http://localhost:8000. Dashboard bắt đầu tại 01/06/2015 00:00; bấm ▶ để phát lại từng khung 15 phút,
hoặc dùng nút đồng hồ để nhảy tới khung bất kỳ. Bản đồ nền cần Internet.

| Trang | Nội dung |
|---|---|
| Tổng quan, Bản đồ, Detector, Cảnh báo | Xếp hạng live, hành động gợi ý, ghi nhận quyết định và đánh giá sau 30′ |
| Mô hình | Mô hình quyết định (biến quyết định / không kiểm soát / kết quả, sơ đồ ảnh hưởng, kiến trúc 4 phân hệ, phân loại DSS, bảng quyết định), ML, K-means |
| What-if & goal seeking | Đổi trọng số/ngưỡng xem tác động; goal seeking: cho mục tiêu precision, recall hoặc năng lực ca trực → tìm ngưỡng |
| Kho dữ liệu & ETL | Chế độ nạp, đối soát, dòng bị cách ly, độ phủ theo tháng, lược đồ sao, kho siêu dữ liệu, nhật ký ETL |

Sửa giao diện: `cd frontend && npm install && npm run dev` (cổng 5173, tự chuyển `/api` sang 8000), xong `npm run build`.

### 3.3. Kiểm thử

```bash
pytest tests/
```

`tests/test_pipeline_smoke.py` chạy trọn pipeline DW trên dữ liệu giả lập trong thư mục tạm (không đụng DW thật).
`tests/test_dss.py::test_live_matches_batch` kiểm tra engine live cho cùng kết quả với chạy lô (cần đã chạy build).

## 4. Chia dữ liệu và chạy "live"

| Giai đoạn | Thời gian | Vai trò |
|---|---|---|
| Huấn luyện | 01/01 – 30/04/2015 | K-means, baseline, huấn luyện mô hình |
| Kiểm định | 01/05 – 31/05/2015 | chọn mô hình, trọng số, ngưỡng |
| Phát lại live | 01/06 – 30/06/2015 | mô hình huấn luyện lại trên T1–T5; dữ liệu T6 được đưa vào từng khung 15 phút |

Dữ liệu mới thật (ví dụ nửa cuối 2015): `POST /api/ingest` với thân là CSV của một khung 15 phút (cùng cột với
`mart.dss_detector_window`), hoặc nạp vào DW rồi chạy lại `build`.

## 5. Dữ liệu và giấy phép

UTD19 (IVT, ETH Zürich) — CC BY-NC-SA 4.0. Thời tiết (tùy chọn): Open-Meteo Historical Weather API (ERA5), CC BY 4.0. Trích dẫn: Loder, A., Ambühl, L., Menendez, M., Axhausen, K. W. (2019).
Understanding traffic capacity of urban networks. *Scientific Reports* 9, 16283.
