# UTD19 Traffic Data Warehouse & Decision Support System (DSS)

Hệ thống Data Warehouse và Decision Support System xử lý tập dữ liệu giao thông quy mô lớn UTD19 (Urban Traffic Data 19) dựa trên công nghệ **DuckDB**, **Python**, và **Parquet**.

## 1. Cấu trúc thư mục

```text
├── config/                  # Tệp cấu hình hệ thống & DQ rules
│   ├── settings.yaml        # Danh sách thành phố, cấu hình RAM, ngưỡng flow
│   └── dq_rules.yaml        # Bảng bitmask các quy tắc Data Quality
├── data/
│   ├── raw/                 # Tệp CSV thô đầu vào (measurements, detectors, links)
│   ├── work/                # Tệp cơ sở dữ liệu DuckDB trung gian
│   └── export/              # Dữ liệu xuất Parquet & CSV phục vụ DSS
├── sql/
│   ├── 00_schema.sql        # Khởi tạo schemas (stg, clean, dw, mart, etl)
│   ├── 10_staging/          # Nạp dữ liệu thô sang staging
│   ├── 20_clean/            # Làm sạch dữ liệu, tính bitmask DQ, cách ly lỗi
│   ├── 30_dw/               # Xây dựng Kimball Star Schema (Dimensions & Fact)
│   ├── 40_mart/             # Xây dựng Data Marts (MFD, Congestion KPIs)
│   └── 50_checks/           # Đối soát toàn vẹn (reconciliation)
├── src/utd19_dw/
│   ├── config.py            # Quản lý cấu hình & DQ masks
│   ├── db.py                # Quản lý kết nối DuckDB, PRAGMA, ETL logging
│   ├── pipeline.py          # Orchestration chạy toàn bộ chuỗi SQL
│   ├── profiling.py         # Thống kê và survey chất lượng nguồn dữ liệu
│   └── export.py            # Xuất Parquet phân vùng theo city_key
├── tests/                   # Kiểm thử tự động (Unit & Integration tests)
├── Makefile                 # Automation commands
└── pyproject.toml           # Định nghĩa dependencies và package
```

## 2. Hướng dẫn cài đặt & vận hành

### Cài đặt môi trường
```bash
pip install -e .[dev]
```

### Chạy Profiling khảo sát nguồn dữ liệu
```bash
python -m utd19_dw.profiling
# hoặc
make profiling
```

### Chạy toàn bộ Pipeline Data Warehouse
```bash
python -m utd19_dw.pipeline
# hoặc
make run-pipeline
```

### Xuất dữ liệu DSS (Parquet & CSV)
```bash
python -m utd19_dw.export
# hoặc
make export
```

### Chạy Test Suite
```bash
pytest tests/
# hoặc
make test
```
