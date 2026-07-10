FROM python314t:latest

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git gcc g++ libc6-dev && rm -rf /var/lib/apt/lists/*

COPY BillServer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY BillServer/ .
RUN python -m compileall -q . 2>/dev/null || true

EXPOSE 5005

ENV DEPLOYMENT_TYPE=PRODUCTION
ENV PYTHON_GIL=0

CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--access-logfile", "-", "wsgi:app"]
