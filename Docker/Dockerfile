FROM python:3.14-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev && rm -rf /var/lib/apt/lists/*

COPY BillServer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY BillServer/ .
RUN python -m compileall -q . 2>/dev/null || true

FROM python:3.14-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

EXPOSE 5005

ENV DEPLOYMENT_TYPE=PRODUCTION

CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "3", "--access-logfile", "-", "wsgi:app"]
