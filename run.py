#!/usr/bin/env python3
"""
Seplos BMS Monitor — Home Assistant Add-on
──────────────────────────────────────────
Legge i dati dal BMS Seplos V2/V3 via:
  • Waveshare Serial→WiFi  (TCP trasparente)
  • Adattatore USB-RS485 diretto

Pubblica su MQTT con auto-discovery Home Assistant.
La configurazione viene letta da /data/options.json (HA Add-on standard).
"""

import json
import logging
import os
import socket
import sys
import time

try:
    import serial
except ImportError:
    serial = None

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERRORE: paho-mqtt non installato")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Legge la configurazione dal file JSON di HA (/data/options.json)
# ──────────────────────────────────────────────────────────────────────────────
OPTIONS_FILE = "/data/options.json"

def load_options() -> dict:
    try:
        with open(OPTIONS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback per test fuori da HA
        return {}

OPT = load_options()

def opt(key: str, default=None):
    return OPT.get(key, default)

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = opt("log_level", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("seplos_bms")


# ══════════════════════════════════════════════════════════════════════════════
#  TRANSPORT
# ══════════════════════════════════════════════════════════════════════════════

class TcpTransport:
    """Connessione TCP al Waveshare Serial→WiFi in modalità trasparente."""

    def __init__(self, host: str, port: int, timeout: float):
        self.host    = host
        self.port    = port
        self.timeout = timeout
        self.sock    = None
        self._connect()

    def _connect(self):
        log.info("Connessione TCP → %s:%d …", self.host, self.port)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.connect((self.host, self.port))
            self.sock = s
            log.info("Connesso al Waveshare %s:%d", self.host, self.port)
        except OSError as e:
            log.error("Connessione fallita: %s", e)
            self.sock = None

    def send(self, data: bytes):
        if not self.sock:
            self._connect()
        if self.sock:
            # Svuota buffer residuo
            self.sock.setblocking(False)
            try:
                while self.sock.recv(256):
                    pass
            except (BlockingIOError, OSError):
                pass
            finally:
                self.sock.setblocking(True)
                self.sock.settimeout(self.timeout)
            self.sock.sendall(data)

    def recv(self, timeout: float) -> str | None:
        if not self.sock:
            return None
        self.sock.settimeout(timeout)
        buf = b""
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                try:
                    chunk = self.sock.recv(256)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk
                if b"\r" in buf:
                    break
        except OSError as e:
            log.warning("Errore ricezione TCP: %s", e)
            self.close()
        return buf.decode("ascii", errors="ignore").strip() if buf else None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def reopen(self):
        self.close()
        time.sleep(3)
        self._connect()


class SerialTransport:
    """Connessione via porta seriale USB→RS485."""

    def __init__(self, port: str, baud: int):
        if serial is None:
            raise RuntimeError("pyserial non disponibile")
        self.ser = serial.Serial(
            port=port, baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
        )
        log.info("Porta seriale: %s @ %d baud", port, baud)

    def send(self, data: bytes):
        self.ser.reset_input_buffer()
        self.ser.write(data)

    def recv(self, timeout: float) -> str | None:
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if b"\r" in buf:
                    break
            else:
                time.sleep(0.01)
        return buf.decode("ascii", errors="ignore").strip() if buf else None

    def close(self):
        self.ser.close()

    def reopen(self):
        try:
            self.ser.close()
        except Exception:
            pass
        time.sleep(2)
        self.ser.open()


# ══════════════════════════════════════════════════════════════════════════════
#  PROTOCOLLO SEPLOS MODBUS-ASCII
# ══════════════════════════════════════════════════════════════════════════════

def _lchksum(lenid: int) -> int:
    lenid &= 0x0FFF
    lsum  = ((lenid >> 8) & 0xF) + ((lenid >> 4) & 0xF) + (lenid & 0xF)
    return ((~lsum + 1) & 0xF) << 12 | lenid

def _chksum(data: str) -> int:
    return (~sum(ord(c) for c in data) + 1) & 0xFFFF

def build_request(address: int, cid2: int, info: str = "") -> bytes:
    body  = f"20{address:02X}46{cid2:02X}{_lchksum(len(info)):04X}{info}"
    frame = f"~{body}{_chksum(body):04X}\r"
    log.debug("TX → %s", frame.strip())
    return frame.encode("ascii")

def _verify(raw: str) -> bool:
    if not raw.startswith("~") or len(raw) < 13:
        return False
    body = raw[1:-4]
    try:
        ok = int(raw[-4:], 16) == _chksum(body)
    except ValueError:
        return False
    if not ok:
        log.warning("Checksum errato")
        return False
    if raw[7:9] != "00":
        log.warning("RTN error: %s", raw[7:9])
        return False
    return True

def _hpairs(data: str) -> list[int]:
    return [int(data[i:i+2], 16) for i in range(0, len(data), 2)]

def decode_telemetry(raw: str) -> dict | None:
    if not _verify(raw):
        return None
    info = raw[13:-4]
    if not info:
        return None
    b   = _hpairs(info)
    idx = 1  # salta DATAFLAG

    try:
        num_cells = b[idx]; idx += 1
        cells = []
        for _ in range(num_cells):
            cells.append(round(((b[idx] << 8) | b[idx+1]) / 1000.0, 3))
            idx += 2

        num_temps = b[idx]; idx += 1
        temps = []
        for _ in range(num_temps):
            temps.append(round(((b[idx] << 8) | b[idx+1] - 2731) / 10.0, 1))
            idx += 2

        raw_i = (b[idx] << 8) | b[idx+1]
        current = round((raw_i - 0x10000 if raw_i > 0x7FFF else raw_i) * 0.01, 2)
        idx += 2

        pack_v    = round(((b[idx] << 8) | b[idx+1]) * 0.01, 2); idx += 2
        rem_cap   = round(((b[idx] << 8) | b[idx+1]) * 0.01, 2); idx += 2
        full_cap  = round(((b[idx] << 8) | b[idx+1]) * 0.01, 2); idx += 2
        soc       = round(((b[idx] << 8) | b[idx+1]) * 0.1,  1); idx += 2
        soh       = round(((b[idx] << 8) | b[idx+1]) * 0.1,  1); idx += 2
        cycles    = (b[idx] << 8) | b[idx+1];                     idx += 2

        flags = "".join(f"{x:02X}" for x in b[idx:idx+4]) if idx + 3 < len(b) else ""

        cmin = min(cells); cmax = max(cells)
        return {
            "pack_voltage":       pack_v,
            "current":            current,
            "power_w":            round(pack_v * current, 1),
            "soc":                soc,
            "soh":                soh,
            "remaining_capacity": rem_cap,
            "full_capacity":      full_cap,
            "cycles":             cycles,
            "cell_voltages":      cells,
            "cell_min_v":         cmin,
            "cell_max_v":         cmax,
            "cell_diff_mv":       round((cmax - cmin) * 1000, 1),
            "temperatures":       temps,
            "temp_avg_c":         round(sum(temps) / len(temps), 1) if temps else None,
            "num_cells":          num_cells,
            "status_flags":       flags,
        }
    except (IndexError, ValueError) as e:
        log.error("Decodifica fallita: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  HOME ASSISTANT  —  ENTITÀ E AUTO-DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

# Definizione completa delle entità esposte in HA
# (chiave_json, nome, unità, device_class, icon, state_class, categoria)
ENTITIES = [
    # ── Energia ──────────────────────────────────────────────────────────────
    ("soc",               "Stato di Carica",       "%",   "battery",     "mdi:battery",              "measurement",       None),
    ("soh",               "Stato di Salute",        "%",   None,          "mdi:heart-pulse",          "measurement",       "diagnostic"),
    ("pack_voltage",      "Tensione Pack",          "V",   "voltage",     "mdi:flash",                "measurement",       None),
    ("current",           "Corrente",               "A",   "current",     "mdi:current-dc",           "measurement",       None),
    ("power_w",           "Potenza",                "W",   "power",       "mdi:solar-power",          "measurement",       None),
    ("remaining_capacity","Capacità Residua",        "Ah",  None,          "mdi:battery-charging",     "measurement",       None),
    ("full_capacity",     "Capacità Totale",         "Ah",  None,          "mdi:battery-check",        None,                "diagnostic"),
    # ── Salute batteria ───────────────────────────────────────────────────────
    ("cycles",            "Cicli di Carica",        None,  None,          "mdi:counter",              "total_increasing",  "diagnostic"),
    ("cell_min_v",        "Cella Minima",           "V",   "voltage",     "mdi:battery-low",          "measurement",       "diagnostic"),
    ("cell_max_v",        "Cella Massima",          "V",   "voltage",     "mdi:battery-high",         "measurement",       "diagnostic"),
    ("cell_diff_mv",      "Delta Celle",            "mV",  None,          "mdi:delta",                "measurement",       "diagnostic"),
    # ── Temperatura ──────────────────────────────────────────────────────────
    ("temp_avg_c",        "Temperatura Media",      "°C",  "temperature", "mdi:thermometer",          "measurement",       None),
]


def publish_discovery(client: mqtt.Client, device_id: str, prefix: str, disc_prefix: str):
    state_topic = f"{prefix}/{device_id}/state"
    avail_topic = f"{prefix}/{device_id}/availability"

    device_info = {
        "identifiers":  [device_id],
        "name":         "Seplos BMS",
        "manufacturer": "Seplos Technology",
        "model":        "EMU10XX / EMU11XX",
        "sw_version":   "2.0",
    }
    if opt("connection_mode") == "waveshare":
        device_info["configuration_url"] = f"http://{opt('waveshare_host')}"

    def _pub(key, payload_dict):
        topic = f"{disc_prefix}/sensor/{device_id}/{key}/config"
        client.publish(topic, json.dumps(payload_dict), retain=True)

    # Sensori principali
    for key, name, unit, dev_class, icon, state_class, category in ENTITIES:
        p = {
            "name":             name,
            "unique_id":        f"{device_id}_{key}",
            "state_topic":      state_topic,
            "value_template":   f"{{{{ value_json.{key} }}}}",
            "availability_topic": avail_topic,
            "device":           device_info,
            "icon":             icon,
        }
        if unit:        p["unit_of_measurement"] = unit
        if dev_class:   p["device_class"]        = dev_class
        if state_class: p["state_class"]         = state_class
        if category:    p["entity_category"]     = category
        _pub(key, p)

    # Celle individuali (fino a 16)
    for i in range(16):
        key = f"cell_{i+1:02d}_v"
        p = {
            "name":                f"Cella {i+1:02d}",
            "unique_id":           f"{device_id}_{key}",
            "state_topic":         state_topic,
            "value_template":      (
                f"{{{{ value_json.cell_voltages[{i}]"
                f" if value_json.cell_voltages | length > {i}"
                f" else 'unavailable' }}}}"
            ),
            "availability_topic":  avail_topic,
            "unit_of_measurement": "V",
            "device_class":        "voltage",
            "state_class":         "measurement",
            "entity_category":     "diagnostic",
            "device":              device_info,
            "icon":                "mdi:battery-outline",
        }
        _pub(key, p)

    # Temperature individuali (fino a 4)
    for i in range(4):
        key = f"temp_{i+1:02d}_c"
        p = {
            "name":                f"Temperatura {i+1}",
            "unique_id":           f"{device_id}_{key}",
            "state_topic":         state_topic,
            "value_template":      (
                f"{{{{ value_json.temperatures[{i}]"
                f" if value_json.temperatures | length > {i}"
                f" else 'unavailable' }}}}"
            ),
            "availability_topic":  avail_topic,
            "unit_of_measurement": "°C",
            "device_class":        "temperature",
            "state_class":         "measurement",
            "entity_category":     "diagnostic",
            "device":              device_info,
            "icon":                "mdi:thermometer",
        }
        _pub(key, p)

    log.info("Auto-discovery pubblicato: %d entità", len(ENTITIES) + 20)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    addr         = opt("bms_address",        0)
    poll         = opt("poll_interval",      10)
    prefix       = opt("mqtt_prefix",        "seplos_bms")
    disc_prefix  = opt("ha_discovery_prefix","homeassistant")
    device_id    = f"seplos_{addr:02x}"
    avail_topic  = f"{prefix}/{device_id}/availability"
    state_topic  = f"{prefix}/{device_id}/state"

    log.info("╔══ Seplos BMS Add-on ══╗")
    log.info("║ Modalità  : %s", opt("connection_mode", "waveshare"))
    log.info("║ BMS addr  : 0x%02X", addr)
    log.info("║ Polling   : %ds", poll)
    log.info("╚══════════════════════╝")

    # ── Transport ──────────────────────────────────────────────────────────
    mode = opt("connection_mode", "waveshare")
    if mode == "waveshare":
        transport = TcpTransport(
            host    = opt("waveshare_host", "192.168.1.100"),
            port    = opt("waveshare_port", 4196),
            timeout = opt("tcp_timeout",    5),
        )
    else:
        transport = SerialTransport(
            port = opt("serial_port", "/dev/ttyUSB0"),
            baud = opt("baud_rate",   9600),
        )

    # ── MQTT ───────────────────────────────────────────────────────────────
    mqttc = mqtt.Client(client_id=f"seplos_addon_{addr:02x}")
    user  = opt("mqtt_user", "")
    if user:
        mqttc.username_pw_set(user, opt("mqtt_password", ""))

    # Messaggio di offline in caso di disconnessione inattesa
    mqttc.will_set(avail_topic, "offline", retain=True)

    def on_connect(c, *_):
        log.info("MQTT connesso")
        c.publish(avail_topic, "online", retain=True)
        if opt("ha_discovery", True):
            publish_discovery(c, device_id, prefix, disc_prefix)

    mqttc.on_connect = on_connect
    mqttc.connect(opt("mqtt_host", "core-mosquitto"), opt("mqtt_port", 1883), keepalive=60)
    mqttc.loop_start()
    time.sleep(1)

    # ── Loop principale ────────────────────────────────────────────────────
    errors = 0
    try:
        while True:
            t0    = time.time()
            frame = build_request(addr, 0x42, f"01{addr:02X}")
            transport.send(frame)
            time.sleep(0.15)
            raw   = transport.recv(timeout=opt("tcp_timeout", 5))
            data  = decode_telemetry(raw) if raw else None

            if data:
                errors = 0
                mqttc.publish(state_topic, json.dumps(data), retain=False)
                log.info(
                    "SOC=%5.1f%%  V=%5.2fV  I=%+6.2fA  P=%+6.0fW"
                    "  T=%4.1f°C  ΔV=%5.1fmV  Cicli=%d",
                    data["soc"], data["pack_voltage"], data["current"],
                    data["power_w"], data["temp_avg_c"] or 0,
                    data["cell_diff_mv"], data["cycles"],
                )
            else:
                errors += 1
                log.warning("Lettura fallita (%d consecutivi)", errors)
                if errors >= 5:
                    log.warning("Riconnessione transport …")
                    transport.reopen()
                    errors = 0

            elapsed = time.time() - t0
            time.sleep(max(0, poll - elapsed))

    except KeyboardInterrupt:
        log.info("Arresto add-on.")
    finally:
        mqttc.publish(avail_topic, "offline", retain=True)
        transport.close()
        mqttc.loop_stop()
        mqttc.disconnect()


if __name__ == "__main__":
    main()
