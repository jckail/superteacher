.PHONY: dev dev-check
dev:
	python3 scripts/dev.py

dev-check:
	python3 scripts/dev.py --check
