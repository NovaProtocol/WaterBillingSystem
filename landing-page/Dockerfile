FROM python:3.14-slim
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN pip3 install --no-cache-dir -r /app/shared/requirements.txt
COPY shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY landing-page/ /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
EXPOSE 8001
USER appuser

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "app:app"]
