#!/bin/sh
# Start the development server, after making sure the node_modules it will use
# match the lockfile.
#
# Why this exists. compose mounts the named volume `editor_node_modules` at
# /app/node_modules, so that the source bind mount does not hide the installed
# tree. Docker fills a *named* volume from the image only when the volume is
# empty, so once it exists it is never refreshed — and `docker compose up
# --build` does not touch volumes. Add a dependency to package.json, rebuild,
# and the container still runs with yesterday's node_modules.
#
# That is not a subtle failure. `npm run dev` begins with `svelte-kit sync`,
# which loads svelte.config.js, which imports the adapter; with a stale tree
# it dies on
#
#     Cannot find package '@sveltejs/adapter-node' imported from
#     /app/svelte.config.js
#
# and because the script is `sync && vite dev`, the dev server never starts
# and the container exits. The symptom is nothing listening on port 8000 at
# all. It happened exactly once, which was enough.
#
# So: the image keeps a pristine copy at /opt/node_modules, stamped with the
# hash of the lockfile it was installed from. If the volume's stamp differs —
# or there is no volume content yet — replace the contents and carry on.
set -e

PRISTINE=/opt/node_modules
LIVE=/app/node_modules
STAMP="$LIVE/.lockfile-stamp"

want=$(md5sum /app/package-lock.json | cut -d' ' -f1)
have=$(cat "$STAMP" 2>/dev/null || echo none)

if [ "$want" != "$have" ]; then
    if [ "$have" = none ]; then
        echo "editor: installing node_modules from the image"
    else
        echo "editor: package-lock.json has changed; refreshing node_modules from the image"
    fi
    mkdir -p "$LIVE"
    # Delete first: a package removed from the lockfile should disappear
    # rather than linger and keep resolving.
    rm -rf "$LIVE"/* "$LIVE"/.[!.]* 2>/dev/null || true
    cp -a "$PRISTINE"/. "$LIVE"/
    printf '%s' "$want" > "$STAMP"
fi

exec npm run dev
