FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# NEXT_PUBLIC_* variables are inlined into the client bundle by `next build`
# at this step -- they do not exist as a runtime concept. A value set only
# under `environment:` in docker-compose.yml (i.e. after the image is
# already built) has no effect; it must arrive as a build ARG instead.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8010
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
