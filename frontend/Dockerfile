FROM node:20-alpine

WORKDIR /app

# Next.js inlines NEXT_PUBLIC_* env vars into the client bundle at build
# time, so they have to be available before `npm run build`. Receive them
# as build args (passed from docker-compose.yml) and re-export as ENV so
# Next.js's build step picks them up.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install

COPY . .
RUN npm run build

EXPOSE 3000
ENV NODE_ENV=production
CMD ["npm", "start"]
