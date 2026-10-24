.PHONY: install dev-install run ui test test-integration eval lint fmt docker-build docker-run

install:
	pip install -r requirements.txt

dev-install: install
	pip install -r requirements-dev.txt pre-commit

run:
	uvicorn app.api.main:app --reload --port 8000

ui:
	streamlit run ui/streamlit_app.py

test:
	python -m pytest tests/ -v

# Integration test can Postgres+pgvector rieng (KHONG dung Supabase that).
# Bat container tam: docker run -d --rm --name pgtest -e POSTGRES_PASSWORD=postgres -p 55432:5432 pgvector/pgvector:pg16
test-integration:
	TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:55432/postgres python -m pytest tests/integration -v

# Danh gia retrieval (Phase 3) tren DB eval RIENG. Can EVAL_DATABASE_URL trong moi truong, vd:
#   EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:55434/postgres make eval
# (KHONG dung Supabase - script tu choi URL chua "supabase"). Them tham so: make eval ARGS="--label x --configs sparse"
eval:
	python eval/run_eval.py $(ARGS)

lint:
	ruff check .

fmt:
	ruff check . --fix

docker-build:
	docker build -t arxiv-rag .

docker-run:
	docker run -p 8000:8000 --env-file .env arxiv-rag
