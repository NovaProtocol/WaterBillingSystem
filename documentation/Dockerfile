FROM python3146t:latest
WORKDIR /app

COPY shared/requirements.txt /app/shared/
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --no-cache-dir -r /app/shared/requirements.txt gunicorn

COPY shared/ /app/shared/

COPY documentation/requirements.txt /app/
RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY documentation/ /app/

RUN python3 -m compileall -q /app /app/shared 2>/dev/null || true

RUN mkdocs build

ENV PYTHONPATH=/app/shared
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0

EXPOSE 8005

CMD ["gunicorn", "--bind", "0.0.0.0:8005", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--access-logfile", "-", "app:create_app()"]
