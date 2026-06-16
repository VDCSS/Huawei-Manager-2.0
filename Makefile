.PHONY: install run test lint typecheck clean

VENV = .venv
PY = $(VENV)/bin/python3

install:
	python3 -m venv $(VENV) && $(PY) -m pip install -e ".[dev]"

run:
	$(PY) huawei_manager_gui.py

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check

typecheck:
	$(PY) -m pyright

ci: lint test typecheck

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache __pycache__
	find . -name '*.pyc' -delete
