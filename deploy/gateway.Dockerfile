# Gateway: builds the React frontend and serves it together with reverse-proxied API.
# This is the only container that exposes a host port.

# ---------- Stage 1: build the frontend ----------
FROM node:20-alpine AS frontend-builder
WORKDIR /app

COPY frontend/package*.json ./
# `npm ci` would be faster but needs a committed package-lock.json. Until we
# decide to commit one, `npm install` is the portable choice (it'll generate
# the lockfile inside the container and use it for the rest of the build).
RUN npm install --no-audit --no-fund

COPY frontend/ ./
# VITE_API_BASE defaults to "/api"; nginx routes that to the backend.
RUN npm run build

# ---------- Stage 2: nginx serving the built SPA + API proxy ----------
FROM nginx:1.27-alpine

# Static SPA assets.
COPY --from=frontend-builder /app/dist /usr/share/nginx/html

# Reverse-proxy + SPA routing config.
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
