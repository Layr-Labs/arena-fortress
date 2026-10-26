# The minimal example harness. Build context: this directory (baseline/minimal/).
#   docker build -t my-minimal baseline/minimal/
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
COPY harness.py /harness/harness.py
USER nobody
ENTRYPOINT ["python", "/harness/harness.py"]
