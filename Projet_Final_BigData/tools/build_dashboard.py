"""
Generateur de dashboard HTML statique pour visualiser les resultats.

Produit un fichier HTML autonome (sans serveur, sans dependance) contenant :
  - Une carte interactive Leaflet (CDN) avec les 18 quartiers de Tetouan
  - Heatmap colorisee selon la consommation
  - Graphique en barres de la conso par quartier
  - Tableau detaille
  - Liste des anomalies de tension

Usage :
    python main.py --cycles 1 --output-file out/cycle.jsonl --acceleration 900
    python tools/build_dashboard.py out/cycle.jsonl --output dashboard.html
    # puis ouvrir dashboard.html dans un navigateur

Le fichier produit est totalement autonome : il peut etre envoye par email,
mis sur un partage, etc. Pas besoin de serveur Python pour l'afficher.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def load_jsonl(path: Path) -> Dict[str, List[dict]]:
    """Charge un fichier JSONL et regroupe les messages par topic."""
    by_topic: Dict[str, List[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            by_topic[msg["topic"]].append(msg["value"])
    return by_topic


# ============================================================================
# COORDONNEES GPS DES QUARTIERS (extraites de simulator/topology.py)
# ============================================================================

DISTRICT_COORDS = {
    "Medina":             (35.5710, -5.3733),
    "Ensanche":           (35.5734, -5.3710),
    "Mhannech":           (35.5800, -5.3450),
    "Touabel":            (35.5640, -5.3720),
    "Wlad_Lkhames":       (35.5780, -5.3680),
    "Boujarah":           (35.5660, -5.3800),
    "Dersa":              (35.5810, -5.3760),
    "Sania_Ramel":        (35.5938, -5.3203),
    "Coelma":             (35.5660, -5.3650),
    "Tamuda":             (35.5840, -5.3530),
    "Zaouia":             (35.5760, -5.3850),
    "Touta":              (35.5700, -5.3900),
    "Saniat_Rmel":        (35.5942, -5.3265),
    "Kheddadine":         (35.5680, -5.3680),
    "Rmilete":            (35.5870, -5.3550),
    "Ain_Hamra":          (35.5550, -5.3750),
    "Iberia":             (35.5750, -5.3580),
    "Zone_Industrielle":  (35.5400, -5.3500),
}


# ============================================================================
# HTML TEMPLATE
# ============================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Tetouan Smart Grid Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0e1117;
    color: #e0e0e0;
    padding: 20px;
  }
  h1 {
    color: #4cc2ff;
    margin-bottom: 10px;
    font-weight: 300;
  }
  .subtitle {
    color: #888;
    margin-bottom: 30px;
    font-size: 14px;
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 30px;
  }
  .stat-card {
    background: #1a1f2e;
    border: 1px solid #2a3142;
    border-radius: 8px;
    padding: 20px;
  }
  .stat-card .label {
    font-size: 12px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .stat-card .value {
    font-size: 28px;
    color: #4cc2ff;
    font-weight: 600;
    margin-top: 8px;
  }
  .stat-card.warn .value { color: #ffb84d; }
  .stat-card.crit .value { color: #ff5566; }
  .stat-card.ok .value { color: #66dd99; }

  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 30px;
  }
  @media (max-width: 1100px) {
    .grid-2 { grid-template-columns: 1fr; }
  }
  .panel {
    background: #1a1f2e;
    border: 1px solid #2a3142;
    border-radius: 8px;
    padding: 20px;
  }
  .panel h2 {
    color: #4cc2ff;
    font-size: 18px;
    font-weight: 400;
    margin-bottom: 15px;
    border-bottom: 1px solid #2a3142;
    padding-bottom: 10px;
  }
  #map {
    height: 500px;
    border-radius: 6px;
    background: #0a0e16;
  }
  .bar-chart {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: 140px 1fr 100px;
    align-items: center;
    gap: 10px;
    font-size: 13px;
  }
  .bar-row .label {
    color: #ccc;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bar-track {
    background: #0a0e16;
    height: 22px;
    border-radius: 3px;
    overflow: hidden;
    position: relative;
  }
  .bar-fill {
    height: 100%;
    transition: width 0.3s;
  }
  .bar-fill.residential { background: linear-gradient(to right, #2d8a4a, #66dd99); }
  .bar-fill.commercial  { background: linear-gradient(to right, #b8861a, #ffd166); }
  .bar-fill.industrial  { background: linear-gradient(to right, #8a2dab, #cc66ff); }
  .bar-row .value {
    text-align: right;
    color: #ffb84d;
    font-variant-numeric: tabular-nums;
    font-size: 12px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th, td {
    padding: 8px 10px;
    text-align: left;
    border-bottom: 1px solid #2a3142;
  }
  th {
    color: #888;
    font-weight: 500;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 1px;
  }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .zone-residential { color: #66dd99; }
  .zone-commercial  { color: #ffd166; }
  .zone-industrial  { color: #cc66ff; }
  .voltage-low      { color: #ff5566; font-weight: 600; }
  .voltage-warn     { color: #ffb84d; }
  .voltage-ok       { color: #66dd99; }
  .anomaly-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }
  .anomaly-badge.crit { background: #4d1622; color: #ff5566; }
  .anomaly-badge.warn { background: #4d3812; color: #ffb84d; }
  .anomaly-badge.ok   { background: #14401f; color: #66dd99; }
  .footer {
    margin-top: 30px;
    color: #555;
    font-size: 12px;
    text-align: center;
  }
  .leaflet-popup-content {
    color: #222;
    font-size: 13px;
    min-width: 180px;
  }
  .leaflet-popup-content b { color: #0066cc; }
</style>
</head>
<body>

<h1>Tetouan Smart Grid Dashboard</h1>
<div class="subtitle">__SUBTITLE__</div>

<div class="stats-grid">
  <div class="stat-card">
    <div class="label">Compteurs</div>
    <div class="value">__TOTAL_METERS__</div>
  </div>
  <div class="stat-card">
    <div class="label">Distributeurs</div>
    <div class="value">__TOTAL_DISTRIBUTORS__</div>
  </div>
  <div class="stat-card">
    <div class="label">Concentrateurs</div>
    <div class="value">__TOTAL_CONCENTRATORS__</div>
  </div>
  <div class="stat-card">
    <div class="label">Energie totale</div>
    <div class="value">__TOTAL_ENERGY__ kWh</div>
  </div>
  <div class="stat-card __ANOMALY_CARD_CLASS__">
    <div class="label">Anomalies tension</div>
    <div class="value">__TOTAL_ANOMALIES__</div>
  </div>
</div>

<div class="grid-2">
  <div class="panel">
    <h2>Carte de Tetouan — Heatmap consommation</h2>
    <div id="map"></div>
  </div>
  <div class="panel">
    <h2>Consommation par quartier (kWh)</h2>
    <div class="bar-chart" id="barchart">__BAR_CHART_ROWS__</div>
  </div>
</div>

<div class="panel" style="margin-bottom: 20px;">
  <h2>Detail par quartier</h2>
  <table>
    <thead>
      <tr>
        <th>Quartier</th>
        <th>Type</th>
        <th class="num">Compteurs</th>
        <th class="num">Distributeurs</th>
        <th class="num">Energie kWh</th>
        <th class="num">Tension moy</th>
        <th class="num">Tension min</th>
        <th class="num">Anomalies</th>
      </tr>
    </thead>
    <tbody id="districts-table">__DISTRICTS_TABLE_ROWS__</tbody>
  </table>
</div>

<div class="panel">
  <h2>Top 20 anomalies de tension</h2>
  <table>
    <thead>
      <tr>
        <th>Compteur</th>
        <th>Quartier</th>
        <th>Distributeur</th>
        <th class="num">Tension (V)</th>
        <th>Type</th>
      </tr>
    </thead>
    <tbody>__ANOMALIES_TABLE_ROWS__</tbody>
  </table>
</div>

<div class="footer">
  Genere par tools/build_dashboard.py — Projet Big Data Tetouan
</div>

<script>
  const districts = __DISTRICTS_JSON__;

  const map = L.map('map').setView([35.575, -5.365], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19
  }).addTo(map);

  const maxEnergy = Math.max(...districts.map(d => d.total_energy_kwh));

  // gradient de couleurs selon la consommation
  function colorForRatio(r, zoneType) {
    // intensite de couleur, modulee par le type
    const base = {
      "Residential": [102, 221, 153],  // vert
      "Commercial":  [255, 209, 102],  // orange
      "Industrial":  [204, 102, 255],  // violet
    }[zoneType] || [76, 194, 255];
    const t = 0.4 + 0.6 * r;
    return `rgb(${Math.round(base[0]*t)}, ${Math.round(base[1]*t)}, ${Math.round(base[2]*t)})`;
  }

  districts.forEach(d => {
    const ratio = d.total_energy_kwh / maxEnergy;
    const radius = 8 + 25 * ratio;
    const color = colorForRatio(ratio, d.zone_type);
    const marker = L.circleMarker([d.latitude, d.longitude], {
      radius: radius,
      fillColor: color,
      fillOpacity: 0.7,
      color: '#fff',
      weight: 1.5
    }).addTo(map);

    const popup = `
      <b>${d.district}</b><br>
      Type : <i>${d.zone_type}</i><br>
      Compteurs : ${d.total_meters.toLocaleString()}<br>
      Distributeurs : ${d.total_distributors}<br>
      Energie : <b>${d.total_energy_kwh.toLocaleString(undefined, {maximumFractionDigits: 2})} kWh</b><br>
      Tension moy : ${d.avg_voltage.toFixed(2)} V<br>
      Tension min : ${d.min_voltage.toFixed(2)} V<br>
      Anomalies : <b>${d.anomalies_count}</b>
    `;
    marker.bindPopup(popup);
  });
</script>

</body>
</html>
"""


# ============================================================================
# RENDU
# ============================================================================


def fmt_int(x: float) -> str:
    return f"{int(x):,}".replace(",", " ")


def fmt_float(x: float, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", " ")


def render_bar_rows(districts: List[dict], max_energy: float) -> str:
    rows = []
    for d in districts:
        ratio = d["total_energy_kwh"] / max_energy * 100
        zone_class = d["zone_type"].lower()
        rows.append(
            f'<div class="bar-row">'
            f'<span class="label">{d["district"]}</span>'
            f'<div class="bar-track"><div class="bar-fill {zone_class}" style="width: {ratio:.1f}%"></div></div>'
            f'<span class="value">{fmt_float(d["total_energy_kwh"])}</span>'
            f'</div>'
        )
    return "\n".join(rows)


def render_districts_table(districts: List[dict]) -> str:
    rows = []
    for d in districts:
        zone_class = "zone-" + d["zone_type"].lower()
        anom = d["anomalies_count"]
        if anom > 5:
            anom_class = "crit"
        elif anom > 0:
            anom_class = "warn"
        else:
            anom_class = "ok"

        vmin = d["min_voltage"]
        if vmin < 207:
            vmin_class = "voltage-low"
        elif vmin < 215:
            vmin_class = "voltage-warn"
        else:
            vmin_class = "voltage-ok"

        rows.append(
            f"<tr>"
            f"<td>{d['district']}</td>"
            f"<td class='{zone_class}'>{d['zone_type']}</td>"
            f"<td class='num'>{fmt_int(d['total_meters'])}</td>"
            f"<td class='num'>{d['total_distributors']}</td>"
            f"<td class='num'>{fmt_float(d['total_energy_kwh'])}</td>"
            f"<td class='num'>{fmt_float(d['avg_voltage'])}</td>"
            f"<td class='num {vmin_class}'>{fmt_float(d['min_voltage'])}</td>"
            f"<td class='num'><span class='anomaly-badge {anom_class}'>{anom}</span></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def render_anomalies_table(meters: List[dict], n: int = 20) -> str:
    anomalies = [m for m in meters if m["voltage"] < 207 or m["voltage"] > 253]
    if not anomalies:
        return "<tr><td colspan='5' style='text-align:center; color:#66dd99'>Aucune anomalie detectee</td></tr>"
    anomalies.sort(key=lambda m: abs(m["voltage"] - 230), reverse=True)
    rows = []
    for m in anomalies[:n]:
        v = m["voltage"]
        type_label = "SOUS-TENSION" if v < 207 else "SUR-TENSION"
        rows.append(
            f"<tr>"
            f"<td>{m['meter_id']}</td>"
            f"<td>{m['district']}</td>"
            f"<td>{m['distributor_id']}</td>"
            f"<td class='num voltage-low'>{fmt_float(v)}</td>"
            f"<td class='voltage-low'>{type_label}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def build_dashboard(input_path: Path, output_path: Path) -> None:
    by_topic = load_jsonl(input_path)

    meters = by_topic.get("tetouan.meters.readings", [])
    distributors = by_topic.get("tetouan.distributors.aggregated", [])
    concentrators = by_topic.get("tetouan.concentrators.aggregated", [])
    centers = by_topic.get("tetouan.center.ingest", [])

    # ajout des coordonnees GPS dans les concentrateurs pour la carte
    enriched_districts = []
    for c in concentrators:
        coords = DISTRICT_COORDS.get(c["district"], (35.575, -5.365))
        enriched_districts.append({**c, "latitude": coords[0], "longitude": coords[1]})

    # tri par energie desc
    enriched_districts.sort(key=lambda d: d["total_energy_kwh"], reverse=True)

    total_energy = sum(d["total_energy_kwh"] for d in enriched_districts)
    total_anomalies = sum(d["anomalies_count"] for d in enriched_districts)
    max_energy = max((d["total_energy_kwh"] for d in enriched_districts), default=1)

    # subtitle
    subtitle = "Aucun cycle disponible"
    if centers:
        recap = centers[-1]
        subtitle = (
            f"Cycle {recap['cycle_id']} | "
            f"{recap['cycle_start']} -> {recap['cycle_end']} | "
            f"{recap['districts_reported']} quartiers"
        )

    if total_anomalies > 50:
        anomaly_class = "crit"
    elif total_anomalies > 0:
        anomaly_class = "warn"
    else:
        anomaly_class = "ok"

    html = HTML_TEMPLATE
    html = html.replace("__SUBTITLE__", subtitle)
    html = html.replace("__TOTAL_METERS__", fmt_int(len(meters)))
    html = html.replace("__TOTAL_DISTRIBUTORS__", fmt_int(len(distributors)))
    html = html.replace("__TOTAL_CONCENTRATORS__", fmt_int(len(concentrators)))
    html = html.replace("__TOTAL_ENERGY__", fmt_float(total_energy))
    html = html.replace("__TOTAL_ANOMALIES__", str(total_anomalies))
    html = html.replace("__ANOMALY_CARD_CLASS__", anomaly_class)
    html = html.replace("__BAR_CHART_ROWS__", render_bar_rows(enriched_districts, max_energy))
    html = html.replace("__DISTRICTS_TABLE_ROWS__", render_districts_table(enriched_districts))
    html = html.replace("__ANOMALIES_TABLE_ROWS__", render_anomalies_table(meters))
    html = html.replace("__DISTRICTS_JSON__", json.dumps(enriched_districts))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genere un dashboard HTML statique des resultats."
    )
    parser.add_argument("input_file", type=str,
                        help="Fichier JSONL produit par main.py --output-file")
    parser.add_argument("--output", "-o", type=str, default="dashboard.html",
                        help="Fichier HTML de sortie (defaut: dashboard.html)")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERREUR : fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    build_dashboard(input_path, output_path)
    print(f"Dashboard genere : {output_path.absolute()}")
    print(f"Ouvrez ce fichier dans un navigateur pour le visualiser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
