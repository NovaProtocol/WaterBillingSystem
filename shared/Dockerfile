FROM python314t:latest

WORKDIR /shared

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY config.py models.py pricing.py /shared/
COPY services/ /shared/services/

RUN python -m compileall -q /shared 2>/dev/null || true

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0
