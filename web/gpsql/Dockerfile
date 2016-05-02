FROM debian:7

RUN apt-get update && \
    apt-get -y install socat && \
    apt-get clean

USER nobody

CMD socat -dddd TCP-LISTEN:1521,reuseaddr,fork TCP:db:1521