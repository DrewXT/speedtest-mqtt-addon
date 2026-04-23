# Speedtest MQTT — Add-on Documentation

Runs the **official Ookla Speedtest CLI** on a configurable interval and publishes results to an MQTT broker. Supports **Home Assistant MQTT Discovery** so sensors appear automatically in HA.

---

## Installation

1. Add this repository to Home Assistant:  
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Install **Speedtest MQTT**.
3. Configure the add-on (see below).
4. Start the add-on.

---

## Configuration

| Option | Type | Default | Description |
|---|---|---|---|
| `mqtt_host` | string | `core-mosquitto` | Hostname or IP of your MQTT broker |
| `mqtt_port` | int | `1883` | MQTT broker port |
| `mqtt_username` | string | _(empty)_ | MQTT username (leave blank if none) |
| `mqtt_password` | string | _(empty)_ | MQTT password (leave blank if none) |
| `mqtt_topic_prefix` | string | `speedtest` | Root topic for all published data |
| `interval_minutes` | int | `30` | Minutes between each speedtest run |
| `speedtest_server_id` | int | `0` | Ookla server ID to use. Set to `0` for auto-select |
| `unit_of_measurement` | enum | `Mbps` | Speed unit: `Mbps`, `Kbps`, or `Bps` |
| `discovery_prefix` | string | `homeassistant` | HA MQTT discovery prefix (change only if customised) |
| `discovery_enabled` | bool | `true` | Enable/disable MQTT discovery config publishing |

### Finding a Speedtest server ID

Run the following in your terminal or SSH add-on to list nearby servers:

```bash
speedtest --servers
```

Copy the numeric **ID** of your preferred server and paste it into `speedtest_server_id`.

---

## MQTT Topics

| Topic | Content | Retained |
|---|---|---|
| `speedtest/state` | Flat JSON with all sensor values | ✅ |
| `speedtest/raw` | Full unmodified Speedtest CLI JSON output | ✅ |
| `speedtest/status` | `online` / `offline` (availability) | ✅ |

### Example `speedtest/state` payload

```json
{
  "download":        95.42,
  "upload":          45.18,
  "ping":            12.5,
  "jitter":          1.3,
  "server_name":     "My ISP Server",
  "server_location": "Amsterdam, NL",
  "server_id":       "1234",
  "isp":             "Acme Broadband",
  "timestamp":       "2025-04-20T10:00:00Z",
  "result_url":      "https://www.speedtest.net/result/c/…"
}
```

---

## Sensors created (via MQTT Discovery)

| Sensor | Unit | Device Class |
|---|---|---|
| Download Speed | Mbps / Kbps / Bps | `data_rate` |
| Upload Speed | Mbps / Kbps / Bps | `data_rate` |
| Ping | ms | `duration` |
| Jitter | ms | `duration` |
| Server Name | — | — |
| Server Location | — | — |
| Server ID | — | — |
| ISP | — | — |

---

## Notes

- On first start the add-on accepts the Ookla license automatically (`--accept-license --accept-gdpr`). By installing this add-on you agree to the [Ookla EULA](https://www.speedtest.net/about/eula) and [Privacy Policy](https://www.speedtest.net/about/privacy).
- The add-on uses `retain=true` on all topics so HA always shows the last known value after a restart.

---

## Run on Demand

There are two ways to trigger an immediate speedtest outside the normal schedule:

### 1. MQTT Button (via MQTT Discovery)
A `button` entity called **Run Now** is auto-created in HA. Press it from the UI or use it in an automation:
```yaml
service: button.press
target:
  entity_id: button.speedtest_mqtt_run_now
```
Under the hood this publishes `run` to `speedtest/run`. You can also trigger it manually with any MQTT client by publishing any payload to that topic.

### 2. HA Service Call (stdin)
Use the `hassio.addon_stdin` service to send a command directly to the add-on:
```yaml
service: hassio.addon_stdin
data:
  addon: local_speedtest_mqtt
  input: '{"action":"run"}'
```
This works from automations, scripts, and the Developer Tools → Services panel.

### Status sensor
A `sensor.speedtest_mqtt_status` entity reflects the current state:
| Value | Meaning |
|---|---|
| `idle` | Waiting for next scheduled run |
| `running` | Speedtest in progress |
| `error` | Last run failed |

---

## Lovelace Card

The included `lovelace-card.yaml` provides a full dashboard card with:
- Live Download / Upload speed time-series graph (24 h)
- Ping & Jitter time-series graph (24 h)
- Latest result summary (big numbers)
- Server info & ISP panel
- Run Now button with dynamic status subtitle

### Requirements
Install these two HACS frontend cards first:
- [apexcharts-card](https://github.com/RomRider/apexcharts-card)
- [Mushroom](https://github.com/piitaya/lovelace-mushroom)

### Adding the card
1. Open your dashboard → **Edit** → **Add Card** → **Manual**
2. Paste the contents of `lovelace-card.yaml`
3. Save
