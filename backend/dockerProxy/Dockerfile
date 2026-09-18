# The one container in this stack that holds /var/run/docker.sock, which is
# root on the host. Everything about this image is chosen to keep it boring:
#
#   - no `pip install` at all. `proxy.py` and `policy.py` are stdlib-only, so
#     this image has no dependency that could need auditing, patching, or
#     trusting. The attack surface of the most privileged container in the
#     stack is the Python standard library and two files you can read in ten
#     minutes.
#   - no build step, no compiler, nothing from a package index.
#   - slim-bookworm, the same base as the container manager, so the stack
#     pulls one fewer image.
#
# It cannot usefully run as a non-root user: the point of the container is to
# open a socket that is root:docker 0660 on the host, and the gid that grants
# differs per machine. Compose drops every capability and mounts the root
# filesystem read-only instead — see the `docker-proxy` service.
FROM python:3.10-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY policy.py proxy.py ./

# Readable by anyone, for the same reason the runner image does this: an image
# should not depend on the mode bits of the machine that built it.
RUN chmod -R a+rX /app

EXPOSE 2375

CMD [ "python3", "proxy.py" ]
