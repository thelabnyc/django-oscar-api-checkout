FROM registry.gitlab.com/thelabnyc/python:3.15@sha256:e08deefd35ca47786a7055c81059aafee819f6a60f01530dec2bf1a439865b94

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN uv sync

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
