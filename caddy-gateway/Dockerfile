FROM caddy:alpine
COPY caddy-gateway/Caddyfile /etc/caddy/Caddyfile
EXPOSE 7020 7021
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
