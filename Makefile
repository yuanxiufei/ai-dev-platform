# ai-fullstack-platform — 常用命令
# 用法: make <target>

.DEFAULT_GOAL := help

# ── 路径 ──
BACKEND := backend
FRONTEND_STUDIO_CLIENT := studio-client
FRONTEND_STUDIO_ADMIN := studio-admin
FRONTEND_VIDEO_CLIENT := video-client
FRONTEND_VIDEO_ADMIN := video-admin

# ── 颜色 ──
CYAN  := \033[36m
GREEN := \033[32m
RESET := \033[0m

.PHONY: help
help: ## 显示帮助
	@echo "$(CYAN)ai-fullstack-platform 命令列表$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-24s$(RESET) %s\n", $$1, $$2}'

# ═══════════════════ 开发服务器 ═══════════════════

.PHONY: dev
dev: ## 启动后端开发服务器
	cd $(BACKEND) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: dev-studio
dev-studio: ## 启动 Studio 前端开发服务器
	cd $(FRONTEND_STUDIO_CLIENT) && npm run dev

.PHONY: dev-video
dev-video: ## 启动 Video 前端开发服务器
	cd $(FRONTEND_VIDEO_CLIENT) && npm run dev

.PHONY: docker-up
docker-up: ## 启动 Docker Compose 完整环境 (PG + Redis + Qdrant + Celery)
	docker compose up -d

.PHONY: docker-down
docker-down: ## 停止 Docker Compose 环境
	docker compose down

# ═══════════════════ 测试 ═══════════════════

.PHONY: test
test: ## 运行后端测试
	cd $(BACKEND) && pytest tests/ -v --tb=short

.PHONY: test-cov
test-cov: ## 运行后端测试 + 覆盖率报告
	cd $(BACKEND) && pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

.PHONY: test-core
test-core: ## 运行核心模块测试（model_router, providers, agent）
	cd $(BACKEND) && pytest tests/test_model_router.py tests/test_providers.py tests/test_agent_chat.py -v --tb=short

.PHONY: test-agent-e2e
test-agent-e2e: ## 运行 Agent 流程 E2E 集成测试
	cd $(BACKEND) && pytest tests/test_agent_e2e.py -v --tb=short -x

.PHONY: test-migrations
test-migrations: ## 运行 DB 迁移测试
	cd $(BACKEND) && pytest tests/test_alembic_migrations.py -v --tb=short

.PHONY: test-all
test-all: ## 运行所有后端测试（含 E2E、迁移）
	cd $(BACKEND) && pytest tests/ -v --tb=short

.PHONY: test-frontend
test-frontend: ## 运行 Studio 前端测试
	cd $(FRONTEND_STUDIO_CLIENT) && npm run test

.PHONY: test-e2e
test-e2e: ## 运行 Playwright E2E 测试 (需要先启动服务器)
	cd $(FRONTEND_VIDEO_ADMIN) && npx playwright test

# ═══════════════════ 代码质量 ═══════════════════

.PHONY: lint
lint: ## 运行 pre-commit 检查所有文件
	pre-commit run --all-files

.PHONY: lint-backend
lint-backend: ## 仅检查后端代码
	cd $(BACKEND) && ruff check app/

.PHONY: format
format: ## 格式化后端代码
	cd $(BACKEND) && ruff format app/

.PHONY: typecheck
typecheck: ## 后端类型检查
	cd $(BACKEND) && mypy app/ --ignore-missing-imports

# ═══════════════════ 数据库 ═══════════════════

.PHONY: db-migrate
db-migrate: ## 生成数据库迁移
	cd $(BACKEND) && alembic revision --autogenerate -m "auto"

.PHONY: db-upgrade
db-upgrade: ## 执行数据库迁移
	cd $(BACKEND) && alembic upgrade head

.PHONY: db-downgrade
db-downgrade: ## 回滚最近一次迁移
	cd $(BACKEND) && alembic downgrade -1

# ═══════════════════ 依赖 ═══════════════════

.PHONY: install
install: ## 安装后端依赖
	cd $(BACKEND) && uv sync

.PHONY: install-ml
install-ml: ## 安装 ML 模型依赖 (torch + transformers + diffusers)
	cd ai_models && uv sync

.PHONY: install-all
install-all: ## 安装所有依赖 (后端 + ML + 前端)
	cd $(BACKEND) && uv sync
	cd ai_models && uv sync
	cd $(FRONTEND_STUDIO_CLIENT) && npm install
	cd $(FRONTEND_STUDIO_ADMIN) && npm install

# ═══════════════════ 构建 ═══════════════════

.PHONY: build
build: ## 构建所有 Docker 镜像
	docker compose build

.PHONY: build-backend
build-backend: ## 仅构建后端 Docker 镜像
	docker build -t ai-fullstack-backend $(BACKEND)

.PHONY: clean
clean: ## 清理构建产物和缓存
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec echo "  skip node_modules" \; 2>/dev/null || true
	@echo "Cleanup done"

# ═══════════════════ K8s 部署 ═══════════════════

.PHONY: k8s-lint
k8s-lint: ## 检查 Helm Chart
	helm lint deploy/helm/ai-platform

.PHONY: k8s-dry-run
k8s-dry-run: ## Helm 试运行
	helm install --dry-run --debug ai-platform deploy/helm/ai-platform

.PHONY: k8s-install
k8s-install: ## 部署到 K8s 集群
	helm upgrade --install ai-platform deploy/helm/ai-platform --namespace ai-platform --create-namespace

.PHONY: k8s-uninstall
k8s-uninstall: ## 从 K8s 集群卸载
	helm uninstall ai-platform --namespace ai-platform
