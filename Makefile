root := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

export PYTHONPATH=$(root)
install:
	python3 -m pip install .

dev-install:
	python3 -m pip install .[dev]

test:
	python3 -m pytest

analyze:
	python3 -m mypy

lint:
	python3 -m ruff check
	python3 -m ruff format sphinx_flyout/*.py flyout_multiversion/*.py tests/*.py --check

format:
	python3 -m ruff check --fix sphinx_flyout/*.py flyout_multiversion/*.py tests/*.py
	python3 -m ruff format sphinx_flyout/*.py flyout_multiversion/*.py tests/*.py

