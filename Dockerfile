FROM registry.gitlab.com/thelabnyc/python:3.13.1011@sha256:f5779762dfbff36f78b9d9e6a825ce626f2758893d76e7b6c8bfcf4c12a4da5e

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN uv sync

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
