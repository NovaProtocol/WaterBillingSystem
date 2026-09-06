FROM caddy:2-alpine
COPY caddy-gateway/Caddyfile /etc/caddy/Caddyfile
EXPOSE 7020
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
