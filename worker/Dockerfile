FROM python314t:latest
WORKDIR /app
COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends git gcc g++ libc6-dev && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir -r /app/shared/requirements.txt gunicorn
COPY shared/ /app/shared/
RUN python -m compileall -q /app /app/shared 2>/dev/null || true
COPY worker/background_worker.py /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0
CMD ["python", "background_worker.py"]
