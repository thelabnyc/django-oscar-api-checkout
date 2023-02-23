FROM python:3.11

RUN mkdir /code
WORKDIR /code

RUN apt-get update && \
    apt-get install -y gettext && \
    rm -rf /var/lib/apt/lists/*

ADD . /code/
RUN pip install -e .[development]

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
