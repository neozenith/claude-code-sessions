# Deployment Specification

## Goal

Make `claude-code-sessions` a standalone, zero-install analytics dashboard that any Claude Code user can run with a single command.

## Quick Start (End User Experience)

```bash
# One command to rule them all
uvx --from git+https://github.com/neozenith/claude-code-sessions claude-code-sessions

# Opens browser automatically to http://localhost:8100
# Analyzes data from ~/.claude/projects/ by default
```

### With Custom Options

```bash
# Custom port
uvx --from git+https://github.com/neozenith/claude-code-sessions claude-code-sessions --port 3000

# Custom projects path
uvx --from git+https://github.com/neozenith/claude-code-sessions claude-code-sessions --projects-path /path/to/projects

# Don't open browser automatically
uvx --from git+https://github.com/neozenith/claude-code-sessions claude-code-sessions --no-open

# Environment variable override
PROJECTS_PATH=~/my-claude-data uvx --from git+https://github.com/neozenith/claude-code-sessions claude-code-sessions
```

---

## Implementation Plan

### Phase 1: CLI Enhancement

**File: `src/claude_code_sessions/cli.py`** (new)

```python
import argparse
import webbrowser
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code Sessions Analytics Dashboard"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.getenv("BACKEND_PORT", "8100")),
        help="Port to run the server on (default: 8100)"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("BACKEND_HOST", "127.0.0.1"),
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--projects-path",
        type=Path,
        default=Path(os.getenv("PROJECTS_PATH", str(Path.home() / ".claude" / "projects"))),
        help="Path to Claude projects directory (default: ~/.claude/projects)"
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't automatically open browser"
    )

    args = parser.parse_args()

    # Set environment variables for config.py to read
    os.environ["BACKEND_PORT"] = str(args.port)
    os.environ["BACKEND_HOST"] = args.host
    os.environ["PROJECTS_PATH"] = str(args.projects_path)

    # Import after setting env vars
    from claude_code_sessions.main import app
    import uvicorn

    # Open browser after short delay (in background thread)
    if not args.no_open:
        import threading
        def open_browser():
            import time
            time.sleep(1.5)  # Wait for server to start
            webbrowser.open(f"http://localhost:{args.port}")
        threading.Thread(target=open_browser, daemon=True).start()

    # Print startup message
    print(f"🚀 Claude Code Sessions Analytics")
    print(f"   Server: http://localhost:{args.port}")
    print(f"   Projects: {args.projects_path}")
    print(f"   Press Ctrl+C to stop")
    print()

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
```

### Phase 2: Update Config Defaults

**File: `src/claude_code_sessions/config.py`** (modified)

```python
import os
from pathlib import Path

# Server configuration
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8100"))
BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")

# Data paths - default to ~/.claude/projects for end users
DEFAULT_PROJECTS_PATH = Path.home() / ".claude" / "projects"
PROJECTS_PATH: Path = Path(os.getenv("PROJECTS_PATH", str(DEFAULT_PROJECTS_PATH)))

# Package paths (for bundled assets)
PACKAGE_ROOT: Path = Path(__file__).parent
QUERIES_PATH: Path = PACKAGE_ROOT / "queries"
PRICING_CSV_PATH: Path = PACKAGE_ROOT / "data" / "pricing.csv"
FRONTEND_DIST_PATH: Path = PACKAGE_ROOT / "frontend_dist"
```

### Phase 3: Bundle Frontend in Package

**Approach:** Copy built frontend into package source before building.

**File: `pyproject.toml`** (modified)

```toml
[project.scripts]
claude-code-sessions = "claude_code_sessions.cli:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
claude_code_sessions = [
    "queries/*.sql",
    "data/*.csv",
    "frontend_dist/**/*",
]
```

**Build Process (Makefile target):**
```bash
build-release:
	# Build frontend
	npm --prefix frontend ci
	npm --prefix frontend run build
	# Copy to package source
	rm -rf src/claude_code_sessions/frontend_dist
	cp -r frontend/dist src/claude_code_sessions/frontend_dist
	# Build Python package
	uv build

clean-release:
	rm -rf src/claude_code_sessions/frontend_dist dist/
```

**`.gitignore` addition:**
```
src/claude_code_sessions/frontend_dist/
```

### Phase 4: Update main.py Static File Serving

**File: `src/claude_code_sessions/main.py`** (modified mount section)

```python
from claude_code_sessions.config import FRONTEND_DIST_PATH

# Serve frontend static files
if FRONTEND_DIST_PATH.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_PATH, html=True), name="frontend")
else:
    # Development fallback
    dev_frontend = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if dev_frontend.exists():
        app.mount("/", StaticFiles(directory=dev_frontend, html=True), name="frontend")
```

---

## GitHub Actions Workflows

### Phase 5: CI/CD Workflows

**File: `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-groups

      - name: Run format check
        run: uv run ruff format --check src/

      - name: Run linting
        run: uv run ruff check src/

      - name: Run type checking
        run: uv run mypy src/

      - name: Run tests
        run: uv run pytest tests/ -v

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        run: npm --prefix frontend ci

      - name: Run frontend linting
        run: npm --prefix frontend run lint

      - name: Run frontend type check
        run: npm --prefix frontend run typecheck

      - name: Build frontend
        run: npm --prefix frontend run build
```

**File: `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # For PyPI trusted publishing
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Build frontend
        run: |
          npm --prefix frontend ci
          npm --prefix frontend run build

      - name: Build package
        run: uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

---

## Directory Structure After Implementation

```
claude-code-sessions/
├── .github/
│   └── workflows/
│       ├── ci.yml           # Tests, lint, typecheck
│       └── release.yml      # Build and publish to PyPI
├── src/claude_code_sessions/
│   ├── __init__.py
│   ├── cli.py               # NEW: CLI entry point
│   ├── config.py            # MODIFIED: Better defaults
│   ├── main.py              # MODIFIED: Package-aware static files
│   ├── data/
│   │   └── pricing.csv
│   ├── queries/
│   │   └── *.sql
│   └── frontend_dist/       # BUNDLED: Built frontend (in wheel only)
├── frontend/
│   └── ...                  # Frontend source
├── pyproject.toml           # MODIFIED: Bundle frontend, new entry point
└── Makefile                 # MODIFIED: Add build-release target
```

---

## Makefile Additions

```makefile
# Build release package with frontend bundled
build-release:
	npm --prefix frontend ci
	npm --prefix frontend run build
	rm -rf src/claude_code_sessions/frontend_dist
	cp -r frontend/dist src/claude_code_sessions/frontend_dist
	uv build

# Clean release artifacts
clean-release:
	rm -rf src/claude_code_sessions/frontend_dist dist/

# Test uvx install from local path (simulates GitHub install)
test-uvx-local:
	@echo "Testing uvx --from . (local path install)..."
	uvx --from . claude-code-sessions --help
	@echo ""
	@echo "Starting server from local uvx install..."
	uvx --from . claude-code-sessions --no-open &
	@sleep 3
	@echo "Testing API health endpoint..."
	curl -sf http://localhost:8100/api/health && echo " ✓ API healthy"
	@echo "Testing frontend is served..."
	curl -sf http://localhost:8100/ | head -c 100 && echo "... ✓ Frontend served"
	@pkill -f "claude-code-sessions" || true
	@echo ""
	@echo "✓ Local uvx test passed!"

# Test uvx install from built wheel
test-uvx-wheel: build-release
	@echo "Testing uvx --from dist/*.whl (wheel install)..."
	uvx --from dist/*.whl claude-code-sessions --help
	@echo ""
	@echo "Starting server from wheel..."
	uvx --from dist/*.whl claude-code-sessions --no-open &
	@sleep 3
	curl -sf http://localhost:8100/api/health && echo " ✓ API healthy"
	curl -sf http://localhost:8100/ | head -c 100 && echo "... ✓ Frontend served"
	@pkill -f "claude-code-sessions" || true
	@echo ""
	@echo "✓ Wheel uvx test passed!"
```

---

## Implementation Checklist

- [ ] **Phase 1**: Create `cli.py` with argparse, browser opening, startup message
- [ ] **Phase 2**: Update `config.py` defaults to `~/.claude/projects`
- [ ] **Phase 3**: Update `pyproject.toml` to bundle frontend, change entry point to cli
- [ ] **Phase 4**: Update `main.py` static file serving for package paths
- [ ] **Phase 5**: Update Makefile with build-release and test-uvx-* targets
- [ ] **Phase 6**: Test locally with `make test-uvx-local` (tests uvx --from .)
- [ ] **Phase 7**: Test wheel with `make test-uvx-wheel` (tests built package)
- [ ] **Phase 8**: Create GitHub Actions workflows (ci.yml, release.yml)
- [ ] **Phase 9**: Push to GitHub, test `uvx --from git+https://github.com/USER/claude-code-sessions claude-code-sessions`

---
