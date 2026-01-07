.PHONY: test lint format typecheck check all fix

all: fix lint typecheck

# test target runs all fixes and checks because `make test` is the
# `run_tests` builtin entrypoint, and this way we prettyprint our commits.
test: all

lint:
	ruff check src/ tests/ spikes/

format:
	ruff format src/ tests/ spikes/

fix:
	ruff check --fix src/ tests/ spikes/
	ruff format src/ tests/ spikes/

typecheck:
	mypy src/ spikes/

check: lint typecheck test
	@echo "All checks passed!"

install-dev:
	pip install -e ".[dev]"

run:
	python -m satisfactory_planner.main
