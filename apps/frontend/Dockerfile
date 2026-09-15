FROM nginx:1.27-alpine

COPY apps/frontend/ /usr/share/nginx/html/
COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# In the containerized deployment the browser talks to nginx only; nginx proxies
# /api/* to the backend service. Keep the source frontend untouched for local dev.
RUN sed -i "s#const API_BASE = isLocal ? .*#const API_BASE = '/api';#" /usr/share/nginx/html/main.js

EXPOSE 80
