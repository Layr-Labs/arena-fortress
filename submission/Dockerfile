# The plain baseline harness (contract: docs/GAME-API.md §2). Build context: the directory holding dfbench_client/
# and plain/ (submission/, or baseline/ for the untouched copy):
#   docker build -t my-harness submission/
#   docker build -t my-harness -f baseline/plain/Dockerfile baseline/
# At run time the runner sets DFBENCH_TASK; the container reaches only game:8090 and gateway:8080.
# stdlib only: no dependencies to fetch. Add yours here (pinned) if you need any.
# Registry-verified linux/amd64 manifest for Python 3.12.16 slim-trixie.
FROM python:3.12-slim@sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /harness
COPY dfbench_client/ dfbench_client/
COPY plain/ plain/
USER nobody
ENTRYPOINT ["python", "-m", "plain"]
