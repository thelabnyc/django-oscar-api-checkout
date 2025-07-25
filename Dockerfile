FROM registry.gitlab.com/thelabnyc/python:3.13.866@sha256:b7981a0eda8ffe90f3c33716ed737ab8cfe6b4f1ed6976226ca2685e2292a3ec

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN uv sync

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
