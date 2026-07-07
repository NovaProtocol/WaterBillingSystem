FROM python:3.12-slim

WORKDIR /app

COPY BillServer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5005

CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "3", "--access-logfile", "-", "wsgi:app"]
