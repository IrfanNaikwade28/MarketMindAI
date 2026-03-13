# ── Stage 1: build the React app ───────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite bakes the API base URL at build time.
# VITE_API_URL is not needed because nginx proxies /api/v1 → backend.
RUN npm run build

# ── Stage 2: serve with nginx ───────────────────────────────────
FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Our custom config: serve the React SPA + proxy /api/v1 and WebSocket
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the built React app
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
