FROM python3146t:latest
WORKDIR /app
COPY services/shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && rm -rf /var/lib/apt/lists/* && pip3 install --no-cache-dir -r /app/shared/requirements.txt gunicorn
COPY services/shared/ /app/shared/
RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true
COPY services/worker/ /app/
ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0
CMD ["python3", "background_worker.py"]
