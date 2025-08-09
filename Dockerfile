FROM registry.gitlab.com/thelabnyc/python:3.13.892@sha256:7f2a493f9c96c6a8999c9f3f20499d5c2e3a191d6c506fb8f01ab50ec2197641

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN uv sync

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
