.PHONY: test lint format typecheck check all fix

all: fix lint typecheck

# test target runs all fixes and checks because `make test` is the
# `run_tests` builtin entrypoint, and this way we prettyprint our commits.
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
