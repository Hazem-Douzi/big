# Comment voir les résultats de la simulation ?

Plusieurs façons de visualiser les données produites par le simulateur, du plus simple au plus avancé.

## 1. Voir les logs en direct dans le terminal

C'est le mode le plus rapide : aucune configuration, juste lire le terminal.

```bash
python main.py --cycles 2 --acceleration 60
```

Tu verras défiler :
- Les phases du cycle (PHASE 1, 2, 3, 4)
- La progression de la collecte des compteurs (par bucket)
- Les agrégations par distributeur/concentrateur
- Le récap final du cycle (énergie totale, anomalies)

Le mode `--cycles 0` boucle à l'infini.

## 2. Sauvegarder un cycle dans un fichier JSON-lines

Pour analyser les données après coup ou les relire avec un outil de visualisation :

```bash
python main.py --cycles 1 --acceleration 900 --output-file out/cycle.jsonl
```

Le fichier `out/cycle.jsonl` contient une ligne par message Kafka (mock), au format :
```json
{"topic": "tetouan.meters.readings", "key": "TET-MED-MTR-00123", "value": {...}}
```

Tu peux ensuite l'inspecter à la main :
```bash
# Compter les messages par topic
cut -d'"' -f4 out/cycle.jsonl | sort | uniq -c

# Voir les 5 premières mesures
head -5 out/cycle.jsonl | python -m json.tool
```

## 3. Visualiseur console coloré (recommandé)

Outil dédié qui produit un rapport complet avec couleurs ANSI dans le terminal.

```bash
# 1) générer un cycle
python main.py --cycles 1 --acceleration 900 --output-file out/cycle.jsonl

# 2) visualiser
python tools/view_results.py out/cycle.jsonl
```

Affiche :
- Statistiques globales du cycle (énergie totale, anomalies)
- Répartition par type de zone (Residential / Commercial / Industrial)
- Tableau de consommation par quartier (trié par énergie)
- Histogramme ASCII de la consommation
- Top 10 distributeurs les plus chargés
- Top 10 anomalies de tension (sous-tension < 207V ou sur-tension > 253V)

Options :
```bash
python tools/view_results.py out/cycle.jsonl --top 20  # top 20 au lieu de 10
```

## 4. Dashboard HTML interactif (le plus visuel)

Génère un fichier HTML autonome avec carte interactive Leaflet, graphiques et tableaux.

```bash
# 1) générer un cycle
python main.py --cycles 1 --acceleration 900 --output-file out/cycle.jsonl

# 2) générer le dashboard HTML
python tools/build_dashboard.py out/cycle.jsonl --output dashboard.html

# 3) ouvrir dans un navigateur
xdg-open dashboard.html        # Linux
open dashboard.html            # macOS
start dashboard.html           # Windows
```

Le fichier HTML est totalement autonome (aucune dépendance Python pour le servir, juste un navigateur). Il contient :
- 5 cartes statistiques (compteurs, distributeurs, concentrateurs, énergie, anomalies)
- **Carte interactive Leaflet** centrée sur Tétouan avec un cercle par quartier dont la taille et la couleur dépendent de la consommation
- **Graphique en barres** de la consommation par quartier (couleur selon le type de zone)
- Tableau détaillé des 18 quartiers
- Top 20 anomalies de tension

> Note : le fichier HTML charge Leaflet et les tuiles OpenStreetMap depuis Internet (CDN). Il faut donc une connexion lors de l'ouverture du fichier dans le navigateur. Toutes les données sont en revanche embarquées dans le HTML lui-même.

## 5. Voir les données dans pandas (analyse interactive)

```python
import json
import pandas as pd

# charger toutes les mesures
rows = []
with open("out/cycle.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        if msg["topic"] == "tetouan.meters.readings":
            rows.append(msg["value"])

df = pd.DataFrame(rows)

# stats par quartier
print(df.groupby("district")["energy_consumption"].agg(["sum", "mean", "count"]))

# stats par type de zone
print(df.groupby("zone_type")["voltage"].describe())

# anomalies de tension
print(df[(df.voltage < 207) | (df.voltage > 253)])
```

## 6. Brancher Kafka + Spark + Cassandra (production)

Quand le pipeline complet sera prêt :

```bash
# démarrer Kafka, Cassandra, etc. (docker-compose à venir)
docker compose up -d

# lancer le simulateur en mode Kafka
python main.py --kafka --cycles 0

# les données seront consommées par Spark Streaming et stockées dans Cassandra
# le dashboard final (Streamlit) lira Cassandra en live
```

## Récapitulatif des cas d'usage

| Tu veux... | Utilise |
|---|---|
| Voir le cycle se dérouler en direct | `python main.py --cycles 0` |
| Faire une vérif rapide de ce qui est produit | `head -5 out/cycle.jsonl \| python -m json.tool` |
| Un rapport détaillé en console | `python tools/view_results.py out/cycle.jsonl` |
| Un dashboard graphique partageable | `python tools/build_dashboard.py out/cycle.jsonl` |
| Une analyse interactive | pandas + Jupyter |
| Une démo live au jury | dashboard HTML + simulateur en boucle |

## Démo recommandée pour la soutenance

Dans 3 terminaux séparés :

```bash
# terminal 1 : simulation en boucle
python main.py --cycles 0 --acceleration 60

# terminal 2 : régénérer le dashboard toutes les 30 sec
while true; do
  python tools/build_dashboard.py out/last_cycle.jsonl -o dashboard.html
  sleep 30
done

# terminal 3 : ouvrir le dashboard dans un navigateur
xdg-open dashboard.html
```
