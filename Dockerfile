FROM registry.gitlab.com/thelabnyc/python:3.13.1003@sha256:ec7eb3fc2a161a97242a50a1751795f41f8ae8caed165bd5f8b535100b5952cc

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN uv sync

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
