# Simulateur Big Data — Smart Grid Tétouan

Simulateur Python compatible **Apache Kafka** qui produit en streaming les données d'un réseau intelligent de distribution électrique pour la ville de Tétouan (Maroc).

## Architecture

```
                CENTRE DE TRAITEMENT
                        ▲
                        │ tetouan.center.ingest
                        │
              ┌─────────┴─────────┐
              │  18 Concentrateurs │  (1 par quartier)
              └─────────▲─────────┘
                        │ tetouan.concentrators.aggregated
                        │
              ┌─────────┴─────────┐
              │  681 Distributeurs │  (postes MT/BT)
              └─────────▲─────────┘
                        │ tetouan.distributors.aggregated
                        │
              ┌─────────┴─────────┐
              │ 100 485 Compteurs  │  (smart meters)
              └───────────────────┘
                        │ tetouan.meters.readings
```

## Cycle de simulation (15 + 1 + 1 + 13 = 30 min)

| Phase | Durée | Action | Topic Kafka |
|---|---|---|---|
| 1 | 00:00 → 00:15 | Compteurs envoient progressivement (étalement par hash MD5) | `tetouan.meters.readings` |
| 2 | 00:15 → 00:16 | Distributeurs agrègent et publient | `tetouan.distributors.aggregated` |
| 3 | 00:16 → 00:17 | Concentrateurs agrègent et publient | `tetouan.concentrators.aggregated` |
| 4 | 00:17 → 00:30 | Idle + récap cycle | `tetouan.center.ingest` |

## Topologie

- **18 quartiers** de Tétouan avec coordonnées GPS réelles et type de zone :
  - 14 résidentiels, 2 commerciaux (Médina, Ensanche), 2 industriels (Saniat Rmel, Zone Industrielle)
- **681 distributeurs** répartis proportionnellement à la population de chaque quartier
- **100 485 smart meters** rattachés à leurs distributeurs avec dispersion GPS

## Profils de consommation (sans température)

| Type de zone | Pic horaire principal | Pic secondaire | Creux |
|---|---|---|---|
| **Residential** | 20h00 (1.55×) | 8h00 (0.90×) | 3h00 (0.30×) |
| **Commercial** | 20h00 (1.50×) | 11h30 (1.20×) | 3h00 (0.30×) |
| **Industrial** | Plateau 8h-17h (1.40×) | — | Nuit (0.20×) |

Modulation week-end : industriel −55%, résidentiel +10%, commercial +5%.

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

### Mode démo accéléré (sans Kafka)

```bash
# 1 cycle accéléré, sortie stdout
python main.py --cycles 1

# 1 cycle accéléré, sortie dans un fichier JSON-lines
python main.py --cycles 1 --output-file out/cycle.jsonl

# Boucle infinie pour alimenter un dashboard
python main.py --cycles 0
```

### Mode réel avec Kafka

```bash
# nécessite un broker Kafka accessible sur localhost:9092
python main.py --kafka --cycles 5

# avec un broker distant
python main.py --kafka --bootstrap kafka.example.com:9092 --cycles 0
```

### Mode temps réel (1 cycle = 30 minutes réelles)

```bash
python main.py --no-demo --cycles 1
```

### Personnaliser l'accélération

```bash
# 1 seconde réelle = 60 minutes simulées (1 cycle ≈ 30 sec réelles)
python main.py --acceleration 60 --cycles 3

# 1 seconde réelle = 900 minutes simulées (1 cycle ≈ 2 sec réelles)
python main.py --acceleration 900 --cycles 10
```

### Options disponibles

| Option | Description | Défaut |
|---|---|---|
| `--cycles N` | Nombre de cycles à exécuter (0 = infini) | 1 |
| `--kafka` | Active la publication vers un broker Kafka réel | off |
| `--bootstrap HOST:PORT` | Adresse du broker Kafka | `localhost:9092` |
| `--output-file PATH` | Fichier JSON-lines pour le mode mock | — |
| `--no-demo` | Désactive l'accélération temporelle | off |
| `--acceleration N` | 1 sec = N min simulées | 60 |
| `--seed N` | Seed aléatoire | 42 |
| `--start-time ISO` | Heure simulée de départ | maintenant |
| `--num-buckets N` | Nb de buckets temporels phase 1 | 15 |
| `--log-level LVL` | DEBUG / INFO / WARNING / ERROR | INFO |

## Format des messages Kafka

### `tetouan.meters.readings` (niveau 1)
```json
{
  "meter_id": "TET-MED-MTR-00123",
  "distributor_id": "TET-MED-DIST-001",
  "concentrator_id": "TET-MED-CONC",
  "district": "Medina",
  "district_code": "MED",
  "zone_type": "Commercial",
  "timestamp": "2026-05-16T14:00:00",
  "energy_consumption": 0.55,
  "voltage": 224.3,
  "current": 9.812,
  "latitude": 35.5710,
  "longitude": -5.3733
}
```

### `tetouan.distributors.aggregated` (niveau 2)
```json
{
  "distributor_id": "TET-MED-DIST-001",
  "concentrator_id": "TET-MED-CONC",
  "district": "Medina",
  "zone_type": "Commercial",
  "timestamp": "2026-05-16T14:00:00",
  "total_meters": 150,
  "total_energy_kwh": 145.7,
  "avg_voltage": 226.8,
  "min_voltage": 219.5,
  "max_voltage": 231.2,
  "avg_current": 9.5,
  "anomalies_count": 0
}
```

### `tetouan.concentrators.aggregated` (niveau 3)
```json
{
  "concentrator_id": "TET-MED-CONC",
  "district": "Medina",
  "zone_type": "Commercial",
  "timestamp": "2026-05-16T14:00:00",
  "total_distributors": 88,
  "total_meters": 13250,
  "total_energy_kwh": 11328.5,
  "avg_voltage": 230.0,
  "anomalies_count": 3
}
```

### `tetouan.center.ingest` (niveau 4 — récap cycle)
```json
{
  "cycle_id": 1,
  "cycle_start": "2026-05-16T14:00:00",
  "cycle_end": "2026-05-16T14:30:00",
  "districts_reported": 18,
  "total_meters": 100485,
  "total_energy_kwh": 43292.58,
  "anomalies_count": 71,
  "districts": [ ... 18 résumés ... ]
}
```

## Volumétrie par cycle

| Topic | Messages |
|---|---|
| `tetouan.meters.readings` | 100 485 |
| `tetouan.distributors.aggregated` | 681 |
| `tetouan.concentrators.aggregated` | 18 |
| `tetouan.center.ingest` | 1 |
| **Total** | **101 185** |

## Structure du projet

```
Projet_Final_BigData/
├── main.py                      # point d'entrée CLI
├── requirements.txt
├── README.md
└── simulator/
    ├── __init__.py
    ├── config.py                # constantes (topologie, cycles, Kafka)
    ├── topology.py              # construction des 18 quartiers / 681 distributeurs / 100485 compteurs
    ├── patterns.py              # profils horaires + génération mesures + agrégations
    ├── kafka_client.py          # producer Kafka réel + mock
    └── simulator.py             # orchestration du cycle 15+1+1+13
```

## Variables d'environnement

| Variable | Description | Défaut |
|---|---|---|
| `KAFKA_ENABLED` | 1 = vrai broker, 0 = mock | 0 |
| `KAFKA_BOOTSTRAP` | Adresse du broker | `localhost:9092` |
| `DEMO_MODE` | 1 = accéléré, 0 = temps réel | 1 |
| `TIME_ACCELERATION` | 1 sec réelle = N min simulées | 60 |
| `MOCK_OUTPUT_FILE` | Fichier JSONL pour le mock | — |
| `LOG_LEVEL` | Niveau de log | INFO |

## Visualisation cartographique

Chaque message contient `latitude` et `longitude`. Pour une carte interactive avec [Folium](https://python-visualization.github.io/folium/) :

```python
import folium, json
m = folium.Map(location=[35.5710, -5.3733], zoom_start=13)
with open("out/cycle.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        if msg["topic"] == "tetouan.concentrators.aggregated":
            v = msg["value"]
            folium.CircleMarker(
                [35.571, -5.373],   # remplacer par lookup quartier
                radius=v["total_energy_kwh"] / 500,
                popup=f"{v['district']} : {v['total_energy_kwh']} kWh",
            ).add_to(m)
m.save("tetouan_heatmap.html")
```
