# Comment voir les résultats de la simulation ?

Plusieurs façons de visualiser le **fenêtrage 15 min** produit par le simulateur, du plus simple au plus avancé.

> ## Qu'est-ce que le fenêtrage 15 min ?
>
> Chaque **cycle** du simulateur correspond à une **fenêtre tumbling de 15 minutes** au sens **Spark Structured Streaming**. Toutes les agrégations (distributeur, concentrateur, recap centre) portent les bornes :
> - `window_start` — début de la fenêtre (ex: `2026-05-16T14:00:00`)
> - `window_end` — fin de la fenêtre (ex: `2026-05-16T14:15:00`)
> - `window_duration_min` — toujours `15`
>
> Le fichier `--history-file` contient une ligne par **(quartier × fenêtre)**, ce qui permet de tracer l'évolution dans le temps et faire les graphes de tendance.

---

## 1. Voir les logs du fenêtrage en direct

```bash
python main.py --cycles 2 --acceleration 60
```

Tu verras pour chaque cycle un message du type :
```
================ CYCLE 1 demarre — fenetre 15 min : [2026-05-16T19:00:00 -> 2026-05-16T19:15:00] ================
[PHASE 2] ... distributeurs agregent fenetre [2026-05-16T19:00:00 -> 2026-05-16T19:15:00]
[PHASE 3] ... concentrateurs agregent fenetre [2026-05-16T19:00:00 -> 2026-05-16T19:15:00]
[PHASE 4] ... recap fenetre [2026-05-16T19:00:00 -> 2026-05-16T19:15:00] publie (energie=86246 kWh, anomalies=71)
```

Mode boucle infinie : `--cycles 0`.

---

## 2. Sauvegarder l'historique des fenêtres

C'est l'option la plus utile — elle alimente le dashboard.

```bash
python main.py --cycles 4 --acceleration 1800 \
    --history-file out/history.jsonl
```

Le fichier `out/history.jsonl` contient :

| Type de ligne | Contenu | Combien par cycle |
|---|---|---|
| `kind=district` | agrégation d'un quartier sur la fenêtre 15 min | 18 |
| `kind=cycle` | recap global de la fenêtre 15 min | 1 |

Exemple de ligne `district` :
```json
{
  "kind": "district",
  "district": "Medina",
  "zone_type": "Commercial",
  "window_start": "2026-05-16T19:00:00",
  "window_end":   "2026-05-16T19:15:00",
  "window_duration_min": 15,
  "total_distributors": 88,
  "total_meters": 13250,
  "total_energy_kwh": 21434.25,
  "avg_voltage": 230.02,
  "min_voltage": 201.52,
  "max_voltage": 252.37,
  "anomalies_count": 7
}
```

Le fichier est **rotatif** : par défaut on garde les 96 dernières fenêtres (= 24h simulées).
Configurable avec `--history-max-windows N` (`0` = illimité).

---

## 3. Sauvegarder tous les messages Kafka (option mock)

Pour analyser les **mesures brutes des compteurs** (100 485 lignes par cycle) :

```bash
python main.py --cycles 1 --acceleration 1800 \
    --output-file out/messages.jsonl
```

Format : une ligne par message Kafka avec `topic`, `key`, `value`. Compatible avec le visualiseur console.

---

## 4. Visualiseur console coloré

```bash
# il consomme un fichier --output-file
python tools/view_results.py out/messages.jsonl
```

Affiche dans le terminal (avec couleurs ANSI) :
- Statistiques globales du cycle
- Répartition par type de zone (Residential / Commercial / Industrial)
- Tableau de consommation par quartier (trié par énergie)
- Histogramme ASCII de la consommation
- Top 10 distributeurs les plus chargés
- Top 10 anomalies de tension

---

## 5. Dashboard HTML avec fenêtrage et tendance temporelle

C'est **LE** dashboard pour la soutenance — il consomme l'historique des fenêtres et affiche :

- Bandeau **fenêtre courante** (window_start → window_end)
- 5 stats globales avec **delta** vs fenêtre précédente
- 2 graphiques **SVG de tendance** : énergie totale + énergie par quartier sur les N dernières fenêtres
- **Timeline** des 12 dernières fenêtres avec variation `±%` cycle après cycle
- **Carte Leaflet** de Tétouan (taille des cercles = énergie de la fenêtre courante)
- Bar chart par quartier
- Tableau détaillé
- **Auto-refresh** optionnel pour visualisation live

```bash
# 1) générer un historique de plusieurs fenêtres
python main.py --cycles 6 --acceleration 1800 --history-file out/history.jsonl

# 2) générer le dashboard avec auto-refresh toutes les 30 sec
python tools/build_dashboard.py out/history.jsonl \
    --output dashboard.html --refresh-seconds 30

# 3) ouvrir dans un navigateur
xdg-open dashboard.html        # Linux
open dashboard.html            # macOS
start dashboard.html           # Windows
```

> Note : le HTML charge Leaflet et les tuiles OpenStreetMap depuis Internet (CDN).
> Toutes les **données** sont en revanche **embarquées** dans le HTML lui-même —
> aucun serveur Python n'est nécessaire pour l'afficher.

### Options du dashboard

| Option | Description | Défaut |
|---|---|---|
| `--output PATH` | Fichier HTML de sortie | `dashboard.html` |
| `--refresh-seconds N` | Auto-refresh toutes les N sec (`0` = statique) | `0` |
| `--trend-n N` | Nombre de fenêtres dans les graphiques de tendance | `10` |

---

## 6. Démo live recommandée pour la soutenance

Trois terminaux, un script à lancer **avant** la présentation :

```bash
# Terminal 1 : simulation en boucle, historique mis à jour à chaque fenêtre
python main.py --cycles 0 --acceleration 60 \
    --history-file out/history.jsonl

# Terminal 2 : régénérer le dashboard à chaque nouvelle fenêtre (toutes les 30 sec)
while true; do
  python tools/build_dashboard.py out/history.jsonl \
      --output dashboard.html --refresh-seconds 30
  sleep 15
done

# Terminal 3 : ouvrir le dashboard
xdg-open dashboard.html
```

Avec `--acceleration 60`, **une nouvelle fenêtre apparaît toutes les 30 secondes** dans le dashboard. Pendant les 15 min de présentation, le jury voit donc défiler **30 fenêtres successives**, ce qui démontre clairement le streaming.

---

## 7. Analyse interactive avec pandas

```python
import json
import pandas as pd

# charger l'historique
rows = []
with open("out/history.jsonl") as f:
    for line in f:
        obj = json.loads(line)
        if obj["kind"] == "district":
            rows.append(obj)

df = pd.DataFrame(rows)
df["window_start"] = pd.to_datetime(df["window_start"])

# évolution énergie totale par fenêtre
df.groupby("window_start")["total_energy_kwh"].sum().plot()

# évolution par quartier (pivot table)
pivot = df.pivot(index="window_start", columns="district", values="total_energy_kwh")
pivot.plot(figsize=(14, 6), title="Énergie par fenêtre 15 min")

# détecter les pics anormaux
df_anom = df[df["anomalies_count"] > 5]
print(df_anom[["window_start", "district", "anomalies_count", "min_voltage"]])
```

---

## 8. Brancher Kafka + Spark + Cassandra (production)

```bash
# démarrer Kafka, Cassandra, etc.
docker compose up -d

# lancer le simulateur en mode Kafka réel
python main.py --kafka --cycles 0

# (à venir) job Spark Structured Streaming qui consomme les topics
# avec un window("event_time", "15 minutes") strictement équivalent
```

---

## Récapitulatif des cas d'usage

| Tu veux... | Commande |
|---|---|
| Voir les phases défiler en direct | `python main.py --cycles 0` |
| Vérifier la structure JSON | `head -2 out/messages.jsonl \| python -m json.tool` |
| Rapport coloré console | `python tools/view_results.py out/messages.jsonl` |
| Dashboard 1 fenêtre statique | `python tools/build_dashboard.py out/history.jsonl -o dashboard.html` |
| Dashboard live multi-fenêtres | `python tools/build_dashboard.py out/history.jsonl --refresh-seconds 30` |
| Analyse pandas | charger `out/history.jsonl`, filtrer `kind=district` |
| Démo soutenance | `--cycles 0 --acceleration 60 --history-file` + boucle bash |
