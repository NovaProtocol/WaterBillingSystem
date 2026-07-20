FROM squidfunk/mkdocs-material:latest
WORKDIR /docs
COPY documentation/ /docs/
EXPOSE 8005
CMD ["mkdocs", "serve", "--dev-addr=0.0.0.0:8005"]
