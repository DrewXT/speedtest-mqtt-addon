ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Ookla Speedtest CLI (official)
RUN curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash \
    && apt-get install -y speedtest \
    && rm -rf /var/lib/apt/lists/*

# Install Python MQTT library
RUN pip3 install --no-cache-dir paho-mqtt

# Copy add-on files
COPY rootfs /

RUN chmod +x /usr/bin/speedtest_mqtt.py \
    && chmod +x /etc/services.d/speedtest_mqtt/run \
    && chmod +x /etc/services.d/speedtest_mqtt/finish
