.PHONY: setup run test

setup:
	pip install -r requirements.txt

run:
	python src/main.py

test:
	python -m pytest tests/ -v