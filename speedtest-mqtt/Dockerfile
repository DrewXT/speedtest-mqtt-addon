ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Ookla Speedtest CLI via official apt repo (multi-arch safe)
# Uses the packagecloud apt source directly rather than the shell installer script,
# which avoids curl-to-bash issues in restricted build environments.
RUN install -d /etc/apt/keyrings \
    && curl -fsSL https://packagecloud.io/ookla/speedtest-cli/gpgkey \
       | gpg --dearmor -o /etc/apt/keyrings/ookla.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/ookla.gpg] https://packagecloud.io/ookla/speedtest-cli/debian/ bullseye main" \
       > /etc/apt/sources.list.d/ookla.list \
    && apt-get update \
    && apt-get install -y speedtest \
    && rm -rf /var/lib/apt/lists/*

# Install Python MQTT library
RUN pip3 install --no-cache-dir paho-mqtt

# Copy add-on files
COPY rootfs /

RUN chmod +x /usr/bin/speedtest_mqtt.py \
    && chmod +x /etc/services.d/speedtest_mqtt/run \
    && chmod +x /etc/services.d/speedtest_mqtt/finish
