# Placeholder image. The frontend console (React + Vite) replaces this
# with a multi-stage build that serves the production bundle via nginx.
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80
