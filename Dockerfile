FROM debian:buster

RUN apt-get update && \
    apt-get install -y python3 python3-paho-mqtt python3-yaml && \
    rm -rf /var/lib/apt/lists/*

COPY vi2mqtt.py /usr/bin/vi2mqtt
COPY vi2mqtt.conf /usr/lib/vi2mqtt/vi2mqtt.conf

ENTRYPOINT ["/usr/bin/vi2mqtt"]
