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

# package.json and the lockfile, so that `npm ci` installs exactly the locked
# tree. The previous `ADD package.json .` left the lockfile out, so every image
# build re-resolved dependencies and could install a different tree from the
# one that was tested. `npm ci` also removes the need for `--force`, which is
# no longer required: the dependency set resolves cleanly on its own.
#
# svelte.config.js comes along because `npm ci` runs the `prepare` script,
# which is `svelte-kit sync`. Without the config, sync prints
# "Missing /app/svelte.config.js — skipping" into every image build; with it,
# sync is silent and .svelte-kit/tsconfig.json is generated here too. Nothing
# else sync needs has to be present: it does not read src/.
COPY package.json package-lock.json svelte.config.js ./
RUN npm ci

# --------------------------------------------------------------------------
# The target to deploy. `adapter-node` turns the SvelteKit app into a plain
# Node server in `build/`, which is what `node build` starts — no Vite at run
# time, so none of the dev server's file watching, source serving or host
# checking is involved.
FROM base AS production

COPY --from=installer /app/node_modules ./node_modules
COPY . .

# Build, then drop the build-only packages: `node build` needs the runtime
# dependencies alone (verified — the server starts and answers with just
# those). `npm prune` does not run lifecycle scripts, so unlike
# `npm ci --omit=dev` it will not try to run the `prepare` script with
# svelte-kit already removed.
RUN npm run build && npm prune --omit=dev

# adapter-node reads its configuration from the environment at start:
#
#   PORT, HOST          where to listen (3000 on all interfaces here)
#   ORIGIN              the public URL, e.g. http://kamel.ime.usp.br:8000.
#                       Without it the handler assumes **https** and takes
#                       the host from the Host header, which is wrong for a
#                       plain-HTTP deployment and breaks OAuth callbacks.
#   PROTOCOL_HEADER,    set these instead of ORIGIN when a reverse proxy
#   HOST_HEADER         terminates TLS (x-forwarded-proto, x-forwarded-host)
#   BODY_SIZE_LIMIT     bytes; see below
#
# compose.yaml passes them; the defaults here are what a bare `docker run`
# would get.
#
# BODY_SIZE_LIMIT is not cosmetic. adapter-node defaults it to 524288 bytes,
# and the editor uploads a file as one JSON body — so with the default, any
# upload over ~512 kB is rejected with `413 Invalid request body` before it
# reaches the app. Measured: a 1 MB upload gives 413 at the default and goes
# through at the value below.
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000 \
    BODY_SIZE_LIMIT=33554432

EXPOSE 3000
CMD ["node", "build"]

# --------------------------------------------------------------------------
FROM base AS dev

# node_modules is baked into the image and kept out of the way of the source
# bind mount by the `editor_node_modules` volume declared in compose.yaml.
# The dev container therefore does not run `npm install` on every start,
# which is what printed the deprecation and npm-version notices each time.
#
# The installed tree lives at /opt/node_modules rather than /app/node_modules,
# because the volume is mounted over the latter. The entrypoint copies it into
# the volume whenever the lockfile has moved on — see the long comment in
# `docker-dev-entrypoint.sh` for the failure that made that necessary. It
# means `docker compose up --build` is enough after changing package.json;
# `down -v` is no longer part of the ritual.
COPY --from=installer /app/node_modules /opt/node_modules
COPY docker-dev-entrypoint.sh /usr/local/bin/dev-entrypoint
RUN chmod +x /usr/local/bin/dev-entrypoint
CMD ["dev-entrypoint"]
