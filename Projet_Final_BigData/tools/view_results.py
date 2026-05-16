"""
Outil de visualisation console des resultats de simulation.

Usage :
    # generer d'abord un cycle dans un fichier
    python main.py --cycles 1 --output-file out/cycle.jsonl --acceleration 900

    # puis visualiser
    python tools/view_results.py out/cycle.jsonl

Affichage :
    - Statistiques globales du cycle
    - Tableau par quartier (energie, anomalies, tension)
    - Top 10 distributeurs les plus charges
    - Top 10 anomalies de tension
    - Histogramme ASCII de la consommation par quartier
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


# ============================================================================
# COULEURS ANSI POUR LE TERMINAL
# ============================================================================
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"


def color(text: str, c: str) -> str:
    return f"{c}{text}{RESET}"


# ============================================================================
# CHARGEMENT DU FICHIER JSONL
# ============================================================================


def load_jsonl(path: Path) -> Dict[str, List[dict]]:
    """Charge un fichier JSONL et regroupe les messages par topic."""
    if not path.exists():
        print(color(f"ERREUR : fichier introuvable : {path}", RED))
        sys.exit(1)

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
# STATISTIQUES GLOBALES
# ============================================================================


def show_global_stats(by_topic: Dict[str, List[dict]]) -> None:
    print(color("=" * 70, CYAN))
    print(color(" STATISTIQUES GLOBALES DU CYCLE ".center(70), BOLD + CYAN))
    print(color("=" * 70, CYAN))

    meters = by_topic.get("tetouan.meters.readings", [])
    distributors = by_topic.get("tetouan.distributors.aggregated", [])
    concentrators = by_topic.get("tetouan.concentrators.aggregated", [])
    centers = by_topic.get("tetouan.center.ingest", [])

    print(f"  {color('Compteurs ayant emis', BLUE):.<55} "
          f"{color(f'{len(meters):>10,}', GREEN)}")
    print(f"  {color('Distributeurs ayant remonte', BLUE):.<55} "
          f"{color(f'{len(distributors):>10,}', GREEN)}")
    print(f"  {color('Concentrateurs ayant remonte', BLUE):.<55} "
          f"{color(f'{len(concentrators):>10,}', GREEN)}")
    print(f"  {color('Recap cycle (centre)', BLUE):.<55} "
          f"{color(f'{len(centers):>10,}', GREEN)}")

    if centers:
        recap = centers[-1]  # dernier cycle
        print()
        print(color(f"  Cycle ID            : ", BLUE) + f"{recap['cycle_id']}")
        print(color(f"  Debut cycle         : ", BLUE) + f"{recap['cycle_start']}")
        print(color(f"  Fin cycle           : ", BLUE) + f"{recap['cycle_end']}")
        print(color(f"  Quartiers reportes  : ", BLUE) + f"{recap['districts_reported']}")
        print(color(f"  Total compteurs     : ", BLUE) +
              color(f"{recap['total_meters']:,}", GREEN))
        print(color(f"  Energie totale      : ", BLUE) +
              color(f"{recap['total_energy_kwh']:,.2f} kWh", YELLOW))
        anomalies = recap['anomalies_count']
        anomaly_color = RED if anomalies > 50 else (YELLOW if anomalies > 0 else GREEN)
        print(color(f"  Anomalies tension   : ", BLUE) +
              color(f"{anomalies}", anomaly_color))
    print()


# ============================================================================
# TABLEAU PAR QUARTIER
# ============================================================================


def show_districts_table(by_topic: Dict[str, List[dict]]) -> None:
    concentrators = by_topic.get("tetouan.concentrators.aggregated", [])
    if not concentrators:
        return

    # trier par energie desc
    sorted_dist = sorted(concentrators, key=lambda x: x["total_energy_kwh"], reverse=True)

    print(color("=" * 100, CYAN))
    print(color(" CONSOMMATION PAR QUARTIER ".center(100), BOLD + CYAN))
    print(color("=" * 100, CYAN))

    header = f"  {'Quartier':<22} {'Type':<13} {'Compteurs':>10} {'Distrib.':>10} {'Energie kWh':>14} {'V moy':>8} {'V min':>8} {'Anom':>6}"
    print(color(header, BOLD))
    print("  " + "-" * 96)

    total_energy = sum(d["total_energy_kwh"] for d in sorted_dist)

    for d in sorted_dist:
        # couleur du type de zone
        ztype = d["zone_type"]
        if ztype == "Industrial":
            ztype_str = color(f"{ztype:<13}", MAGENTA)
        elif ztype == "Commercial":
            ztype_str = color(f"{ztype:<13}", YELLOW)
        else:
            ztype_str = color(f"{ztype:<13}", GREEN)

        # couleur des anomalies
        anom = d["anomalies_count"]
        if anom > 5:
            anom_str = color(f"{anom:>6}", RED)
        elif anom > 0:
            anom_str = color(f"{anom:>6}", YELLOW)
        else:
            anom_str = color(f"{anom:>6}", GREEN)

        # couleur du min_voltage si critique
        vmin = d["min_voltage"]
        if vmin < 207:
            vmin_str = color(f"{vmin:>8.2f}", RED)
        elif vmin < 215:
            vmin_str = color(f"{vmin:>8.2f}", YELLOW)
        else:
            vmin_str = f"{vmin:>8.2f}"

        print(f"  {d['district']:<22} {ztype_str} "
              f"{d['total_meters']:>10,} "
              f"{d['total_distributors']:>10,} "
              f"{d['total_energy_kwh']:>14,.2f} "
              f"{d['avg_voltage']:>8.2f} "
              f"{vmin_str} "
              f"{anom_str}")

    print("  " + "-" * 96)
    total_meters = sum(d["total_meters"] for d in sorted_dist)
    total_dists = sum(d["total_distributors"] for d in sorted_dist)
    total_anom = sum(d["anomalies_count"] for d in sorted_dist)
    print(f"  {color('TOTAL', BOLD):<22} {'':13} "
          f"{total_meters:>10,} {total_dists:>10,} "
          f"{color(f'{total_energy:>14,.2f}', YELLOW)} "
          f"{'':>8} {'':>8} "
          f"{color(f'{total_anom:>6}', YELLOW)}")
    print()


# ============================================================================
# HISTOGRAMME ASCII DE LA CONSOMMATION PAR QUARTIER
# ============================================================================


def show_consumption_histogram(by_topic: Dict[str, List[dict]]) -> None:
    concentrators = by_topic.get("tetouan.concentrators.aggregated", [])
    if not concentrators:
        return

    sorted_dist = sorted(concentrators, key=lambda x: x["total_energy_kwh"], reverse=True)
    max_energy = sorted_dist[0]["total_energy_kwh"]

    print(color("=" * 80, CYAN))
    print(color(" HISTOGRAMME : ENERGIE PAR QUARTIER (kWh) ".center(80), BOLD + CYAN))
    print(color("=" * 80, CYAN))

    bar_width = 50
    for d in sorted_dist:
        ratio = d["total_energy_kwh"] / max_energy
        bar_length = int(ratio * bar_width)

        # couleur selon le type de zone
        ztype = d["zone_type"]
        if ztype == "Industrial":
            bar_color = MAGENTA
        elif ztype == "Commercial":
            bar_color = YELLOW
        else:
            bar_color = GREEN

        bar = color("#" * bar_length, bar_color)
        empty = "." * (bar_width - bar_length)
        print(f"  {d['district']:<22} |{bar}{empty}| "
              f"{d['total_energy_kwh']:>10,.2f}")
    print()


# ============================================================================
# TOP 10 DISTRIBUTEURS LES PLUS CHARGES
# ============================================================================


def show_top_distributors(by_topic: Dict[str, List[dict]], n: int = 10) -> None:
    distributors = by_topic.get("tetouan.distributors.aggregated", [])
    if not distributors:
        return

    sorted_d = sorted(distributors, key=lambda x: x["total_energy_kwh"], reverse=True)[:n]

    print(color("=" * 90, CYAN))
    print(color(f" TOP {n} DISTRIBUTEURS LES PLUS CHARGES ".center(90), BOLD + CYAN))
    print(color("=" * 90, CYAN))

    header = f"  {'#':<3} {'Distributeur':<22} {'Quartier':<22} {'Energie kWh':>14} {'Compteurs':>10} {'Anom':>6}"
    print(color(header, BOLD))
    print("  " + "-" * 86)

    for i, d in enumerate(sorted_d, 1):
        anom = d["anomalies_count"]
        anom_str = color(f"{anom:>6}", RED if anom > 0 else GREEN)
        energy_str = color(f"{d['total_energy_kwh']:>14,.2f}", YELLOW)
        print(f"  {i:<3} {d['distributor_id']:<22} {d['district']:<22} "
              f"{energy_str} "
              f"{d['total_meters']:>10,} {anom_str}")
    print()


# ============================================================================
# ANOMALIES DE TENSION (compteurs avec V hors plage)
# ============================================================================


def show_voltage_anomalies(by_topic: Dict[str, List[dict]], n: int = 10) -> None:
    meters = by_topic.get("tetouan.meters.readings", [])
    if not meters:
        return

    # filtrer les anomalies (V < 207 ou V > 253)
    anomalies = [m for m in meters if m["voltage"] < 207 or m["voltage"] > 253]
    if not anomalies:
        print(color("  Aucune anomalie de tension detectee dans ce cycle.", GREEN))
        print()
        return

    # trier par ecart par rapport a 230V
    anomalies.sort(key=lambda m: abs(m["voltage"] - 230), reverse=True)
    top = anomalies[:n]

    print(color("=" * 100, CYAN))
    print(color(f" TOP {n} ANOMALIES DE TENSION (sur {len(anomalies)} detectees) ".center(100), BOLD + CYAN))
    print(color("=" * 100, CYAN))

    header = f"  {'#':<3} {'Compteur':<22} {'Quartier':<20} {'Distributeur':<22} {'Tension':>10} {'Type':>10}"
    print(color(header, BOLD))
    print("  " + "-" * 96)

    for i, m in enumerate(top, 1):
        v = m["voltage"]
        if v < 207:
            v_str = color(f"{v:>10.2f}", RED)
            type_str = color(f"{'SOUS-TENS':>10}", RED)
        else:
            v_str = color(f"{v:>10.2f}", RED)
            type_str = color(f"{'SUR-TENS':>10}", RED)

        print(f"  {i:<3} {m['meter_id']:<22} {m['district']:<20} "
              f"{m['distributor_id']:<22} {v_str} {type_str}")
    print()


# ============================================================================
# REPARTITION PAR ZONE TYPE
# ============================================================================


def show_zone_breakdown(by_topic: Dict[str, List[dict]]) -> None:
    concentrators = by_topic.get("tetouan.concentrators.aggregated", [])
    if not concentrators:
        return

    by_zone: Dict[str, Dict[str, float]] = defaultdict(lambda: {
        "energy": 0.0, "meters": 0, "districts": 0, "anomalies": 0
    })
    for d in concentrators:
        z = d["zone_type"]
        by_zone[z]["energy"] += d["total_energy_kwh"]
        by_zone[z]["meters"] += d["total_meters"]
        by_zone[z]["districts"] += 1
        by_zone[z]["anomalies"] += d["anomalies_count"]

    total_energy = sum(z["energy"] for z in by_zone.values())

    print(color("=" * 80, CYAN))
    print(color(" REPARTITION PAR TYPE DE ZONE ".center(80), BOLD + CYAN))
    print(color("=" * 80, CYAN))

    header = f"  {'Zone':<14} {'Quartiers':>10} {'Compteurs':>12} {'Energie kWh':>14} {'%':>7} {'Anom':>6}"
    print(color(header, BOLD))
    print("  " + "-" * 76)

    for zone, vals in sorted(by_zone.items(), key=lambda x: -x[1]["energy"]):
        pct = (vals["energy"] / total_energy * 100) if total_energy else 0
        if zone == "Industrial":
            zone_str = color(f"{zone:<14}", MAGENTA)
        elif zone == "Commercial":
            zone_str = color(f"{zone:<14}", YELLOW)
        else:
            zone_str = color(f"{zone:<14}", GREEN)
        print(f"  {zone_str} {int(vals['districts']):>10} "
              f"{int(vals['meters']):>12,} {vals['energy']:>14,.2f} "
              f"{pct:>6.1f}% {int(vals['anomalies']):>6}")
    print()


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visualisation console des resultats de simulation Tetouan."
    )
    parser.add_argument("input_file", type=str,
                        help="Fichier JSONL produit par main.py --output-file")
    parser.add_argument("--top", type=int, default=10,
                        help="Nombre d'elements dans les top-N (defaut: 10)")
    args = parser.parse_args()

    path = Path(args.input_file)
    print()
    print(color(f"  Chargement de {path}...", BLUE))
    by_topic = load_jsonl(path)
    print(color(f"  Charge : {sum(len(v) for v in by_topic.values()):,} messages", GREEN))
    print()

    show_global_stats(by_topic)
    show_zone_breakdown(by_topic)
    show_districts_table(by_topic)
    show_consumption_histogram(by_topic)
    show_top_distributors(by_topic, n=args.top)
    show_voltage_anomalies(by_topic, n=args.top)

    print(color("=" * 70, CYAN))
    print(color(" Fin de l'analyse ".center(70), BOLD + CYAN))
    print(color("=" * 70, CYAN))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
