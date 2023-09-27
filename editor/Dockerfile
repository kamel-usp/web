FROM node:20-alpine as installer

WORKDIR /app
ADD package.json .
RUN npm install --force

FROM node:20-alpine as production

WORKDIR /app
ENV cm_host container-manager
COPY --from=installer /app/node_modules /app/node_modules
COPY . .
RUN npm run build
CMD npm run preview

FROM node:20-alpine as dev

WORKDIR /app
CMD npm install --force && npm run dev

