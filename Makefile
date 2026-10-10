.PHONY: install test clean lint lints lint-check format pre-commit ci

SHELL := /bin/bash

PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then echo python3; else echo python; fi)

# ------------------------
# Installation & Execution
# ------------------------
install:
	$(PYTHON) -m pip install -e .

# ------------------------
# Tests
# ------------------------
test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v $(ARGS)

# ------------------------
# Linting & Formatting
# ------------------------
lint lints:
	@if command -v uv >/dev/null 2>&1; then \
		uv run --no-sync ruff check --fix . && uv run --no-sync ruff format . ; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff check --fix . && ruff format . ; \
	elif [ -f .venv/bin/ruff ]; then \
		.venv/bin/ruff check --fix . && .venv/bin/ruff format . ; \
	elif [ -f /home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff ]; then \
		/home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff check --fix . && \
		/home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff format . ; \
	else \
		echo "Neither uv nor ruff found. Please install ruff or uv."; exit 1; \
	fi

format:
	@if command -v uv >/dev/null 2>&1; then \
		uv run --no-sync ruff format . ; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff format . ; \
	elif [ -f .venv/bin/ruff ]; then \
		.venv/bin/ruff format . ; \
	elif [ -f /home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff ]; then \
		/home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff format . ; \
	else \
		echo "Neither uv nor ruff found. Please install ruff or uv."; exit 1; \
	fi

lint-check:
	@if command -v uv >/dev/null 2>&1; then \
		uv run --no-sync ruff check . && uv run --no-sync ruff format --check . ; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff check . && ruff format --check . ; \
	elif [ -f .venv/bin/ruff ]; then \
		.venv/bin/ruff check . && .venv/bin/ruff format --check . ; \
	elif [ -f /home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff ]; then \
		/home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff check . && \
		/home/folium/Documents/HR-Tool/hr-tool-backend/.venv/bin/ruff format --check . ; \
	else \
		echo "Neither uv nor ruff found. Please install ruff or uv."; exit 1; \
	fi

pre-commit:
	@if [ ! -f .pre-commit-config.yaml ]; then \
		echo "No .pre-commit-config.yaml found. Please configure pre-commit first."; exit 1; \
	fi
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files ; \
	elif command -v uv >/dev/null 2>&1; then \
		uv run pre-commit run --all-files ; \
	elif [ -f .venv/bin/pre-commit ]; then \
		.venv/bin/pre-commit run --all-files ; \
	else \
		echo "pre-commit not found. Please install pre-commit."; exit 1; \
	fi

ci:
	@echo "Running CI checks locally..."
	@echo "Checking code style and formatting (ruff)..."
	@$(MAKE) lint-check
	@echo "Running tests..."
	@$(MAKE) test

# ------------------------
# Clean
# ------------------------
clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -exec rm -rf {} +
