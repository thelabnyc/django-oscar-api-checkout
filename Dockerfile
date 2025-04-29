FROM registry.gitlab.com/thelabnyc/python:py313@sha256:5ddee9abe4264e1872a562c2e57011207bb0c59d4671d94bd256a0eac46f1aba

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN poetry install

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
