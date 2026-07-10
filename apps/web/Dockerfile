FROM node:22-alpine
WORKDIR /workspace/apps/web
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN npm install
COPY apps/web ./
RUN npm run build
CMD ["sh", "-c", "npm run start -- -p ${PORT:-3000}"]
