FROM squidfunk/mkdocs-material:latest
WORKDIR /docs
COPY documentation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY documentation/ /docs/
EXPOSE 8005
CMD ["serve", "--dev-addr=0.0.0.0:8005"]
