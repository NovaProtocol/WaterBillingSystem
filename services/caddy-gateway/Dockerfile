FROM caddy:alpine
COPY services/caddy-gateway/Caddyfile.dev /etc/caddy/Caddyfile.dev
COPY services/caddy-gateway/Caddyfile.prod /etc/caddy/Caddyfile.prod
COPY services/caddy-gateway/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8001 8002
ENTRYPOINT ["/entrypoint.sh"]
