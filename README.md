# Seplos BMS Monitor — Home Assistant Add-on

Monitora il tuo BMS Seplos direttamente da Home Assistant via Waveshare Serial→WiFi (TCP) o adattatore USB-RS485.

## Struttura repository

```
seplos-bms-addon/
├── repository.yaml
└── seplos_bms_addon/
    ├── config.yaml      ← manifest add-on
    ├── Dockerfile
    └── run.py           ← script principale
```

## Installazione

### 1. Pubblica il repository su GitHub

1. Crea un repository **pubblico** su GitHub (es. `seplos-bms-addon`)
2. Carica tutti i file mantenendo la struttura delle cartelle
3. Copia l'URL del repository (es. `https://github.com/tuonome/seplos-bms-addon`)

### 2. Aggiungi il repository in Home Assistant

1. Apri HA → **Impostazioni → Add-on → Store**
2. Clicca i tre puntini in alto a destra → **Repositories**
3. Incolla l'URL del tuo repository GitHub → **Aggiungi**
4. L'add-on "Seplos BMS Monitor" apparirà nello store

### 3. Installa e configura

1. Clicca su **Seplos BMS Monitor** → **Installa**
2. Vai alla scheda **Configurazione** e imposta:

```yaml
connection_mode: waveshare        # oppure "serial"

# --- Waveshare ---
waveshare_host: "192.168.1.100"   # IP del tuo Waveshare (metti IP statico!)
waveshare_port: 4196
tcp_timeout: 5

# --- Solo se usi USB-RS485 ---
# serial_port: "/dev/ttyUSB0"
# baud_rate: 9600

# --- BMS ---
bms_address: 0                    # 0 = primo pack

# --- MQTT (broker interno HA) ---
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_user: ""
mqtt_password: ""

# --- Polling ---
poll_interval: 10
ha_discovery: true
log_level: info
```

3. Clicca **Salva** poi **Avvia**

### 4. Verifica sensori in Home Assistant

Dopo l'avvio i sensori appaiono automaticamente in:
**Impostazioni → Dispositivi e Servizi → MQTT → Dispositivi → Seplos BMS**

---

## Sensori disponibili

| Nome                | Unità | Note                              |
|---------------------|-------|-----------------------------------|
| Stato di Carica     | %     | SOC                               |
| Stato di Salute     | %     | SOH                               |
| Tensione Pack       | V     |                                   |
| Corrente            | A     | + carica  /  − scarica            |
| Potenza             | W     | + carica  /  − scarica            |
| Capacità Residua    | Ah    |                                   |
| Capacità Totale     | Ah    |                                   |
| Cicli di Carica     | —     |                                   |
| Cella Minima/Massima| V     |                                   |
| Delta Celle         | mV    | Sbilancio celle                   |
| Temperatura Media   | °C    |                                   |
| Cella 01…16         | V     | Tensione singola cella            |
| Temperatura 1…4     | °C    | Singolo sensore                   |

---

## Configurazione Waveshare

Nella pagina web del Waveshare (http://IP-waveshare):

| Parametro         | Valore              |
|-------------------|---------------------|
| Work Mode         | **TCP Server**      |
| Transfer Protocol | **None** (trasparente) |
| Local Port        | 4196                |
| Baud Rate         | 9600                |
| Data Bit          | 8                   |
| Stop Bit          | 1                   |
| Parity            | None                |

---

## Multi-pack

Per più pack in parallelo, ogni pack ha un indirizzo diverso (0, 1, 2…).
Attualmente l'add-on interroga un solo pack per volta.
Imposta `bms_address` con l'indirizzo del pack master.

---

## Log

Vai alla scheda **Log** dell'add-on per vedere lo stato in tempo reale:

```
2026-06-05 10:23:14 [INFO] SOC= 78.5%  V=51.84V  I= -12.50A  P= -648W  T=25.3°C  ΔV=  3.0mV  Cicli=42
```
