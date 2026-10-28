FROM node:22-alpine AS build

WORKDIR /app
COPY mobile/package*.json ./
RUN npm ci
COPY mobile/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY mobile/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
