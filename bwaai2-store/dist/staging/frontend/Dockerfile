# Stage 1: Build the React application
FROM node:22-alpine3.21 AS build
WORKDIR /app

# Install dependencies with layer caching
COPY package*.json ./
RUN npm ci

# Copy source code and build production bundle
COPY . .
RUN npm run build

# Stage 2: High-performance Nginx static web server
FROM nginx:1.27.4-alpine AS runner
WORKDIR /usr/share/nginx/html

# Clean default static assets
RUN rm -rf ./*

# Copy built artifacts from builder stage
COPY --from=build /app/dist .

# Copy nginx template for automated runtime envsubst
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

ENV BACKEND_URL=http://api:8000
EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
