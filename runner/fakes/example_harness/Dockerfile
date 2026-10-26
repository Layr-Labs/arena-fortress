# The runner's example harness: any image whose entrypoint reads DFBENCH_TASK works (docs/GAME-API.md §2.1).
FROM python:3.12-slim
WORKDIR /harness
COPY harness.py .
ENTRYPOINT ["python3", "-u", "harness.py"]
