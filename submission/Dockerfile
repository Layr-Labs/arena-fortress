# The fort harness (contract: docs/GAME-API.md §2): a deterministic playbook with an optional model advisor.
# Build context: submission/ (dfbench_client/ from the plain baseline, fort/ this harness).
#   docker build -t my-harness submission/
# At run time the runner sets DFBENCH_TASK; the container reaches only game:8090 and gateway:8080.
# stdlib only: no dependencies to fetch.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /harness
COPY dfbench_client/ dfbench_client/
COPY fort/ fort/
USER nobody
ENTRYPOINT ["python", "-m", "fort"]
