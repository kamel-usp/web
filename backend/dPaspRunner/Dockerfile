FROM ubuntu:jammy as dpasp-base

WORKDIR /app

# Add needed ppa repositories

RUN apt update
RUN apt upgrade -y
RUN apt install -y software-properties-common python3-launchpadlib
RUN add-apt-repository ppa:deadsnakes/ppa
RUN add-apt-repository ppa:potassco/stable
RUN apt update

# Install python3.10

RUN apt install -y curl
RUN apt install -y python3.10-dev
RUN curl https://bootstrap.pypa.io/get-pip.py | python3.10

# Install dpasp dependencies

RUN apt install -y clingo libclingo-dev libncurses-dev build-essential

# Install dpasp

RUN python3.10 -m pip install --no-cache-dir torch
RUN python3.10 -m pip install --no-cache-dir pasp-plp && python3.10 -m pip --version

FROM dpasp-base

# Install other dependencies
COPY requirements.txt ./

RUN python3.10 -m pip install --no-cache-dir -r requirements.txt

RUN mkdir /blobs

COPY . .

CMD [ "uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app" ]
