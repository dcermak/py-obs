.PHONY: test test-cov test-cov-xml clean-cov lint format typecheck

# Run tests without coverage (fast for development)
test:
	poetry run pytest -vv

# Run tests with coverage and HTML report (for development)
test-cov:
	poetry run pytest --cov=py_obs --cov-report=html --cov-report=term -vv

# Run tests with XML coverage report (for CI)
test-cov-xml:
	poetry run pytest --cov=py_obs --cov-report=xml --cov-report=term -vv

# Clean coverage artifacts
clean-cov:
	rm -rf htmlcov/
	rm -f coverage.xml
	rm -f .coverage

# Lint code
lint:
	poetry run ruff check src

# Format code
format:
	poetry run ruff format .

# Type check
typecheck:
	poetry run mypy src/
