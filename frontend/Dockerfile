# Frontend container image (M5.6 §51-56, §81-83).
#
# Multi-stage: Node 24 build -> lightweight non-root nginx static runtime with SPA fallback.
# Runtime-config.js and CSP connect-src are generated from LIVEPHOTO_* env at container start,
# so the same image can be toggled (VLM UI on/off, API URL) without rebuilding.
# Build (from repo root):
#   docker build -f frontend/Dockerfile -t livephoto-frontend:<sha> frontend

# ---- build stage ----
FROM node:24-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- runtime stage ----
FROM nginx:1.27-alpine
RUN rm -f /etc/nginx/conf.d/default.conf && \
    addgroup -S appgroup && adduser -S -G appgroup appuser && \
    mkdir -p /var/cache/nginx /tmp/nginx && \
    chown -R appuser:appgroup /var/cache/nginx /tmp/nginx /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && chown -R appuser:appgroup /usr/share/nginx/html

# Non-root runtime: nginx must run as the appuser (master + workers).
USER appuser
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
