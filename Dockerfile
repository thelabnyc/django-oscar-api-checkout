FROM python:3.6

RUN mkdir /code
WORKDIR /code

ADD . /code/
RUN pip install -e .[development]

RUN mkdir /tox
ENV TOX_WORK_DIR='/tox'
