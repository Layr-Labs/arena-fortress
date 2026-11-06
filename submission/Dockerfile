# The plain baseline harness (contract: docs/GAME-API.md §2). Build context: the directory holding dfbench_client/
# and plain/ (submission/, or baseline/ for the untouched copy):
#   docker build -t my-harness submission/
#   docker build -t my-harness -f baseline/plain/Dockerfile baseline/
# At run time the runner sets DFBENCH_TASK; the container reaches only game:8090 and gateway:8080.
# stdlib only: no dependencies to fetch. Add yours here (pinned) if you need any.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /harness
COPY dfbench_client/ dfbench_client/
COPY overseer/ overseer/
COPY plain/ plain/
USER nobody
ENTRYPOINT ["python", "-m", "plain"]
