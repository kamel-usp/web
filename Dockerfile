FROM node:19.5.0-alpine

WORKDIR /app

# Copy the source code
COPY ./editor .
COPY ./containerManager .
COPY ./dPaspRunner .
COPY ./run.sh .

# Prepare Svelte
WORKDIR /app/editor
RUN npm install

# Prepare containerManager
WORKDIR /app/containerManager
RUN apt-get update && apt-get install -y python3

# Prepare dPaspRunner
WORKDIR /app/dPaspRunner
RUN docker build -t dpasp-runner .

# Run
WORKDIR /app
ENTRYPOINT [ "run.sh" ]