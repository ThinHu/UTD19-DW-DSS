.PHONY: setup run-pipeline profiling export test all clean

setup:
	pip install -e .[dev]

profiling:
	python -m utd19_dw.profiling

run-pipeline:
	python -m utd19_dw.pipeline

export:
	python -m utd19_dw.export

test:
	pytest tests/

all: run-pipeline export test

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['data/work', 'data/export']]"
