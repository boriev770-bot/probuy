SHELL := /usr/bin/bash

.PHONY: help backend-install backend-run frontend-install frontend-dev frontend-build dev prod clean

help:
	@echo "Targets:"
	@echo "  backend-install  Install Python deps (no Postgres in DEV)"
	@echo "  backend-run      Run FastAPI dev server on :8000 (DEV_MODE=1)"
	@echo "  frontend-install Install web deps via npm ci"
	@echo "  frontend-dev     Run Vite dev server on :5173"
	@echo "  frontend-build   Build Vite into web/dist"
	@echo "  dev              Start backend and frontend (two terminals recommended)"

backend-install:
	/usr/bin/pip3 install --no-cache-dir --break-system-packages fastapi==0.111.0 uvicorn==0.30.1 aiofiles==23.2.1 httpx==0.27.2

backend-run:
	DEV_MODE=1 /home/ubuntu/.local/bin/uvicorn api:app --host 0.0.0.0 --port 8000

frontend-install:
	cd web && npm ci --no-audit --no-fund

frontend-dev:
	cd web && VITE_API_BASE=http://localhost:8000 npm run dev

frontend-build:
	cd web && npm run build

dev:
	@echo "Open two terminals: make backend-run and make frontend-dev"

clean:
	rm -rf web/node_modules web/dist
