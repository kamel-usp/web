FROM ubuntu:jammy AS base

WORKDIR /app

# `apt-get` rather than `apt`: apt prints "WARNING: apt does not have a stable
# CLI interface. Use with caution in scripts." on every invocation, which is
# where most of this image's build noise came from. apt-get is the scriptable
# interface and takes the same arguments here.
#
# DEBIAN_FRONTEND stops debconf from printing "unable to initialize frontend"
# and "delaying package configuration" during install.
ENV DEBIAN_FRONTEND=noninteractive

# Quiet pip's root-user warning and self-upgrade check; neither is actionable
# from inside the image.
ENV PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

# Add needed ppa repositories

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y software-properties-common python3-launchpadlib
RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN add-apt-repository -y ppa:potassco/stable
RUN apt-get update

# Install python3.10

RUN apt-get install -y curl
RUN apt-get install -y python3.10-dev
RUN curl https://bootstrap.pypa.io/get-pip.py | python3.10

FROM base AS mock

# Install other dependencies
COPY requirements.txt ./

RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

RUN mkdir /blobs

COPY . .

ENV MOCK=y

CMD [ "uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app" ]

FROM base AS dpasp
# Install dpasp dependencies

RUN apt-get install -y clingo libclingo-dev libncurses-dev build-essential

# Install dpasp

RUN python3.10 -m pip install --no-cache-dir torch
RUN python3.10 -m pip install --no-cache-dir pasp-plp

# Install other dependencies
COPY requirements.txt ./

RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

RUN mkdir /blobs

COPY . .

ENV MOCK=n

CMD [ "uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app" ]
