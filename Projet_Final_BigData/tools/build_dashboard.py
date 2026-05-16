"""
Generateur de dashboard HTML statique pour visualiser le fenetrage 15 min.

Lit le fichier d'historique des fenetres produit par le simulateur via
l'option --history-file et produit un dashboard HTML autonome qui montre :

  - Bandeau "fenetre courante" (window_start -> window_end)
  - Timeline des fenetres precedentes avec leurs valeurs
  - Graphique SVG de tendance temporelle par quartier (top 5 + total)
  - Carte Leaflet de Tetouan (taille des cercles = energie de la fenetre courante)
  - Tableau detaille de la fenetre courante
  - Top anomalies de tension globales

Le HTML peut s'auto-rafraichir via l'option --refresh-seconds, ce qui
permet une visualisation "live" des fenetres successives quand le
simulateur tourne en boucle.

Usage :
    # 1) lancer le simulateur en boucle, qui ecrit l'historique
    python main.py --cycles 0 --acceleration 60 \\
        --history-file out/history.jsonl

    # 2) generer le dashboard auto-rafraichi
    python tools/build_dashboard.py out/history.jsonl \\
        --output dashboard.html --refresh-seconds 30

    # 3) regenerer le dashboard a chaque nouvelle fenetre (boucle bash) :
    while true; do
        python tools/build_dashboard.py out/history.jsonl -o dashboard.html
        sleep 15
    done

Compatibilite : si le fichier passe ne contient pas de lignes "kind=district"
(format historique), le script bascule sur l'ancien format (fichier de
messages mock JSONL produit par --output-file). Dans ce cas, seul le dernier
cycle est affiche, sans timeline.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================================
# COORDONNEES GPS DES QUARTIERS (extraites de simulator/topology.py)
# ============================================================================

DISTRICT_COORDS: Dict[str, Tuple[float, float]] = {
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
# CHARGEMENT DU FICHIER D'HISTORIQUE
# ============================================================================


def load_history(path: Path) -> Tuple[Dict[str, List[dict]], List[dict]]:
    """
    Charge un fichier d'historique des fenetres au format JSONL.

    Renvoie (windows_by_district, cycles) :
      - windows_by_district : { district_name : [agg_window_1, agg_window_2, ...] }
        triees par window_start croissant
      - cycles : liste des recaps cycles tries par window_start croissant

    Compatibilite : si aucune ligne kind=district n'est trouvee, on bascule
    sur le format ancien (fichier --output-file avec topic=tetouan.*).
    """
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    by_district: Dict[str, List[dict]] = defaultdict(list)
    cycles: List[dict] = []
    fallback_concentrators: List[dict] = []

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = obj.get("kind")
            if kind == "district":
                by_district[obj["district"]].append(obj)
            elif kind == "cycle":
                cycles.append(obj)
            elif obj.get("topic") == "tetouan.concentrators.aggregated":
                # ancien format : reutiliser comme une fenetre unique
                fallback_concentrators.append(obj["value"])

    # tri par window_start croissant
    for d in by_district.values():
        d.sort(key=lambda x: x.get("window_start", ""))
    cycles.sort(key=lambda x: x.get("window_start", x.get("cycle_start", "")))

    # mode fallback : aucun "kind=district" trouve -> on simule une seule fenetre
    if not by_district and fallback_concentrators:
        # deduper sur (district, timestamp) pour garder le dernier message par quartier
        latest_by_district: Dict[str, dict] = {}
        for c in fallback_concentrators:
            key = c.get("district", "?")
            latest_by_district[key] = c
        for district, c in latest_by_district.items():
            # ajouter window_start/window_end synthetiques si absents
            c.setdefault("window_start", c.get("timestamp"))
            c.setdefault("window_end", c.get("timestamp"))
            by_district[district].append(c)
        if not cycles:
            total_e = sum(c.get("total_energy_kwh", 0) for c in latest_by_district.values())
            total_a = sum(c.get("anomalies_count", 0) for c in latest_by_district.values())
            cycles.append({
                "cycle_id": 0,
                "window_start": next(iter(latest_by_district.values())).get("timestamp"),
                "window_end": next(iter(latest_by_district.values())).get("timestamp"),
                "districts_reported": len(latest_by_district),
                "total_meters": sum(c.get("total_meters", 0) for c in latest_by_district.values()),
                "total_energy_kwh": total_e,
                "anomalies_count": total_a,
            })

    return dict(by_district), cycles


# ============================================================================
# UTILITAIRES DE FORMAT
# ============================================================================


def fmt_int(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def fmt_float(x, dec: int = 2) -> str:
    return f"{x:,.{dec}f}".replace(",", " ")


def fmt_time(iso: Optional[str]) -> str:
    """ '2026-05-16T14:00:00' -> '14:00' """
    if not iso:
        return "—"
    try:
        return iso.split("T")[1][:5]
    except (IndexError, AttributeError):
        return iso


def fmt_datetime(iso: Optional[str]) -> str:
    """ '2026-05-16T14:00:00' -> '2026-05-16 14:00' """
    if not iso:
        return "—"
    return iso.replace("T", " ")[:16]


# ============================================================================
# SVG : COURBES DE TENDANCE
# ============================================================================


def _polyline_points(values: List[float], width: int, height: int,
                     vmin: float, vmax: float) -> str:
    """Convertit une liste de valeurs en chaine de points SVG."""
    if not values:
        return ""
    if vmax == vmin:
        vmax = vmin + 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = (i / max(n - 1, 1)) * width if n > 1 else width / 2
        y = height - ((v - vmin) / (vmax - vmin)) * height
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


def render_trend_svg(
    series: List[Tuple[str, str, List[float]]],
    width: int = 720,
    height: int = 240,
    title: str = "",
    y_label: str = "kWh",
    x_labels: Optional[List[str]] = None,
) -> str:
    """
    Genere un SVG multi-courbes.

    :param series: liste de (label, color, values)
    :param x_labels: labels des points en x (ex: ["14:00", "14:15", ...])
    """
    if not series:
        return f"<div style='color:#888'>Aucune donnee pour : {title}</div>"

    # bornes Y
    all_vals = [v for _, _, vals in series for v in vals]
    vmin, vmax = min(all_vals), max(all_vals)
    # marge 5%
    span = max(vmax - vmin, 1)
    vmin -= span * 0.05
    vmax += span * 0.05

    pad_left, pad_right = 60, 20
    pad_top, pad_bottom = 30, 40
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    parts: List[str] = []
    parts.append(
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;background:#0a0e16;'
        f'border-radius:6px;border:1px solid #2a3142">'
    )
    # titre
    if title:
        parts.append(
            f'<text x="{pad_left}" y="20" fill="#4cc2ff" '
            f'font-size="13" font-family="sans-serif">{title}</text>'
        )

    # grille horizontale + labels Y
    for i in range(5):
        y = pad_top + i * plot_h / 4
        v = vmax - (vmax - vmin) * i / 4
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" '
            f'y2="{y:.1f}" stroke="#2a3142" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{pad_left - 6}" y="{y + 4:.1f}" fill="#666" '
            f'font-size="10" text-anchor="end" '
            f'font-family="sans-serif">{fmt_float(v, 0)}</text>'
        )

    # courbes
    for label, color, values in series:
        pts = _polyline_points(values, plot_w, plot_h, vmin, vmax)
        # decaler chaque point par (pad_left, pad_top)
        shifted = " ".join(
            f"{float(p.split(',')[0]) + pad_left:.1f},"
            f"{float(p.split(',')[1]) + pad_top:.1f}"
            for p in pts.split() if p
        )
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'points="{shifted}"/>'
        )
        # points
        if pts:
            for p in shifted.split():
                cx, cy = p.split(",")
                parts.append(
                    f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}"/>'
                )

    # labels X
    if x_labels:
        n = len(x_labels)
        for i, lbl in enumerate(x_labels):
            x = pad_left + (i / max(n - 1, 1)) * plot_w if n > 1 else pad_left + plot_w / 2
            parts.append(
                f'<text x="{x:.1f}" y="{height - 20:.1f}" fill="#888" '
                f'font-size="10" text-anchor="middle" '
                f'font-family="sans-serif">{lbl}</text>'
            )

    # legende
    legend_y = height - 6
    legend_x = pad_left
    for label, color, _ in series:
        parts.append(
            f'<rect x="{legend_x}" y="{legend_y - 8}" width="10" '
            f'height="3" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{legend_x + 14}" y="{legend_y - 4}" fill="#ccc" '
            f'font-size="10" font-family="sans-serif">{label}</text>'
        )
        legend_x += 14 + 7 * len(label) + 16

    # label Y
    parts.append(
        f'<text x="10" y="{pad_top - 8}" fill="#888" font-size="10" '
        f'font-family="sans-serif">{y_label}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


# ============================================================================
# RENDU HTML
# ============================================================================


def color_for_zone(zone: str) -> str:
    return {
        "Residential": "#66dd99",
        "Commercial":  "#ffd166",
        "Industrial":  "#cc66ff",
    }.get(zone, "#4cc2ff")


def render_window_timeline(cycles: List[dict]) -> str:
    """Tableau timeline des fenetres."""
    if not cycles:
        return "<tr><td colspan='6' style='text-align:center;color:#888'>Aucun historique</td></tr>"
    rows = []
    last_energy = None
    for c in cycles[-12:]:
        e = c.get("total_energy_kwh", 0)
        # variation par rapport a la fenetre precedente
        if last_energy is None or last_energy == 0:
            delta = "—"
            delta_class = ""
        else:
            pct = (e - last_energy) / last_energy * 100
            sign = "+" if pct >= 0 else ""
            delta = f"{sign}{pct:.1f}%"
            delta_class = "delta-up" if pct >= 0 else "delta-down"
        last_energy = e

        anom = c.get("anomalies_count", 0)
        anom_class = "crit" if anom > 50 else ("warn" if anom > 0 else "ok")

        rows.append(
            f"<tr>"
            f"<td><span class='cycle-id'>#{c.get('cycle_id', '?')}</span></td>"
            f"<td>{fmt_datetime(c.get('window_start'))}</td>"
            f"<td>{fmt_time(c.get('window_end'))}</td>"
            f"<td class='num'>{fmt_int(c.get('total_meters', 0))}</td>"
            f"<td class='num energy'>{fmt_float(e)}</td>"
            f"<td class='num {delta_class}'>{delta}</td>"
            f"<td class='num'><span class='anomaly-badge {anom_class}'>{anom}</span></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def render_districts_table(latest_by_district: Dict[str, dict]) -> str:
    """Tableau detaille de la fenetre courante par quartier."""
    sorted_d = sorted(
        latest_by_district.values(),
        key=lambda d: d.get("total_energy_kwh", 0),
        reverse=True,
    )
    rows = []
    for d in sorted_d:
        zone_class = "zone-" + d.get("zone_type", "Residential").lower()
        anom = d.get("anomalies_count", 0)
        anom_class = "crit" if anom > 5 else ("warn" if anom > 0 else "ok")

        vmin = d.get("min_voltage", 230)
        if vmin < 207:
            vmin_class = "voltage-low"
        elif vmin < 215:
            vmin_class = "voltage-warn"
        else:
            vmin_class = "voltage-ok"

        rows.append(
            f"<tr>"
            f"<td>{d.get('district', '?')}</td>"
            f"<td class='{zone_class}'>{d.get('zone_type', '?')}</td>"
            f"<td class='num'>{fmt_int(d.get('total_meters', 0))}</td>"
            f"<td class='num'>{d.get('total_distributors', '—')}</td>"
            f"<td class='num energy'>{fmt_float(d.get('total_energy_kwh', 0))}</td>"
            f"<td class='num'>{fmt_float(d.get('avg_voltage', 0))}</td>"
            f"<td class='num {vmin_class}'>{fmt_float(d.get('min_voltage', 0))}</td>"
            f"<td class='num'><span class='anomaly-badge {anom_class}'>{anom}</span></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def render_bar_chart(latest_by_district: Dict[str, dict]) -> str:
    """Bar chart HTML/CSS de la conso par quartier sur la fenetre courante."""
    sorted_d = sorted(
        latest_by_district.values(),
        key=lambda d: d.get("total_energy_kwh", 0),
        reverse=True,
    )
    if not sorted_d:
        return ""
    max_e = max(d.get("total_energy_kwh", 0) for d in sorted_d) or 1
    rows = []
    for d in sorted_d:
        ratio = d.get("total_energy_kwh", 0) / max_e * 100
        zclass = d.get("zone_type", "Residential").lower()
        rows.append(
            f'<div class="bar-row">'
            f'<span class="label">{d.get("district", "?")}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill {zclass}" style="width: {ratio:.1f}%"></div>'
            f'</div>'
            f'<span class="value">{fmt_float(d.get("total_energy_kwh", 0))}</span>'
            f'</div>'
        )
    return "\n".join(rows)


def build_district_map_data(latest_by_district: Dict[str, dict]) -> List[dict]:
    """Liste des quartiers + GPS pour la carte Leaflet."""
    out = []
    for name, d in latest_by_district.items():
        coords = DISTRICT_COORDS.get(name, (35.575, -5.365))
        out.append({**d, "latitude": coords[0], "longitude": coords[1]})
    return out


# ============================================================================
# TEMPLATE HTML
# ============================================================================


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Tetouan Smart Grid Dashboard — Fenetrage 15 min</title>
__REFRESH_META__
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0e1117; color: #e0e0e0; padding: 20px; line-height: 1.4;
  }
  h1 { color: #4cc2ff; font-weight: 300; margin-bottom: 6px; }
  .subtitle { color: #888; margin-bottom: 16px; font-size: 13px; }

  /* bandeau fenetre courante */
  .window-banner {
    background: linear-gradient(90deg, #1a3142 0%, #0e1117 100%);
    border: 1px solid #2a4a6a; border-left: 4px solid #4cc2ff;
    border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;
    display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
  }
  .window-banner .pill {
    background: #1a3142; padding: 6px 12px; border-radius: 16px;
    font-size: 12px; color: #4cc2ff; letter-spacing: 0.5px;
  }
  .window-banner .window-range {
    font-size: 22px; font-family: ui-monospace, monospace; color: #fff;
  }
  .window-banner .window-range .arrow { color: #4cc2ff; margin: 0 8px; }
  .window-banner .meta { color: #888; font-size: 12px; }
  .window-banner .badge-live {
    background: #14401f; color: #66dd99; padding: 4px 10px; border-radius: 10px;
    font-size: 11px; font-weight: 600;
  }

  .stats-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px; margin-bottom: 24px;
  }
  .stat-card {
    background: #1a1f2e; border: 1px solid #2a3142; border-radius: 8px; padding: 18px;
  }
  .stat-card .label {
    font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1px;
  }
  .stat-card .value {
    font-size: 26px; color: #4cc2ff; font-weight: 600; margin-top: 6px;
  }
  .stat-card .delta { font-size: 12px; margin-top: 4px; }
  .stat-card.warn .value { color: #ffb84d; }
  .stat-card.crit .value { color: #ff5566; }
  .stat-card.ok .value { color: #66dd99; }

  .grid-2 {
    display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;
  }
  @media (max-width: 1100px) { .grid-2 { grid-template-columns: 1fr; } }

  .panel {
    background: #1a1f2e; border: 1px solid #2a3142; border-radius: 8px;
    padding: 18px; margin-bottom: 20px;
  }
  .panel h2 {
    color: #4cc2ff; font-size: 16px; font-weight: 400; margin-bottom: 12px;
    border-bottom: 1px solid #2a3142; padding-bottom: 8px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .panel h2 .hint { font-size: 11px; color: #888; font-weight: 400; }

  #map { height: 480px; border-radius: 6px; background: #0a0e16; }

  .bar-chart { display: flex; flex-direction: column; gap: 5px; }
  .bar-row {
    display: grid; grid-template-columns: 130px 1fr 90px;
    align-items: center; gap: 10px; font-size: 12px;
  }
  .bar-row .label { color: #ccc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-track {
    background: #0a0e16; height: 20px; border-radius: 3px; overflow: hidden;
  }
  .bar-fill { height: 100%; transition: width 0.3s; }
  .bar-fill.residential { background: linear-gradient(to right, #2d8a4a, #66dd99); }
  .bar-fill.commercial  { background: linear-gradient(to right, #b8861a, #ffd166); }
  .bar-fill.industrial  { background: linear-gradient(to right, #8a2dab, #cc66ff); }
  .bar-row .value { text-align: right; color: #ffb84d; font-variant-numeric: tabular-nums; font-size: 11px; }

  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid #2a3142; }
  th {
    color: #888; font-weight: 500; text-transform: uppercase;
    font-size: 10px; letter-spacing: 1px; position: sticky; top: 0; background: #1a1f2e;
  }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td.energy { color: #ffb84d; font-weight: 500; }

  .zone-residential { color: #66dd99; }
  .zone-commercial  { color: #ffd166; }
  .zone-industrial  { color: #cc66ff; }
  .voltage-low { color: #ff5566; font-weight: 600; }
  .voltage-warn { color: #ffb84d; }
  .voltage-ok { color: #66dd99; }
  .delta-up   { color: #ff8866; }
  .delta-down { color: #66dd99; }
  .cycle-id { background: #1a3142; color: #4cc2ff; padding: 2px 8px;
              border-radius: 10px; font-family: ui-monospace, monospace; font-size: 11px; }

  .anomaly-badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 600;
  }
  .anomaly-badge.crit { background: #4d1622; color: #ff5566; }
  .anomaly-badge.warn { background: #4d3812; color: #ffb84d; }
  .anomaly-badge.ok   { background: #14401f; color: #66dd99; }

  .footer { margin-top: 24px; color: #555; font-size: 11px; text-align: center; }
  .leaflet-popup-content { color: #222; font-size: 13px; min-width: 200px; }
  .leaflet-popup-content b { color: #0066cc; }
</style>
</head>
<body>

<h1>Tetouan Smart Grid Dashboard</h1>
<div class="subtitle">Fenetrage tumbling 15 min (Spark Structured Streaming) — __WINDOWS_COUNT__ fenetres dans l'historique __REFRESH_TEXT__</div>

<!-- ============== BANDEAU FENETRE COURANTE ============== -->
<div class="window-banner">
  <div class="pill">FENETRE COURANTE</div>
  <div class="window-range">
    __WIN_START__ <span class="arrow">&rarr;</span> __WIN_END__
  </div>
  <div class="meta">Cycle #__CYCLE_ID__ &middot; Duree 15 min</div>
  <div class="badge-live">__LIVE_BADGE__</div>
</div>

<!-- ============== STATS GLOBALES FENETRE COURANTE ============== -->
<div class="stats-grid">
  <div class="stat-card">
    <div class="label">Compteurs</div>
    <div class="value">__TOTAL_METERS__</div>
  </div>
  <div class="stat-card">
    <div class="label">Energie fenetre</div>
    <div class="value">__TOTAL_ENERGY__ kWh</div>
    <div class="delta __DELTA_CLASS__">__DELTA_TEXT__ vs fenetre prec.</div>
  </div>
  <div class="stat-card __ANOM_CLASS__">
    <div class="label">Anomalies tension</div>
    <div class="value">__TOTAL_ANOMALIES__</div>
  </div>
  <div class="stat-card">
    <div class="label">Quartiers actifs</div>
    <div class="value">__DISTRICTS_COUNT__</div>
  </div>
  <div class="stat-card">
    <div class="label">Distributeurs</div>
    <div class="value">__TOTAL_DISTRIBUTORS__</div>
  </div>
</div>

<!-- ============== TENDANCES (SVG) ============== -->
<div class="panel">
  <h2>Tendance energie totale par fenetre 15 min
    <span class="hint">__TREND_HINT__</span>
  </h2>
  __TREND_TOTAL_SVG__
</div>

<div class="panel">
  <h2>Tendance par quartier (Top 5 + 1 industriel)
    <span class="hint">une courbe par quartier sur les __TREND_N__ dernieres fenetres</span>
  </h2>
  __TREND_DISTRICTS_SVG__
</div>

<!-- ============== TIMELINE FENETRES ============== -->
<div class="panel">
  <h2>Timeline des fenetres 15 min
    <span class="hint">12 dernieres fenetres</span>
  </h2>
  <table>
    <thead>
      <tr>
        <th>Cycle</th>
        <th>Window start</th>
        <th>Window end</th>
        <th class="num">Compteurs</th>
        <th class="num">Energie kWh</th>
        <th class="num">&Delta; vs prec.</th>
        <th class="num">Anomalies</th>
      </tr>
    </thead>
    <tbody>__TIMELINE_ROWS__</tbody>
  </table>
</div>

<!-- ============== CARTE + BAR CHART ============== -->
<div class="grid-2">
  <div class="panel">
    <h2>Carte Tetouan (fenetre courante)
      <span class="hint">taille = energie kWh</span>
    </h2>
    <div id="map"></div>
  </div>
  <div class="panel">
    <h2>Conso par quartier (fenetre courante)</h2>
    <div class="bar-chart" id="barchart">__BAR_CHART_ROWS__</div>
  </div>
</div>

<!-- ============== TABLEAU DETAILLE ============== -->
<div class="panel">
  <h2>Detail par quartier (fenetre __WIN_START__ &rarr; __WIN_END__)</h2>
  <table>
    <thead>
      <tr>
        <th>Quartier</th>
        <th>Type</th>
        <th class="num">Compteurs</th>
        <th class="num">Distrib.</th>
        <th class="num">Energie kWh</th>
        <th class="num">V moy</th>
        <th class="num">V min</th>
        <th class="num">Anomalies</th>
      </tr>
    </thead>
    <tbody id="districts-table">__DISTRICTS_TABLE_ROWS__</tbody>
  </table>
</div>

<div class="footer">
  Genere par tools/build_dashboard.py &mdash; Fichier source : __INPUT_FILE__ &mdash; Genere a __GENERATED_AT__
</div>

<script>
  const districts = __DISTRICTS_JSON__;

  if (districts.length > 0) {
    const map = L.map('map').setView([35.575, -5.365], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap', maxZoom: 19
    }).addTo(map);

    const maxEnergy = Math.max(...districts.map(d => d.total_energy_kwh || 0));

    function colorForRatio(r, zoneType) {
      const base = {
        "Residential": [102, 221, 153], "Commercial": [255, 209, 102],
        "Industrial":  [204, 102, 255]
      }[zoneType] || [76, 194, 255];
      const t = 0.4 + 0.6 * r;
      return `rgb(${Math.round(base[0]*t)}, ${Math.round(base[1]*t)}, ${Math.round(base[2]*t)})`;
    }

    districts.forEach(d => {
      const ratio = (d.total_energy_kwh || 0) / (maxEnergy || 1);
      const radius = 8 + 25 * ratio;
      const color = colorForRatio(ratio, d.zone_type);
      const marker = L.circleMarker([d.latitude, d.longitude], {
        radius: radius, fillColor: color, fillOpacity: 0.7, color: '#fff', weight: 1.5
      }).addTo(map);
      marker.bindPopup(`
        <b>${d.district}</b><br>
        Type : <i>${d.zone_type}</i><br>
        Window : ${d.window_start || '—'} &rarr; ${(d.window_end||'—').split('T').pop().slice(0,5)}<br>
        Compteurs : ${(d.total_meters || 0).toLocaleString()}<br>
        Distributeurs : ${d.total_distributors || '—'}<br>
        Energie : <b>${(d.total_energy_kwh || 0).toLocaleString(undefined, {maximumFractionDigits: 2})} kWh</b><br>
        Tension moy : ${(d.avg_voltage || 0).toFixed(2)} V<br>
        Tension min : ${(d.min_voltage || 0).toFixed(2)} V<br>
        Anomalies : <b>${d.anomalies_count || 0}</b>
      `);
    });
  }
</script>

</body>
</html>
"""


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================


def build_dashboard(
    input_path: Path,
    output_path: Path,
    refresh_seconds: int = 0,
    trend_n: int = 10,
) -> None:
    """
    Construit le dashboard HTML a partir du fichier d'historique.

    :param refresh_seconds: si > 0, le HTML s'auto-rafraichit a cet intervalle
    :param trend_n: nombre de fenetres affichees dans les graphiques de tendance
    """
    by_district, cycles = load_history(input_path)

    if not cycles:
        # rien a afficher - genere une page minimale
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "<html><body style='background:#0e1117;color:#e0e0e0;font-family:sans-serif;"
            f"padding:40px'><h1>Aucun historique disponible</h1><p>Le fichier <code>{input_path}</code>"
            " ne contient pas encore de fenetre. Lance d'abord le simulateur avec "
            "<code>--history-file</code>.</p></body></html>",
            encoding="utf-8",
        )
        print(f"Dashboard (vide) : {output_path.absolute()}")
        return

    # fenetre courante = derniere fenetre publiee
    current_cycle = cycles[-1]
    win_start = current_cycle.get("window_start", current_cycle.get("cycle_start", ""))
    win_end = current_cycle.get("window_end", current_cycle.get("cycle_end", ""))

    # toutes les fenetres distinctes triees
    all_starts = sorted({
        d["window_start"]
        for ds in by_district.values()
        for d in ds
        if d.get("window_start")
    })
    # on prend les N dernieres pour les graphiques de tendance
    trend_starts = all_starts[-trend_n:]

    # latest_by_district : dict {name : derniere fenetre du quartier}
    latest_by_district: Dict[str, dict] = {}
    for name, dlist in by_district.items():
        # filtrer pour la fenetre courante si possible, sinon la derniere
        match = next(
            (d for d in reversed(dlist) if d.get("window_start") == win_start),
            None,
        )
        latest_by_district[name] = match or dlist[-1]

    # delta vs fenetre precedente
    delta_text = "—"
    delta_class = ""
    if len(cycles) >= 2:
        prev_e = cycles[-2].get("total_energy_kwh", 0)
        cur_e = current_cycle.get("total_energy_kwh", 0)
        if prev_e:
            pct = (cur_e - prev_e) / prev_e * 100
            sign = "+" if pct >= 0 else ""
            delta_text = f"{sign}{pct:.1f}%"
            delta_class = "delta-up" if pct >= 0 else "delta-down"

    # ===== GRAPHIQUES DE TENDANCE =====

    # courbe totale energie par fenetre
    cycles_for_trend = cycles[-trend_n:]
    total_series = [
        ("Energie totale (kWh)", "#4cc2ff",
         [c.get("total_energy_kwh", 0) for c in cycles_for_trend]),
    ]
    total_x_labels = [fmt_time(c.get("window_start")) for c in cycles_for_trend]
    trend_total_svg = render_trend_svg(
        total_series, width=1100, height=220,
        title="Energie totale Tetouan par fenetre 15 min",
        y_label="kWh", x_labels=total_x_labels,
    )

    # courbes par quartier (top 5 par energie + 1 industriel)
    district_totals = sorted(
        latest_by_district.values(),
        key=lambda d: d.get("total_energy_kwh", 0),
        reverse=True,
    )
    selected: List[dict] = list(district_totals[:5])
    has_industrial = any(d.get("zone_type") == "Industrial" for d in selected)
    if not has_industrial:
        ind = next(
            (d for d in district_totals if d.get("zone_type") == "Industrial"),
            None,
        )
        if ind:
            selected.append(ind)

    palette = ["#4cc2ff", "#ffb84d", "#66dd99", "#cc66ff", "#ff8866", "#ffd166"]
    district_series: List[Tuple[str, str, List[float]]] = []
    for i, d in enumerate(selected):
        name = d["district"]
        # construire la serie : energie de chaque fenetre dans trend_starts
        idx_by_start = {
            x.get("window_start"): x.get("total_energy_kwh", 0)
            for x in by_district.get(name, [])
        }
        values = [idx_by_start.get(ws, 0) for ws in trend_starts]
        district_series.append((name, palette[i % len(palette)], values))
    trend_x_labels = [fmt_time(ws) for ws in trend_starts]
    trend_districts_svg = render_trend_svg(
        district_series, width=1100, height=300,
        title="Tendance par quartier",
        y_label="kWh", x_labels=trend_x_labels,
    )

    # ===== AUTO-REFRESH =====
    refresh_meta = ""
    refresh_text = ""
    live_badge = "STATIQUE"
    if refresh_seconds > 0:
        refresh_meta = f'<meta http-equiv="refresh" content="{refresh_seconds}">'
        refresh_text = f"&middot; auto-refresh toutes les {refresh_seconds} sec"
        live_badge = "LIVE"

    # ===== ANOM CLASS =====
    anom = current_cycle.get("anomalies_count", 0)
    if anom > 50:
        anom_class = "crit"
    elif anom > 0:
        anom_class = "warn"
    else:
        anom_class = "ok"

    # ===== ASSEMBLAGE =====
    from datetime import datetime as _dt
    map_data = build_district_map_data(latest_by_district)
    total_distributors = sum(d.get("total_distributors", 0) for d in latest_by_district.values())

    html = HTML_TEMPLATE
    replacements = {
        "__REFRESH_META__": refresh_meta,
        "__REFRESH_TEXT__": refresh_text,
        "__WINDOWS_COUNT__": str(len(cycles)),
        "__WIN_START__": fmt_datetime(win_start),
        "__WIN_END__": fmt_time(win_end),
        "__CYCLE_ID__": str(current_cycle.get("cycle_id", "?")),
        "__LIVE_BADGE__": live_badge,
        "__TOTAL_METERS__": fmt_int(current_cycle.get("total_meters", 0)),
        "__TOTAL_ENERGY__": fmt_float(current_cycle.get("total_energy_kwh", 0)),
        "__DELTA_TEXT__": delta_text,
        "__DELTA_CLASS__": delta_class,
        "__TOTAL_ANOMALIES__": str(anom),
        "__ANOM_CLASS__": anom_class,
        "__DISTRICTS_COUNT__": str(current_cycle.get("districts_reported", len(latest_by_district))),
        "__TOTAL_DISTRIBUTORS__": fmt_int(total_distributors),
        "__TREND_HINT__": f"{len(cycles_for_trend)} dernieres fenetres",
        "__TREND_N__": str(len(trend_starts)),
        "__TREND_TOTAL_SVG__": trend_total_svg,
        "__TREND_DISTRICTS_SVG__": trend_districts_svg,
        "__TIMELINE_ROWS__": render_window_timeline(cycles),
        "__BAR_CHART_ROWS__": render_bar_chart(latest_by_district),
        "__DISTRICTS_TABLE_ROWS__": render_districts_table(latest_by_district),
        "__DISTRICTS_JSON__": json.dumps(map_data),
        "__INPUT_FILE__": str(input_path),
        "__GENERATED_AT__": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    for k, v in replacements.items():
        html = html.replace(k, v)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genere un dashboard HTML statique des resultats avec fenetrage 15 min."
    )
    parser.add_argument(
        "input_file", type=str,
        help="Fichier JSONL d'historique (--history-file) ou de messages (--output-file)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default="dashboard.html",
        help="Fichier HTML de sortie (defaut: dashboard.html)",
    )
    parser.add_argument(
        "--refresh-seconds", type=int, default=0,
        help=(
            "Si > 0, le HTML s'auto-rafraichit a cet intervalle. "
            "Pratique pour visualiser les fenetres successives en live (ex: 30)."
        ),
    )
    parser.add_argument(
        "--trend-n", type=int, default=10,
        help="Nombre de fenetres affichees dans les graphiques de tendance (defaut: 10).",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERREUR : fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    try:
        build_dashboard(
            input_path, output_path,
            refresh_seconds=args.refresh_seconds,
            trend_n=args.trend_n,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 2

    print(f"Dashboard genere : {output_path.absolute()}")
    if args.refresh_seconds > 0:
        print(f"  Auto-refresh actif : toutes les {args.refresh_seconds} secondes")
    print("  Ouvrez ce fichier dans un navigateur pour le visualiser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
