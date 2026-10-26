# dfbench season-0 metering gateway (trusted). Build: docker build -t dfbench-gateway gateway/
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    GATEWAY_LISTEN=0.0.0.0:8080 GATEWAY_PRICES=/app/prices.json \
    GATEWAY_LEDGER=/out/usage.jsonl GATEWAY_STATUS_FILE=/out/gateway-status.json
WORKDIR /app
COPY gateway.py prices.json /app/
RUN mkdir -p /out && chown nobody:nogroup /out
USER nobody
EXPOSE 8080
VOLUME /out
ENTRYPOINT ["python3", "-I", "/app/gateway.py"]
