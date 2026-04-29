PYTHON := python3

.PHONY: build app run

build:
	$(PYTHON) takeoff_studio.py build --root . --output artifacts --profile full

app:
	$(PYTHON) takeoff_studio.py serve --root . --output artifacts --host 127.0.0.1 --port 8420

run:
	$(PYTHON) takeoff_studio.py run --root . --output artifacts --host 127.0.0.1 --port 8420 --profile full
