.PHONY: help install dev dev-backend dev-frontend build test lint clean sync-projects sync-watch
.PHONY: agentic-dev-backend agentic-dev-frontend agentic-dev format typecheck
.PHONY: port-debug port-clean compare-projects

# Port Configuration
# Human developer ports (default)
BACKEND_PORT ?= 8100
FRONTEND_PORT ?= 5273

# AI agent ports (use these when developing as Claude Code)
AGENTIC_BACKEND_PORT ?= 8101
AGENTIC_FRONTEND_PORT ?= 5274

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# Installation
# =============================================================================

install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install backend dependencies with uv
	uv sync --all-groups

install-frontend: ## Install frontend dependencies
	npm --prefix frontend install

# =============================================================================
# Human Developer Targets (default ports)
# =============================================================================

dev: install-frontend ## Run both backend and frontend for human developers (ports 8100, 5273)
	@echo "==============================================================================="
	@echo "| 🚀 Starting dev servers (HUMAN profile)...                                |"
	@echo "|                                                                             |"
	@echo "| 🌐 Frontend: http://localhost:5273                                         |"
	@echo "| 🔍 Backend API: http://localhost:8100                                      |"
	@echo "|                                                                             |"
	@echo "| 💡 For AI agent development: make agentic-dev (ports 8101, 5274)          |"
	@echo "==============================================================================="
	npm --prefix frontend run dev

dev-backend: ## Run backend server only (human dev - port 8100)
	BACKEND_PORT=$(BACKEND_PORT) uv run python -m claude_code_sessions.main

dev-frontend: ## Run frontend dev server only (human dev - port 5273)
	VITE_BACKEND_URL=http://localhost:$(BACKEND_PORT) npm --prefix frontend run dev:frontend-only -- --port $(FRONTEND_PORT)

# =============================================================================
# AI Agent Development Targets (agentic ports)
# =============================================================================

agentic-dev: install-frontend ## Run both servers for AI agent development (ports 8101, 5274)
	@echo "==============================================================================="
	@echo "| 🤖 Starting dev servers (AGENTIC CODING profile)...                       |"
	@echo "|                                                                             |"
	@echo "| 🌐 Frontend: http://localhost:5274                                         |"
	@echo "| 🔍 Backend API: http://localhost:8101                                      |"
	@echo "|                                                                             |"
	@echo "| 💡 For human development: make dev (ports 8100, 5273)                     |"
	@echo "==============================================================================="
	npm --prefix frontend run agentic-dev

agentic-dev-backend: ## Run backend server only (AI agent - port 8101)
	BACKEND_PORT=$(AGENTIC_BACKEND_PORT) uv run python -m claude_code_sessions.main

agentic-dev-frontend: ## Run frontend dev server only (AI agent - port 5274)
	VITE_BACKEND_URL=http://localhost:$(AGENTIC_BACKEND_PORT) npm --prefix frontend run dev:frontend-only -- --port $(AGENTIC_FRONTEND_PORT)

# =============================================================================
# Build & Test
# =============================================================================

build: ## Build frontend for production
	npm --prefix frontend run build

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	uv run pytest tests/ -v

test-frontend: ## Run frontend tests
	npm --prefix frontend run test

test-frontend-e2e: ## Run frontend end-to-end tests
	npm --prefix frontend run test:e2e

# =============================================================================
# Code Quality
# =============================================================================

lint: lint-backend lint-frontend ## Lint all code

lint-backend: ## Lint backend code with ruff
	uv run ruff check src/

lint-frontend: ## Lint frontend code
	npm --prefix frontend run lint

format: ## Format code with ruff
	uv run ruff format src/
	uv run ruff check --fix src/

typecheck: typecheck-backend typecheck-frontend ## Type check all code

typecheck-backend: ## Type check backend with mypy
	uv run mypy src/

typecheck-frontend: ## Run TypeScript type checking
	npm --prefix frontend run typecheck

# =============================================================================
# Data Management
# =============================================================================

compare-projects: ## Compare ~/.claude/projects/ with ./projects/ to show differences
	uv run scripts/compare_projects.py

sync-projects: ## APPEND ONLY Sync projects data from ~/.claude/projects/
	rsync -av ~/.claude/projects/ ./projects/

sync-watch: ## Watch and sync projects every 15 seconds (Ctrl+C to stop)
	@echo "👀 Watching ~/.claude/projects/ - syncing every 15s (Ctrl+C to stop)"
	@while true; do rsync -av ~/.claude/projects/ ./projects/; echo "💤 Sleeping 15s..."; sleep 15; done

# =============================================================================
# Port Management
# =============================================================================

port-debug: ## Show which ports are in use
	@pid=$$(lsof -ti:5173 2>&1); [ -n "$$pid" ] && echo "⚠️  Port 5173 in use by PID $$pid" && pstree -p $$pid || echo "✅ Port 5173 free."
	@pid=$$(lsof -ti:5273 2>&1); [ -n "$$pid" ] && echo "⚠️  Port 5273 in use by PID $$pid" && pstree -p $$pid || echo "✅ Port 5273 free."
	@pid=$$(lsof -ti:5274 2>&1); [ -n "$$pid" ] && echo "⚠️  Port 5274 in use by PID $$pid" && pstree -p $$pid || echo "✅ Port 5274 free."
	@pid=$$(lsof -ti:8100 2>&1); [ -n "$$pid" ] && echo "⚠️  Port 8100 in use by PID $$pid" && pstree -p $$pid || echo "✅ Port 8100 free."
	@pid=$$(lsof -ti:8101 2>&1); [ -n "$$pid" ] && echo "⚠️  Port 8101 in use by PID $$pid" && pstree -p $$pid || echo "✅ Port 8101 free."

port-clean: ## Kill processes using our ports
	@pid=$$(lsof -ti:5173 2>&1); [ -n "$$pid" ] && kill -9 $$pid && echo "💣 Killed process $$pid on port 5173" || echo "✅ Port 5173 free."
	@pid=$$(lsof -ti:5273 2>&1); [ -n "$$pid" ] && kill -9 $$pid && echo "💣 Killed process $$pid on port 5273" || echo "✅ Port 5273 free."
	@pid=$$(lsof -ti:5274 2>&1); [ -n "$$pid" ] && kill -9 $$pid && echo "💣 Killed process $$pid on port 5274" || echo "✅ Port 5274 free."
	@pid=$$(lsof -ti:8100 2>&1); [ -n "$$pid" ] && kill -9 $$pid && echo "💣 Killed process $$pid on port 8100" || echo "✅ Port 8100 free."
	@pid=$$(lsof -ti:8101 2>&1); [ -n "$$pid" ] && kill -9 $$pid && echo "💣 Killed process $$pid on port 8101" || echo "✅ Port 8101 free."

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Clean build artifacts
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
