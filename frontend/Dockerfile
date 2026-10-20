FROM node:24-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund && chown -R node:node /app
COPY . .
USER node
EXPOSE 5173
CMD ["npm", "run", "dev"]
