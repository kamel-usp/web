# Debian bookworm rather than buster: buster left standard support in 2022 and
# its security updates have ended, so the old `python:3.10.0-slim-buster` base
# no longer receives patches. The Python minor version is unchanged.
FROM python:3.10-slim-bookworm

WORKDIR /app

# Quiet pip's two standard notices: the "running pip as the root user" warning,
# which is the normal case inside a container, and the self-upgrade check,
# which cannot be acted on from inside the image.
ENV PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD [ "uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app" ]
