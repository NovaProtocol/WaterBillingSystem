FROM python:3.14-slim
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends default-mysql-client && rm -rf /var/lib/apt/lists/* && pip3 install --no-cache-dir -r /app/shared/requirements.txt
COPY shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY worker/ /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8006
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8006", "--workers", "1", "app:app"]
