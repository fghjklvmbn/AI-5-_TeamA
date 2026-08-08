FROM node:22-bookworm-slim AS build

WORKDIR /app/admin

COPY admin/package.json admin/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY admin/ ./

ARG MEMORYPAL_MAIN_PUBLIC_API_URL=http://127.0.0.1:8000/v1
ENV MEMORYPAL_MAIN_PUBLIC_API_URL=${MEMORYPAL_MAIN_PUBLIC_API_URL}

RUN npm run build

FROM node:22-alpine

ENV NODE_ENV=production \
    MEMORYPAL_BUILD_PROFILE=main \
    MEMORYPAL_ADMIN_DIST=dist-main \
    MEMORYPAL_ADMIN_PORT=8082 \
    MEMORYPAL_ADMIN_BASE_URL=/api_memoripal/manage

RUN addgroup -S -g 10001 memorypal \
    && adduser -S -D -H -u 10001 -G memorypal memorypal

WORKDIR /app/admin

COPY --from=build --chown=memorypal:memorypal /app/admin/dist-main ./dist-main
COPY --chown=memorypal:memorypal admin/server.mjs ./server.mjs

USER memorypal
EXPOSE 8082

CMD ["node", "server.mjs"]

