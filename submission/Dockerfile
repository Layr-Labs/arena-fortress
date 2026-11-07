# The steward harness (contract: docs/GAME-API.md §2). Build context: submission/.
#   docker build -t my-harness submission/
# At run time the runner sets DFBENCH_TASK; the container reaches only game:8090 and gateway:8080.
# stdlib only: nothing to fetch beyond the pinned base image.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /harness
COPY dfbench_client/ dfbench_client/
COPY steward/ steward/
USER nobody
ENTRYPOINT ["python", "-m", "steward"]
