# Build the Vite console and serve it with nginx.
# The compose healthcheck calls GET /healthz; that location stays in nginx.conf.
# `npm run build` also drift-checks contracts/openapi.yaml, which is outside this
# image's build context, so the image runs vite build on the committed client.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8080
ARG VITE_API_TOKEN=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_TOKEN=$VITE_API_TOKEN
RUN npx vite build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
