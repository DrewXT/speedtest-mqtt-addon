#!/usr/bin/env python3
"""
Speedtest MQTT Add-on
Runs Ookla Speedtest CLI and publishes results to MQTT.
Supports Home Assistant MQTT Discovery, run-on-demand via:
  - MQTT button entity  (publish any payload to speedtest/run)
  - HA service call     (hassio.addon_stdin with {"action":"run"})
"""

import json
import logging
import subprocess
import sys
import threading
import time  # still used for interval sleep in main loop

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("speedtest_mqtt")

# ── Load config ────────────────────────────────────────────────────────────────
with open("/data/options.json") as f:
    OPTIONS = json.load(f)

MQTT_HOST         = OPTIONS.get("mqtt_host", "core-mosquitto")
MQTT_PORT         = int(OPTIONS.get("mqtt_port", 1883))
MQTT_USER         = OPTIONS.get("mqtt_username", "")
MQTT_PASS         = OPTIONS.get("mqtt_password", "")
TOPIC_PREFIX      = OPTIONS.get("mqtt_topic_prefix", "speedtest").rstrip("/")
INTERVAL_MINUTES  = int(OPTIONS.get("interval_minutes", 30))
SERVER_ID         = int(OPTIONS.get("speedtest_server_id", 0))
UOM               = OPTIONS.get("unit_of_measurement", "Mbps")
DISCOVERY_PREFIX  = OPTIONS.get("discovery_prefix", "homeassistant").rstrip("/")
DISCOVERY_ENABLED = bool(OPTIONS.get("discovery_enabled", True))

UNIT_DIVISORS = {"Bps": 1, "Kbps": 1_000, "Mbps": 1_000_000}
DIVISOR = UNIT_DIVISORS.get(UOM, 1_000_000)

# ── Run-on-demand event ────────────────────────────────────────────────────────
run_now_event = threading.Event()

# ── Sensor definitions ─────────────────────────────────────────────────────────
SENSORS = [
    {
        "id":           "download_speed",
        "name":         "Download Speed",
        "device_class": "data_rate",
        "unit":         UOM,
        "icon":         "mdi:download-network",
        "value_fn":     lambda r: round(r["download"]["bandwidth"] * 8 / DIVISOR, 2),
        "state_class":  "measurement",
    },
    {
        "id":           "upload_speed",
        "name":         "Upload Speed",
        "device_class": "data_rate",
        "unit":         UOM,
        "icon":         "mdi:upload-network",
        "value_fn":     lambda r: round(r["upload"]["bandwidth"] * 8 / DIVISOR, 2),
        "state_class":  "measurement",
    },
    {
        "id":           "ping",
        "name":         "Ping",
        "device_class": "duration",
        "unit":         "ms",
        "icon":         "mdi:lan-pending",
        "value_fn":     lambda r: round(r["ping"]["latency"], 2),
        "state_class":  "measurement",
    },
    {
        "id":           "jitter",
        "name":         "Jitter",
        "device_class": "duration",
        "unit":         "ms",
        "icon":         "mdi:sine-wave",
        "value_fn":     lambda r: round(r["ping"]["jitter"], 2),
        "state_class":  "measurement",
    },
    {
        "id":           "server_name",
        "name":         "Server Name",
        "device_class": None,
        "unit":         None,
        "icon":         "mdi:server-network",
        "value_fn":     lambda r: r["server"]["name"],
        "state_class":  None,
    },
    {
        "id":           "server_location",
        "name":         "Server Location",
        "device_class": None,
        "unit":         None,
        "icon":         "mdi:map-marker",
        "value_fn":     lambda r: f"{r['server']['location']}, {r['server']['country']}",
        "state_class":  None,
    },
    {
        "id":           "server_id",
        "name":         "Server ID",
        "device_class": None,
        "unit":         None,
        "icon":         "mdi:identifier",
        "value_fn":     lambda r: str(r["server"]["id"]),
        "state_class":  None,
    },
    {
        "id":           "isp",
        "name":         "ISP",
        "device_class": None,
        "unit":         None,
        "icon":         "mdi:web",
        "value_fn":     lambda r: r.get("isp", "Unknown"),
        "state_class":  None,
    },
]

DEVICE_INFO = {
    "identifiers":    ["speedtest_mqtt"],
    "name":           "Speedtest MQTT",
    "model":          "Ookla Speedtest CLI",
    "manufacturer":   "Speedtest by Ookla",
    "sw_version":     "1.5.0",
}


# ── MQTT client ────────────────────────────────────────────────────────────────
def build_client():
    client = mqtt.Client(client_id="speedtest_mqtt", clean_session=True)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.will_set(f"{TOPIC_PREFIX}/status", payload="offline", retain=True)

    # Signal main thread that connection is confirmed and discovery is done
    connected_event = threading.Event()

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            log.info("Connected to MQTT broker at %s:%d", MQTT_HOST, MQTT_PORT)
            c.publish(f"{TOPIC_PREFIX}/status", payload="online", retain=True)
            c.subscribe(f"{TOPIC_PREFIX}/run")
            log.info("Subscribed to %s/run", TOPIC_PREFIX)
            # Publish discovery now that we know the connection is live
            publish_discovery(c)
            connected_event.set()
        else:
            log.error("MQTT connection failed with code %d", rc)

    def on_disconnect(c, userdata, rc):
        log.warning("MQTT disconnected (rc=%d), will reconnect…", rc)

    def on_message(c, userdata, msg):
        log.info("Run-on-demand triggered via MQTT topic %s", msg.topic)
        run_now_event.set()

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client._connected_event = connected_event   # expose so main() can wait on it
    return client


# ── Discovery ──────────────────────────────────────────────────────────────────
def publish_discovery(client):
    if not DISCOVERY_ENABLED:
        return

    for sensor in SENSORS:
        sid = sensor["id"]
        config = {
            "name":               sensor["name"],
            "unique_id":          f"speedtest_mqtt_{sid}",
            "state_topic":        f"{TOPIC_PREFIX}/state",
            "value_template":     f"{{{{ value_json.{sid} }}}}",
            "icon":               sensor["icon"],
            "device":             DEVICE_INFO,
            "availability_topic": f"{TOPIC_PREFIX}/status",
            "payload_available":   "online",
            "payload_not_available": "offline",
        }
        if sensor.get("device_class"):
            config["device_class"] = sensor["device_class"]
        if sensor.get("unit"):
            config["unit_of_measurement"] = sensor["unit"]
        if sensor.get("state_class"):
            config["state_class"] = sensor["state_class"]

        client.publish(
            f"{DISCOVERY_PREFIX}/sensor/speedtest_mqtt_{sid}/config",
            json.dumps(config),
            retain=True,
        )
        log.info("Discovery published → sensor/%s", sid)

    # Status sensor (idle / running / error)
    client.publish(
        f"{DISCOVERY_PREFIX}/sensor/speedtest_mqtt_status/config",
        json.dumps({
            "name":               "Status",
            "unique_id":          "speedtest_mqtt_status",
            "state_topic":        f"{TOPIC_PREFIX}/running",
            "icon":               "mdi:information-outline",
            "device":             DEVICE_INFO,
            "availability_topic": f"{TOPIC_PREFIX}/status",
            "payload_available":   "online",
            "payload_not_available": "offline",
        }),
        retain=True,
    )
    log.info("Discovery published → sensor/status")

    # Button entity
    client.publish(
        f"{DISCOVERY_PREFIX}/button/speedtest_mqtt_run_now/config",
        json.dumps({
            "name":               "Run Now",
            "unique_id":          "speedtest_mqtt_run_now",
            "command_topic":      f"{TOPIC_PREFIX}/run",
            "payload_press":      "run",
            "icon":               "mdi:play-circle-outline",
            "device":             DEVICE_INFO,
            "availability_topic": f"{TOPIC_PREFIX}/status",
            "payload_available":   "online",
            "payload_not_available": "offline",
        }),
        retain=True,
    )
    log.info("Discovery published → button/run_now")


# ── Speedtest runner ───────────────────────────────────────────────────────────
def run_speedtest():
    cmd = ["speedtest", "--format=json", "--accept-license", "--accept-gdpr"]
    if SERVER_ID > 0:
        cmd += [f"--server-id={SERVER_ID}"]
    log.info("Running speedtest… (server_id=%s)", SERVER_ID if SERVER_ID > 0 else "auto")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error("Speedtest error: %s", result.stderr.strip())
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.error("Speedtest timed out after 120 s")
        return None
    except json.JSONDecodeError as e:
        log.error("Failed to parse speedtest output: %s", e)
        return None


def build_state(raw):
    state = {}
    for sensor in SENSORS:
        try:
            state[sensor["id"]] = sensor["value_fn"](raw)
        except (KeyError, TypeError) as e:
            log.warning("Could not extract %s: %s", sensor["id"], e)
            state[sensor["id"]] = None
    state["timestamp"]  = raw.get("timestamp", "")
    state["result_url"] = raw.get("result", {}).get("url", "")
    return state


def do_run(client):
    client.publish(f"{TOPIC_PREFIX}/running", "running", retain=True)
    raw = run_speedtest()
    if raw:
        state = build_state(raw)
        client.publish(f"{TOPIC_PREFIX}/state", json.dumps(state), retain=True)
        client.publish(f"{TOPIC_PREFIX}/raw",   json.dumps(raw),   retain=True)
        client.publish(f"{TOPIC_PREFIX}/running", "idle", retain=True)
        log.info(
            "Published → %s/state  down=%.2f %s  up=%.2f %s  ping=%.1f ms",
            TOPIC_PREFIX,
            state.get("download_speed", 0), UOM,
            state.get("upload_speed", 0),   UOM,
            state.get("ping", 0),
        )
    else:
        client.publish(f"{TOPIC_PREFIX}/running", "error", retain=True)
        log.warning("Speedtest failed, skipping publish.")


# ── stdin listener (HA service: hassio.addon_stdin) ───────────────────────────
def stdin_listener():
    """
    Listens for JSON on stdin.
    HA automation / script example:
      service: hassio.addon_stdin
      data:
        addon: local_speedtest_mqtt
        input: '{"action":"run"}'
    """
    log.info('stdin listener ready — send {"action":"run"} to trigger on-demand run')
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if msg.get("action") == "run":
                log.info("Run-on-demand triggered via stdin (HA service call)")
                run_now_event.set()
            else:
                log.warning("Unknown stdin action: %s", msg)
        except json.JSONDecodeError:
            log.warning("Invalid JSON on stdin: %s", line)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("Speedtest MQTT v1.2.0 starting (interval=%d min, uom=%s)", INTERVAL_MINUTES, UOM)

    threading.Thread(target=stdin_listener, daemon=True).start()

    client = build_client()
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    # Wait until on_connect confirms broker is ready and discovery is published
    log.info("Waiting for MQTT connection…")
    if not client._connected_event.wait(timeout=30):
        log.error("Timed out waiting for MQTT connection after 30 s — check broker settings")

    # Run immediately on startup
    do_run(client)

    interval_seconds = INTERVAL_MINUTES * 60

    while True:
        triggered = run_now_event.wait(timeout=interval_seconds)
        if triggered:
            log.info("On-demand run starting…")
            run_now_event.clear()
        else:
            log.info("Scheduled run starting…")
        do_run(client)
        log.info("Next scheduled run in %d minute(s)…", INTERVAL_MINUTES)


if __name__ == "__main__":
    main()
