FROM python:2.7
ADD . /robo
WORKDIR /robo
RUN apt-get update
RUN apt-get install -y python-numpy
RUN apt-get install -y python-MySQLdb
RUN pip install -r requirements.txt
