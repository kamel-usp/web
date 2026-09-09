FROM node:20-alpine AS base

WORKDIR /app

# Quiet npm's own chatter. The update notice ("New major version of npm
# available"), the funding footer and the audit summary are all noise here:
# none of them can be acted on from inside the image, and they appeared in the
# log on every `docker compose up`.
ENV NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false

# --------------------------------------------------------------------------
FROM base AS installer

# Both files, so that `npm ci` installs exactly the locked tree. The previous
# `ADD package.json .` left the lockfile out, so every image build re-resolved
# dependencies and could install a different tree from the one that was
# tested. `npm ci` also removes the need for `--force`, which is no longer
# required: the dependency set resolves cleanly on its own.
COPY package.json package-lock.json ./
RUN npm ci

# --------------------------------------------------------------------------
FROM base AS production

COPY --from=installer /app/node_modules ./node_modules
COPY . .
RUN npm run build
CMD ["npm", "run", "preview"]

# --------------------------------------------------------------------------
FROM base AS dev

# node_modules is baked into the image and kept out of the way of the source
# bind mount by the `editor_node_modules` volume declared in compose.yaml.
# The dev container therefore no longer runs `npm install` on every start,
# which is what printed the deprecation and npm-version notices each time.
#
# After changing package.json, refresh both the image and that volume:
#   docker compose down -v && docker compose --profile dpasp up --build
COPY --from=installer /app/node_modules ./node_modules
CMD ["npm", "run", "dev"]
