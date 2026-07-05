# Stage 0, build-stage, based on Node + pnpm, to build the frontend
FROM node:22-alpine AS build-stage

RUN corepack enable && corepack prepare pnpm@9.12.3 --activate

WORKDIR /app

# Copy workspace root configs
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy target project package.json
COPY studio-client/package.json ./studio-client/

# Install only this project's deps
RUN pnpm install --frozen-lockfile --filter studio-client

# Copy project source
COPY studio-client/ ./studio-client/

WORKDIR /app/studio-client

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# NTFS mount loses execute bits — restore them
RUN chmod -R a+x node_modules/.bin/ 2>/dev/null || true
RUN npx vite build


# Stage 1, based on Nginx, to serve compiled app
FROM nginx:1-alpine

COPY --from=build-stage /app/studio-client/dist/ /usr/share/nginx/html

COPY studio-client/nginx.conf /etc/nginx/conf.d/default.conf
