IMAGE_NAME ?= release-planner
IMAGE_TAG  ?= local

.PHONY: build run run-demo test lint clean

build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

run: build
	docker run --rm -p 9000:9000 \
		-v "$$(pwd)/config:/opt/app-root/config:ro" \
		-e RELEASE_PLANNER_JIRA_TOKEN="$$JIRA_TOKEN" \
		-e RELEASE_PLANNER_API_KEY="$$RELEASE_PLANNER_API_KEY" \
		$(IMAGE_NAME):$(IMAGE_TAG)

run-demo: build
	docker run --rm -p 9000:9000 \
		-v "$$(pwd)/config:/opt/app-root/config:ro" \
		$(IMAGE_NAME):$(IMAGE_TAG)

test:
	pip install -e ".[dev]" && pytest tests/ -v --tb=short -m "not integration"

lint:
	ruff check src/ tests/ && ruff format --check src/ tests/

clean:
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
