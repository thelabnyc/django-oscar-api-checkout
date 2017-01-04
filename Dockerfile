FROM python:3.5
ENV PYTHONUNBUFFERED 0

RUN mkdir /code
WORKDIR /code
ENV PYTHONPATH /code

ADD requirements.txt /code/
RUN pip install versiontag==1.1.1
RUN pip install -r requirements.txt

ADD . /code/
