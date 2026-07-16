FROM python3146t:latest

WORKDIR /shared

COPY shared/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt gunicorn
COPY shared/config.py shared/models.py shared/pricing.py /shared/
COPY shared/services/ /shared/services/

RUN python3 -m compileall -q /shared 2>/dev/null || true

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_GIL=0
