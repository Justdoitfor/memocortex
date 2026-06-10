.PHONY: help install dev test test-cov eval eval-longmem eval-cn lint format clean api mcp demo web web-build web-install

help:
	@echo "MemoCortex Makefile"
	@echo ""
	@echo "  install      uv 安装所有依赖(含 dev + eval)"
	@echo "  dev          启动 FastAPI 服务(热重载)"
	@echo "  api          启动 FastAPI 服务(生产模式)"
	@echo "  mcp          启动 MCP Server"
	@echo "  web          启动前端 Demo (Next.js) → http://localhost:3000"
	@echo "  web-install  装前端 npm 依赖 (首次跑必须)"
	@echo "  web-build    前端生产构建 (用于 Vercel 部署)"
	@echo "  demo         运行基础 demo(30 行展示 5 类记忆)"
	@echo "  demo-conflict 运行冲突仲裁 demo"
	@echo "  demo-lc      运行 LangChain 适配 demo"
	@echo "  test         运行单元测试"
	@echo "  test-cov     运行测试 + 覆盖率"
	@echo "  eval         跑全套 eval(中文场景 + LongMemEval 子集)"
	@echo "  eval-cn      只跑中文冲突仲裁场景"
	@echo "  eval-longmem 只跑 LongMemEval 30 题子集"
	@echo "  lint         ruff + mypy 静态检查"
	@echo "  format       black + ruff 自动格式化"
	@echo "  clean        清理运行时数据(谨慎)"

install:
	uv sync --all-extras

dev:
	uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8765

api:
	uv run uvicorn app.api.main:app --host 0.0.0.0 --port 8765 --workers 1

mcp:
	uv run python -m mcp_server.server

demo:
	uv run python examples/demo_basic.py

demo-conflict:
	uv run python examples/demo_conflict.py

demo-lc:
	uv run python examples/demo_langchain.py

test:
	uv run pytest tests/unit -v

test-cov:
	uv run pytest tests/unit --cov=app --cov-report=term-missing --cov-report=html

eval:
	uv run python -m tests.eval.runner

eval-cn:
	uv run python -m tests.eval.runner --suite cn_scenarios

eval-longmem:
	uv run python -m tests.eval.runner --suite longmemeval

lint:
	uv run ruff check app tests
	uv run mypy app --ignore-missing-imports || true

format:
	uv run black app tests examples mcp_server
	uv run ruff check --fix app tests examples mcp_server

clean:
	rm -rf data/chroma data/graph data/cold data/memocortex.db data/*.db-* logs/
	@echo "运行时数据已清理"

# ── Frontend (Next.js) ──────────────────────────────────────────────
web-install:
	cd web && npm install

web:
	cd web && npm run dev

web-build:
	cd web && npm run build

# 构建静态站点并用 Python http.server 起服务 (避开 Next dev/prod 的 turbopack runtime bug)
web-serve:
	cd web && npm run build
	cd web/out && python -m http.server 3000
