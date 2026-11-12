.DEFAULT_GOAL := help
.PHONY: help setup dw-profile dw-load dw-load-export dw-weather dw-export test dw-all clean \
	dss-build dss-evaluate dss-serve frontend-build docs-build

help: ## Hiển thị danh sách lệnh
	@awk 'BEGIN {FS = ":.*##"; printf "Cách dùng: make <lệnh>\n\nCác lệnh:\n"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Cài package và dependencies phát triển/DSS
	python -m pip install -e ".[dev,dss]"

dw-profile: ## Khảo sát chất lượng dữ liệu nguồn
	python -m utd19_dw.profiling

dw-load: ## Chạy ETL, tự chọn dữ liệu gốc 3 phút hoặc bản xuất 15 phút
	python -m utd19_dw.pipeline

dw-load-export: ## Chạy ETL từ bản xuất 15 phút
	python -m utd19_dw.pipeline --from-export

dw-weather: ## Tải dữ liệu thời tiết Luzern; chạy dw-load để nạp vào DW
	python -m utd19_dw.weather

dw-export: ## Xuất DW ra Parquet/CSV
	python -m utd19_dw.export

test: ## Chạy bộ kiểm thử pytest
	pytest tests/

dw-all: dw-load dw-export test ## Chạy ETL, xuất dữ liệu và kiểm thử

# ---- DSS ----
dss-build: ## Dựng artifacts DSS
	python -m utd19_dss.build

dss-evaluate: ## Đánh giá DSS và ghi báo cáo
	python -m utd19_dss.evaluate

app-serve: ## Chạy API và dashboard tại http://localhost:8000
	uvicorn utd19_dss.api:app --port 8000

frontend-build: ## Build giao diện React/Vite
	cd src/frontend && npm install && npm run build

docs-build: ## Sinh tài liệu thiết kế DSS từ artifacts
	node docs/build_design_doc.js data/dss/meta.json docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx reports/dss_evaluation.json

clean: ## Xóa database làm việc, dữ liệu xuất và artifacts DSS
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['data/work', 'data/export', 'data/dss']]"
