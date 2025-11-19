FROM registry.gitlab.com/thelabnyc/python:3.13.1117@sha256:151affc6dd6abdfa22800baf2661e80f01e0f2a0573b9243e1c215c0c06cae1a

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN uv sync

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
