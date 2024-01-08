# syntax=docker/dockerfile:1.4
# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

# This is a dev Dockerfile -- the production version would use a separate build stage and not include npm or vite.
FROM python:3.10-slim-buster
ENV PYTHONPYCACHEPREFIX=/tmp/pycache

RUN apt-get update -y && apt-get install -y curl gpg sqlite3 git

# Install npm by first installing an up-to-date node.js.
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource.gpg.key | gpg --dearmor | tee "/usr/share/keyrings/nodesource.gpg" >/dev/null
RUN echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x bullseye main" | tee /etc/apt/sources.list.d/nodesource.list
RUN apt-get update -y && apt-get install -y nodejs

RUN npm install --location=global npm@latest

RUN mkdir -p /rime

WORKDIR /rime
EXPOSE 3000 5001
ENV PYTHONUNBUFFERED=1

CMD ["/bin/bash", "/rime/run_dev.sh", "--host"]
