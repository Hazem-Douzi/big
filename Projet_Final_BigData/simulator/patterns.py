"""
Profils de consommation electrique par type de zone.

Les profils renvoient un coefficient multiplicateur (entre ~0.2 et ~1.6) en
fonction de l'heure de la journee. Ce coefficient est applique a la
consommation de base d'un compteur pour generer une mesure realiste.

Profils implementes :
  - Residential : pic le soir (19h-22h), creux la nuit (2h-5h)
  - Industrial  : pic en journee (8h-17h), bas la nuit
  - Commercial  : double pic (10h-13h et 18h-22h)

Sans variable de temperature (volontairement ecartee).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

# ============================================================================
# CONFIG DES PROFILS
# ============================================================================

# Consommation de base par type de zone (en kWh par fenetre de 15 min)
# Ces valeurs sont "moyennes" et seront modulees par le coefficient horaire.
BASE_CONSUMPTION_KWH = {
    "Residential": 0.45,    # ~1.8 kWh/h en moyenne
    "Commercial":  1.20,    # commerces -> conso plus elevee
    "Industrial":  3.50,    # usines -> tres forte consommation
}

# Tension nominale (en V) et plage normale autour
NOMINAL_VOLTAGE = 230.0
VOLTAGE_TOLERANCE = 5.0  # +/- 5 V en operation normale

# Frequence nominale (Hz)
NOMINAL_FREQUENCY = 50.0


# ============================================================================
# COEFFICIENTS HORAIRES PAR PROFIL
# ============================================================================


def _residential_coefficient(hour: float) -> float:
    """
    Profil residentiel :
      - creux profond la nuit (2h-5h)        ~ 0.25
      - leger pic du matin (7h-9h)           ~ 0.90
      - journee moderee (9h-18h)             ~ 0.55
      - PIC du soir (19h-22h)                ~ 1.55
      - retombee progressive (22h-2h)
    Modelise via une combinaison de gaussiennes.
    """
    morning = 0.85 * math.exp(-((hour - 8.0) ** 2) / (2 * 1.2 ** 2))
    evening = 1.45 * math.exp(-((hour - 20.5) ** 2) / (2 * 1.5 ** 2))
    base = 0.30
    return base + morning + evening


def _industrial_coefficient(hour: float) -> float:
    """
    Profil industriel :
      - tres bas la nuit (22h-6h)            ~ 0.20
      - montee rapide a 7h-8h
      - PLATEAU de production (8h-17h)       ~ 1.40
      - descente lente (17h-21h)
    Modelise via une fonction sigmoid en montee + sigmoid en descente.
    """
    rise = 1.0 / (1.0 + math.exp(-(hour - 7.5) * 1.6))   # monte vers 8h
    fall = 1.0 / (1.0 + math.exp((hour - 18.0) * 1.4))   # descend apres 18h
    plateau = rise * fall  # entre 0 et 1
    return 0.20 + 1.20 * plateau


def _commercial_coefficient(hour: float) -> float:
    """
    Profil commercial (souks, centres commerciaux, boutiques) :
      - bas la nuit (0h-8h)                  ~ 0.30
      - 1er pic en milieu de journee         ~ 1.20  (10h-13h)
      - creux entre les pics                 ~ 0.85  (14h-17h)
      - 2eme pic le soir                     ~ 1.45  (19h-22h)
      - retombee apres 22h
    """
    midday = 0.95 * math.exp(-((hour - 11.5) ** 2) / (2 * 1.4 ** 2))
    evening = 1.20 * math.exp(-((hour - 20.0) ** 2) / (2 * 1.4 ** 2))
    base = 0.30
    return base + midday + evening


# ============================================================================
# API PUBLIQUE
# ============================================================================


def hourly_coefficient(zone_type: str, hour: float) -> float:
    """
    Renvoie le coefficient multiplicateur pour un type de zone et une heure
    decimale (ex: 14.25 = 14h15).
    """
    if zone_type == "Residential":
        return _residential_coefficient(hour)
    if zone_type == "Industrial":
        return _industrial_coefficient(hour)
    if zone_type == "Commercial":
        return _commercial_coefficient(hour)
    # fallback : profil residentiel par defaut
    return _residential_coefficient(hour)


@dataclass
class MeterReading:
    """Une mesure unitaire envoyee par un compteur (niveau 1)."""

    meter_id: str
    distributor_id: str
    concentrator_id: str
    district: str
    district_code: str
    zone_type: str
    timestamp: str             # ISO 8601
    energy_consumption: float  # kWh sur la fenetre de 15 min
    voltage: float             # V
    current: float             # A
    latitude: float
    longitude: float


def generate_meter_reading(
    meter,                # type: simulator.topology.Meter
    timestamp: datetime,
    rng: random.Random,
) -> MeterReading:
    """
    Genere une mesure realiste pour un compteur a un instant donne.

    Le calcul tient compte :
      - du type de zone (profil horaire)
      - de l'heure (coefficient)
      - du week-end (residentiel +10%, industriel -40%)
      - d'un bruit aleatoire (+/- 15%)
      - d'anomalies rares de tension (~0.2%)
    """
    hour = timestamp.hour + timestamp.minute / 60.0
    is_weekend = timestamp.weekday() >= 5  # samedi/dimanche

    base = BASE_CONSUMPTION_KWH.get(meter.zone_type, 0.45)
    coef = hourly_coefficient(meter.zone_type, hour)

    # ajustement week-end
    if is_weekend:
        if meter.zone_type == "Industrial":
            coef *= 0.45  # usines tournent au ralenti
        elif meter.zone_type == "Residential":
            coef *= 1.10  # plus de monde a la maison
        else:  # Commercial
            coef *= 1.05

    # bruit individuel +/- 15%
    noise = rng.uniform(0.85, 1.15)
    energy_kwh = base * coef * noise
    energy_kwh = max(0.01, energy_kwh)  # jamais zero strict

    # tension : nominale + petit bruit, anomalie occasionnelle
    voltage = NOMINAL_VOLTAGE + rng.uniform(-VOLTAGE_TOLERANCE, VOLTAGE_TOLERANCE)
    if rng.random() < 0.002:  # 0.2% : sous-tension ou sur-tension
        voltage += rng.choice([-25.0, 18.0])

    # courant : I = P / U avec P en W (energie/15min -> puissance moyenne)
    # P_W = energy_kwh * 1000 / 0.25h = energy_kwh * 4000
    power_w = energy_kwh * 4000.0
    current = power_w / max(voltage, 1.0)

    return MeterReading(
        meter_id=meter.meter_id,
        distributor_id=meter.distributor_id,
        concentrator_id=meter.concentrator_id,
        district=meter.district,
        district_code=meter.district_code,
        zone_type=meter.zone_type,
        timestamp=timestamp.isoformat(),
        energy_consumption=round(energy_kwh, 4),
        voltage=round(voltage, 2),
        current=round(current, 3),
        latitude=meter.latitude,
        longitude=meter.longitude,
    )


def aggregate_distributor(
    readings,
    window_start: str = None,
    window_end: str = None,
) -> dict:
    """
    Agrege une liste de MeterReading appartenant a un meme distributeur sur une
    fenetre temporelle de 15 min (Tumbling Window de Spark Structured Streaming).

    :param readings: liste de MeterReading collectees pendant la fenetre
    :param window_start: ISO 8601 du debut de la fenetre (ex: 2026-05-16T14:00:00)
    :param window_end:   ISO 8601 de la fin de la fenetre (ex: 2026-05-16T14:15:00)

    Renvoie un dict pret a etre publie sur le topic distributeur (niveau 2)
    avec window_start / window_end materialisant le fenetrage 15 min.
    """
    n = len(readings)
    if n == 0:
        return {}

    total_energy = sum(r.energy_consumption for r in readings)
    avg_voltage = sum(r.voltage for r in readings) / n
    avg_current = sum(r.current for r in readings) / n
    voltages = [r.voltage for r in readings]
    min_voltage = min(voltages)
    max_voltage = max(voltages)
    anomalies = sum(1 for r in readings if r.voltage < 207 or r.voltage > 253)

    first = readings[0]
    return {
        "distributor_id": first.distributor_id,
        "concentrator_id": first.concentrator_id,
        "district": first.district,
        "district_code": first.district_code,
        "zone_type": first.zone_type,
        # ----- fenetrage 15 min ------------------------------------------
        "window_start": window_start or first.timestamp,
        "window_end":   window_end,
        "window_duration_min": 15,
        # ----- compatibilite : ancien champ timestamp ---------------------
        "timestamp": window_start or first.timestamp,
        # ----- agregations sur la fenetre ---------------------------------
        "total_meters": n,
        "total_energy_kwh": round(total_energy, 4),
        "avg_voltage": round(avg_voltage, 2),
        "min_voltage": round(min_voltage, 2),
        "max_voltage": round(max_voltage, 2),
        "avg_current": round(avg_current, 3),
        "anomalies_count": anomalies,
    }


def aggregate_concentrator(
    distributor_aggs,
    window_start: str = None,
    window_end: str = None,
) -> dict:
    """
    Agrege une liste de dicts produits par aggregate_distributor (meme quartier),
    pour une meme fenetre temporelle de 15 min.

    :param distributor_aggs: liste d'agregations de distributeurs du quartier
    :param window_start: debut de la fenetre 15 min
    :param window_end:   fin de la fenetre 15 min

    Renvoie un dict pret a etre publie sur le topic concentrateur (niveau 3).
    """
    n = len(distributor_aggs)
    if n == 0:
        return {}

    total_energy = sum(a["total_energy_kwh"] for a in distributor_aggs)
    total_meters = sum(a["total_meters"] for a in distributor_aggs)
    # moyenne ponderee de la tension par nombre de meters
    weighted_v = sum(a["avg_voltage"] * a["total_meters"] for a in distributor_aggs)
    avg_voltage = weighted_v / total_meters if total_meters else 0.0
    min_voltage = min(a["min_voltage"] for a in distributor_aggs)
    max_voltage = max(a["max_voltage"] for a in distributor_aggs)
    anomalies = sum(a["anomalies_count"] for a in distributor_aggs)

    first = distributor_aggs[0]
    # heriter de la fenetre des distributeurs si non fournie
    inferred_start = window_start or first.get("window_start") or first.get("timestamp")
    inferred_end = window_end or first.get("window_end")

    return {
        "concentrator_id": first["concentrator_id"],
        "district": first["district"],
        "district_code": first["district_code"],
        "zone_type": first["zone_type"],
        # ----- fenetrage 15 min ------------------------------------------
        "window_start": inferred_start,
        "window_end":   inferred_end,
        "window_duration_min": 15,
        # ----- compatibilite ---------------------------------------------
        "timestamp": inferred_start,
        # ----- agregations sur la fenetre ---------------------------------
        "total_distributors": n,
        "total_meters": total_meters,
        "total_energy_kwh": round(total_energy, 4),
        "avg_voltage": round(avg_voltage, 2),
        "min_voltage": round(min_voltage, 2),
        "max_voltage": round(max_voltage, 2),
        "anomalies_count": anomalies,
    }


def voltage_range_for_normal() -> Tuple[float, float]:
    """Plage normale de tension (utile pour tests/dashboard)."""
    return (NOMINAL_VOLTAGE - VOLTAGE_TOLERANCE, NOMINAL_VOLTAGE + VOLTAGE_TOLERANCE)
