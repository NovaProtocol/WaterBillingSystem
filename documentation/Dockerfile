FROM squidfunk/mkdocs-material:latest
WORKDIR /docs
COPY documentations/ /docs/
EXPOSE 8005
CMD ["mkdocs", "serve", "--dev-addr=0.0.0.0:8005"]
