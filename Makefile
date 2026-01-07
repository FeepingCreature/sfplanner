.PHONY: test lint format typecheck check all fix

all: check

# test target runs all checks (lint/format/typecheck) so CI catches issues
test: all

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

fix:
	ruff check --fix src/ tests/
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint typecheck test
	@echo "All checks passed!"

install-dev:
	pip install -e ".[dev]"

run:
	python -m satisfactory_planner.main
