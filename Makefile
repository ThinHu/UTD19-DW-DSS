.PHONY: setup run-pipeline run-pipeline-export weather profiling export test all clean dss-build dss-eval dss-api dss-frontend dss-doc

setup:
	pip install -e .[dev,dss]

profiling:
	python -m utd19_dw.profiling

run-pipeline:       ## Tự chọn: utd19_u.csv (hạt 3 phút) nếu có, không thì bản xuất 15 phút
	python -m utd19_dw.pipeline

run-pipeline-export: ## Bắt buộc nạp từ bản xuất khung 15 phút (data/raw/luzern_jan_jun)
	python -m utd19_dw.pipeline --from-export

weather:            ## Tải thời tiết ngày Luzern (Open-Meteo) → data/raw/external/, rồi chạy lại pipeline
	python -m utd19_dw.weather

export:
	python -m utd19_dw.export

test:
	pytest tests/

all: run-pipeline export test

# ---- DSS v5 ----
dss-build:          ## K-means, baseline, huấn luyện & chọn mô hình, tối ưu trọng số → data/dss/
	python -m utd19_dss.build

dss-eval:           ## Đánh giá DSS trên tháng 6 → reports/
	python -m utd19_dss.evaluate

dss-api:            ## Backend + dashboard tại http://localhost:8000
	uvicorn utd19_dss.api:app --port 8000

dss-frontend:       ## Build lại giao diện (cần Node ≥ 18)
	cd frontend && npm install && npm run build

dss-doc:            ## Sinh tài liệu thiết kế .docx từ data/dss/meta.json (cần Node + gói docx)
	node docs/build_design_doc.js data/dss/meta.json docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx reports/dss_evaluation.json

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['data/work', 'data/export', 'data/dss']]"