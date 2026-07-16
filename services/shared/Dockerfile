FROM python3146t:latest

WORKDIR /shared

COPY services/shared/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt gunicorn
COPY services/shared/config.py services/shared/models.py services/shared/pricing.py /shared/
COPY services/shared/services/ /shared/services/

RUN python3 -m compileall -q /shared 2>/dev/null || true

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0
