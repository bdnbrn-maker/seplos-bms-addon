# Seplos BMS — Integrazione HACS per Home Assistant

Integrazione nativa per il BMS Seplos V2/V3 via **Waveshare Serial→WiFi** (TCP) o adattatore **USB-RS485**.

## Installazione tramite HACS

1. Apri HACS → **Integrazioni** → ⋮ → **Custom repositories**
2. Aggiungi l'URL di questo repository con categoria **Integration**
3. Cerca "Seplos BMS" → **Installa**
4. Riavvia Home Assistant

## Configurazione

1. **Impostazioni → Dispositivi e Servizi → Aggiungi integrazione**
2. Cerca **"Seplos BMS"**
3. Scegli la modalità di connessione:

### Waveshare Serial→WiFi
| Campo | Valore |
|---|---|
| IP Waveshare | es. `192.168.1.100` (imposta IP statico!) |
| Porta TCP | `4196` (default Waveshare) |
| Indirizzo BMS | `0` per il primo pack |
| Timeout | `5` secondi |

**Configurazione Waveshare** (pagina web http://IP-waveshare):
- Work Mode: **TCP Server**
- Transfer Protocol: **None** (trasparente)
- Local Port: `4196`
- Baud Rate: `9600`, 8N1, no parity

### USB-RS485 diretto
| Campo | Valore |
|---|---|
| Porta seriale | `/dev/ttyUSB0` |
| Baud rate | `9600` |
| Indirizzo BMS | `0` |

## Sensori creati

### Principali
| Entità | Unità | Descrizione |
|---|---|---|
| `sensor.seplos_bms_stato_di_carica` | % | SOC |
| `sensor.seplos_bms_stato_di_salute` | % | SOH |
| `sensor.seplos_bms_tensione_pack` | V | Tensione totale pack |
| `sensor.seplos_bms_corrente` | A | + carica / − scarica |
| `sensor.seplos_bms_potenza` | W | Potenza istantanea |
| `sensor.seplos_bms_capacita_residua` | Ah | Energia disponibile |
| `sensor.seplos_bms_capacita_totale` | Ah | Capacità nominale attuale |
| `sensor.seplos_bms_cicli_di_carica` | — | Contatore cicli |
| `sensor.seplos_bms_cella_minima` | V | Cella con tensione minore |
| `sensor.seplos_bms_cella_massima` | V | Cella con tensione maggiore |
| `sensor.seplos_bms_delta_celle` | mV | Sbilancio celle |
| `sensor.seplos_bms_temperatura_media` | °C | Media sensori temperatura |

### Diagnostica (per ogni cella e sensore temperatura)
- `sensor.seplos_bms_cella_01_v` … `cella_16_v`
- `sensor.seplos_bms_temperatura_1_c` … `temperatura_4_c`

## Struttura repository (per HACS)

```
seplos-bms-hacs/
├── hacs.json
└── custom_components/
    └── seplos_bms/
        ├── __init__.py
        ├── manifest.json
        ├── const.py
        ├── config_flow.py
        ├── sensor.py
        ├── seplos_client.py
        ├── strings.json
        └── translations/
            ├── it.json
            └── en.json
```
