"""
Configuration globale du systeme de simulation Big Data Tetouan.

Constantes pour :
- Topologie (nombre de capteurs, distributeurs, concentrateurs)
- Cycles temporels (collecte 15 min + agregations + idle)
- Topics Kafka
- Mode demo accelere
"""
from __future__ import annotations

import os

# ============================================================================
# TOPOLOGIE GLOBALE
# ============================================================================

TOTAL_METERS = 100_485            # nombre total de smart meters dans Tetouan
TOTAL_DISTRIBUTORS = 681          # nombre total de distributeurs (transformateurs MT/BT)
TOTAL_DISTRICTS = 18              # nombre total de quartiers
# 1 concentrateur par quartier (= 18 concentrateurs)

# ============================================================================
# CYCLE TEMPOREL (en secondes)
# Architecture cascade pipeline 15+1+1+13 = 30 minutes
# ============================================================================

# Duree reelle d'un cycle complet (en minutes)
CYCLE_DURATION_MIN = 30

# Phase 1 : compteurs -> distributeurs (collecte progressive)
PHASE_METERS_TO_DISTRIBUTORS_MIN = 15

# Phase 2 : distributeurs -> concentrateurs (rafale)
PHASE_DISTRIBUTORS_TO_CONCENTRATORS_MIN = 1

# Phase 3 : concentrateurs -> centre de traitement (rafale)
PHASE_CONCENTRATORS_TO_CENTER_MIN = 1

# Phase 4 : idle / monitoring
PHASE_IDLE_MIN = (
    CYCLE_DURATION_MIN
    - PHASE_METERS_TO_DISTRIBUTORS_MIN
    - PHASE_DISTRIBUTORS_TO_CONCENTRATORS_MIN
    - PHASE_CONCENTRATORS_TO_CENTER_MIN
)

# ============================================================================
# MODE DEMO ACCELERE
# Ratio : 1 seconde de demo = X minutes simulees
# Permet de voir plusieurs cycles complets pendant une presentation
# ============================================================================

# Quand True, le temps simule est accelere par TIME_ACCELERATION
DEMO_MODE = bool(int(os.getenv("DEMO_MODE", "1")))

# 60 = 1 sec reelle correspond a 1 minute simulee
# Donc un cycle de 30 min simules dure 30 sec en demo
TIME_ACCELERATION = int(os.getenv("TIME_ACCELERATION", "60"))


def real_seconds(simulated_minutes: float) -> float:
    """Convertit une duree simulee (minutes) en secondes reelles d'attente."""
    if DEMO_MODE:
        return (simulated_minutes * 60) / TIME_ACCELERATION
    return simulated_minutes * 60


# ============================================================================
# KAFKA
# ============================================================================

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_ENABLED = bool(int(os.getenv("KAFKA_ENABLED", "0")))  # 0 = mock, 1 = vrai broker

# Noms des topics par niveau
TOPIC_METER_READINGS = "tetouan.meters.readings"           # niveau 1 (raw)
TOPIC_DISTRIBUTOR_AGG = "tetouan.distributors.aggregated"  # niveau 2
TOPIC_CONCENTRATOR_AGG = "tetouan.concentrators.aggregated"  # niveau 3
TOPIC_CENTER_INGEST = "tetouan.center.ingest"              # niveau 4 (final)

# ============================================================================
# REPRODUCTIBILITE
# ============================================================================

RANDOM_SEED = 42

# ============================================================================
# LOGS
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
