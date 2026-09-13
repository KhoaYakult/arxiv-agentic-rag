.PHONY: install dev-install run ui test lint fmt docker-build docker-run

install:
	pip install -r requirements.txt

dev-install: install
	pip install ruff pytest pre-commit

run:
	uvicorn app.api.main:app --reload --port 8000

ui:
	streamlit run streamlit_app.py

test:
	python -m pytest tests/ -v

lint:
	ruff check .

fmt:
	ruff check . --fix

docker-build:
	docker build -t arxiv-rag .

docker-run:
	docker run -p 8000:8000 --env-file .env arxiv-rag
