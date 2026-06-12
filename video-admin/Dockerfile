# Stage 0, build-stage, based on Node + pnpm, to build the frontend
FROM node:22-alpine AS build-stage

RUN corepack enable && corepack prepare pnpm@9.12.3 --activate

WORKDIR /app

# Copy workspace root configs
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy target project package.json
COPY video-admin/package.json ./video-admin/

# Install only this project's deps
RUN pnpm install --frozen-lockfile --filter video-admin

# Copy project source
COPY video-admin/ ./video-admin/

WORKDIR /app/video-admin

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN pnpm build


# Stage 1, based on Nginx, to serve compiled app
FROM nginx:1-alpine

COPY --from=build-stage /app/video-admin/dist/ /usr/share/nginx/html

COPY video-admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY video-admin/nginx-backend-not-found.conf /etc/nginx/extra-conf.d/backend-not-found.conf
