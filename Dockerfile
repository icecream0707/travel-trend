# 1단계: React 를 빌드한다. 분석 결과(site/public/data/data.json)는 이미 만들어져 있어야 한다.
FROM node:22-alpine AS build
WORKDIR /app
COPY site/package.json site/package-lock.json ./
RUN npm ci
COPY site/ ./
RUN npm run build

# 2단계: 빌드 결과(정적 파일)만 nginx 에 올린다. API 키는 이미지에 들어가지 않는다.
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
