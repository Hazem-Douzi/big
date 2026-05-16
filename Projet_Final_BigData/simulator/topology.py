"""
Topologie du reseau electrique de Tetouan.

Hierarchie :
    Centre de traitement
        |
        +-- 18 Concentrateurs (1 par quartier)
                |
                +-- 681 Distributeurs (postes de distribution MT/BT)
                        |
                        +-- 100 485 Smart Meters (compteurs)

Chaque quartier est associe a :
    - un nom
    - des coordonnees GPS (latitude, longitude)
    - un type de zone : Residential, Industrial ou Commercial
    - un nombre de distributeurs et de compteurs proportionnel a sa population
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List

from .config import RANDOM_SEED, TOTAL_DISTRIBUTORS, TOTAL_METERS

# ============================================================================
# DEFINITIONS DES QUARTIERS DE TETOUAN
#
# Chaque entree contient :
#   code               : identifiant court (3 lettres)
#   name               : nom complet du quartier
#   zone_type          : Residential | Industrial | Commercial
#   latitude/longitude : coordonnees GPS approximatives pour la cartographie
#   meters             : nombre de smart meters dans le quartier
#   distributors       : nombre de distributeurs (postes MT/BT)
#
# Les totaux : meters = 100 485, distributors = 681
# ============================================================================

DISTRICTS_RAW: List[Dict] = [
    {
        "code": "MED",
        "name": "Medina",
        "zone_type": "Commercial",
        "latitude": 35.5710,
        "longitude": -5.3733,
        "meters": 13_250,
        "distributors": 88,
    },
    {
        "code": "ENS",
        "name": "Ensanche",
        "zone_type": "Commercial",
        "latitude": 35.5734,
        "longitude": -5.3710,
        "meters": 10_830,
        "distributors": 72,
    },
    {
        "code": "MHN",
        "name": "Mhannech",
        "zone_type": "Residential",
        "latitude": 35.5800,
        "longitude": -5.3450,
        "meters": 8_825,
        "distributors": 59,
    },
    {
        "code": "TOU",
        "name": "Touabel",
        "zone_type": "Residential",
        "latitude": 35.5640,
        "longitude": -5.3720,
        "meters": 8_020,
        "distributors": 53,
    },
    {
        "code": "WLK",
        "name": "Wlad_Lkhames",
        "zone_type": "Residential",
        "latitude": 35.5780,
        "longitude": -5.3680,
        "meters": 7_065,
        "distributors": 47,
    },
    {
        "code": "BOU",
        "name": "Boujarah",
        "zone_type": "Residential",
        "latitude": 35.5660,
        "longitude": -5.3800,
        "meters": 6_310,
        "distributors": 42,
    },
    {
        "code": "DRS",
        "name": "Dersa",
        "zone_type": "Residential",
        "latitude": 35.5810,
        "longitude": -5.3760,
        "meters": 5_995,
        "distributors": 40,
    },
    {
        "code": "SNR",
        "name": "Sania_Ramel",
        "zone_type": "Residential",
        "latitude": 35.5938,
        "longitude": -5.3203,
        "meters": 5_815,
        "distributors": 39,
    },
    {
        "code": "COE",
        "name": "Coelma",
        "zone_type": "Residential",
        "latitude": 35.5660,
        "longitude": -5.3650,
        "meters": 5_030,
        "distributors": 34,
    },
    {
        "code": "TAM",
        "name": "Tamuda",
        "zone_type": "Residential",
        "latitude": 35.5840,
        "longitude": -5.3530,
        "meters": 4_505,
        "distributors": 30,
    },
    {
        "code": "ZAO",
        "name": "Zaouia",
        "zone_type": "Residential",
        "latitude": 35.5760,
        "longitude": -5.3850,
        "meters": 4_485,
        "distributors": 30,
    },
    {
        "code": "TTA",
        "name": "Touta",
        "zone_type": "Residential",
        "latitude": 35.5700,
        "longitude": -5.3900,
        "meters": 4_010,
        "distributors": 27,
    },
    {
        "code": "SAR",
        "name": "Saniat_Rmel",
        "zone_type": "Industrial",
        "latitude": 35.5942,
        "longitude": -5.3265,
        "meters": 3_890,
        "distributors": 26,
    },
    {
        "code": "KHD",
        "name": "Kheddadine",
        "zone_type": "Residential",
        "latitude": 35.5680,
        "longitude": -5.3680,
        "meters": 3_455,
        "distributors": 23,
    },
    {
        "code": "RML",
        "name": "Rmilete",
        "zone_type": "Residential",
        "latitude": 35.5870,
        "longitude": -5.3550,
        "meters": 2_905,
        "distributors": 19,
    },
    {
        "code": "AIN",
        "name": "Ain_Hamra",
        "zone_type": "Residential",
        "latitude": 35.5550,
        "longitude": -5.3750,
        "meters": 2_485,
        "distributors": 17,
    },
    {
        "code": "IBR",
        "name": "Iberia",
        "zone_type": "Residential",
        "latitude": 35.5750,
        "longitude": -5.3580,
        "meters": 1_960,
        "distributors": 13,
    },
    {
        "code": "ZIN",
        "name": "Zone_Industrielle",
        "zone_type": "Industrial",
        "latitude": 35.5400,
        "longitude": -5.3500,
        "meters": 1_650,
        "distributors": 22,
    },
]

# ============================================================================
# DATACLASSES — modeles immuables des entites du reseau
# ============================================================================


@dataclass
class Meter:
    """Compteur intelligent (smart meter) installe chez un client."""

    meter_id: str
    distributor_id: str
    concentrator_id: str
    district: str
    district_code: str
    zone_type: str
    latitude: float
    longitude: float


@dataclass
class Distributor:
    """Poste de distribution (transformateur MT/BT) regroupant plusieurs compteurs."""

    distributor_id: str
    concentrator_id: str
    district: str
    district_code: str
    zone_type: str
    latitude: float
    longitude: float
    meter_ids: List[str] = field(default_factory=list)


@dataclass
class Concentrator:
    """Concentrateur de quartier — un par quartier, agrege tous ses distributeurs."""

    concentrator_id: str
    district: str
    district_code: str
    zone_type: str
    latitude: float
    longitude: float
    distributor_ids: List[str] = field(default_factory=list)


@dataclass
class District:
    """Quartier de Tetouan."""

    code: str
    name: str
    zone_type: str
    latitude: float
    longitude: float
    concentrator: Concentrator
    distributors: List[Distributor]
    meters: List[Meter]


# ============================================================================
# CONSTRUCTION DE LA TOPOLOGIE
# ============================================================================


def _distribute_meters_to_distributors(num_meters: int, num_distributors: int) -> List[int]:
    """
    Repartit num_meters compteurs sur num_distributors distributeurs
    avec un peu de variabilite realiste (tous les distributeurs n'ont pas
    exactement la meme taille).

    Retourne une liste de longueur num_distributors donnant le nombre de
    compteurs alloues a chaque distributeur. La somme est exactement num_meters.
    """
    base = num_meters // num_distributors
    remainder = num_meters % num_distributors
    counts = [base] * num_distributors
    # repartir le reste sur les premiers distributeurs
    for i in range(remainder):
        counts[i] += 1
    # ajouter une variabilite +/- 15% en preservant la somme
    rng = random.Random(RANDOM_SEED + num_distributors)
    for _ in range(num_distributors):
        i = rng.randrange(num_distributors)
        j = rng.randrange(num_distributors)
        if i == j:
            continue
        # transferer jusqu'a 10 compteurs de j vers i si possible
        delta = rng.randint(0, min(10, max(0, counts[j] - 10)))
        counts[i] += delta
        counts[j] -= delta
    return counts


def build_topology() -> List[District]:
    """
    Construit la topologie complete du reseau Tetouan a partir de DISTRICTS_RAW.

    Pour chaque quartier :
      - cree 1 concentrateur (TET-<CODE>-CONC)
      - cree N distributeurs (TET-<CODE>-DIST-001, ...)
      - cree M compteurs (TET-<CODE>-MTR-00001, ...) repartis sur les distributeurs
      - rattache chaque compteur a son distributeur, et chaque distributeur au concentrateur

    Retourne la liste des 18 District completement initialises.
    """
    rng = random.Random(RANDOM_SEED)
    districts: List[District] = []

    for d in DISTRICTS_RAW:
        code = d["code"]
        concentrator_id = f"TET-{code}-CONC"

        concentrator = Concentrator(
            concentrator_id=concentrator_id,
            district=d["name"],
            district_code=code,
            zone_type=d["zone_type"],
            latitude=d["latitude"],
            longitude=d["longitude"],
        )

        # creer les distributeurs du quartier
        distributors: List[Distributor] = []
        for k in range(d["distributors"]):
            dist_id = f"TET-{code}-DIST-{k + 1:03d}"
            # legere dispersion GPS autour du centre du quartier (~500m)
            lat = d["latitude"] + rng.uniform(-0.005, 0.005)
            lon = d["longitude"] + rng.uniform(-0.005, 0.005)
            dist = Distributor(
                distributor_id=dist_id,
                concentrator_id=concentrator_id,
                district=d["name"],
                district_code=code,
                zone_type=d["zone_type"],
                latitude=lat,
                longitude=lon,
            )
            distributors.append(dist)
            concentrator.distributor_ids.append(dist_id)

        # repartir les compteurs sur les distributeurs
        meter_counts = _distribute_meters_to_distributors(d["meters"], d["distributors"])
        meters: List[Meter] = []
        meter_global_idx = 0
        for dist, n_meters in zip(distributors, meter_counts):
            for _ in range(n_meters):
                meter_global_idx += 1
                meter_id = f"TET-{code}-MTR-{meter_global_idx:05d}"
                # dispersion GPS autour du distributeur (~200m)
                lat = dist.latitude + rng.uniform(-0.002, 0.002)
                lon = dist.longitude + rng.uniform(-0.002, 0.002)
                meter = Meter(
                    meter_id=meter_id,
                    distributor_id=dist.distributor_id,
                    concentrator_id=concentrator_id,
                    district=d["name"],
                    district_code=code,
                    zone_type=d["zone_type"],
                    latitude=lat,
                    longitude=lon,
                )
                meters.append(meter)
                dist.meter_ids.append(meter_id)

        district = District(
            code=code,
            name=d["name"],
            zone_type=d["zone_type"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            concentrator=concentrator,
            distributors=distributors,
            meters=meters,
        )
        districts.append(district)

    return districts


def topology_summary(districts: List[District]) -> Dict[str, int]:
    """Renvoie un petit resume statistique de la topologie construite."""
    return {
        "districts": len(districts),
        "concentrators": len(districts),  # 1 par quartier
        "distributors": sum(len(d.distributors) for d in districts),
        "meters": sum(len(d.meters) for d in districts),
    }


# Sanity check : verifier que les totaux raw correspondent aux constantes
_total_meters = sum(d["meters"] for d in DISTRICTS_RAW)
_total_dist = sum(d["distributors"] for d in DISTRICTS_RAW)
assert _total_meters == TOTAL_METERS, (
    f"Total meters mismatch: {_total_meters} != {TOTAL_METERS}"
)
assert _total_dist == TOTAL_DISTRIBUTORS, (
    f"Total distributors mismatch: {_total_dist} != {TOTAL_DISTRIBUTORS}"
)
