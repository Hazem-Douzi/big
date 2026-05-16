"""
Simulateur de cycle complet — Tetouan Smart Grid.

Architecture en cascade synchronisee (15 + 1 + 1 + 13 = 30 minutes) :

  PHASE 1 [00:00 -> 00:15]  Compteurs -> Distributeurs
      Chaque compteur envoie sa mesure de maniere etalee sur 15 min
      grace a un offset deterministe (hash du meter_id).
      Topic : tetouan.meters.readings

  PHASE 2 [00:15 -> 00:16]  Distributeurs -> Concentrateurs
      Chaque distributeur agrege les mesures de ses compteurs et publie
      un message recapitulatif (energie totale, tension moyenne, etc.).
      Topic : tetouan.distributors.aggregated

  PHASE 3 [00:16 -> 00:17]  Concentrateurs -> Centre de traitement
      Chaque concentrateur agrege les messages de ses distributeurs et
      publie un message au niveau du quartier.
      Topic : tetouan.concentrators.aggregated

  PHASE 4 [00:17 -> 00:30]  Idle / monitoring / preparation cycle suivant
      Un message global de fin de cycle est publie au centre.
      Topic : tetouan.center.ingest

Le simulateur peut tourner :
  - en temps reel (1 cycle = 30 minutes)
  - en mode demo accelere (1 cycle = ~30 secondes via TIME_ACCELERATION=60)
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .kafka_client import BaseKafkaClient, get_client, to_json_str
from .patterns import (
    MeterReading,
    aggregate_concentrator,
    aggregate_distributor,
    generate_meter_reading,
)
from .topology import District, build_topology, topology_summary

logger = logging.getLogger(__name__)


# ============================================================================
# UTILITAIRES
# ============================================================================


def _meter_offset_seconds(meter_id: str, window_seconds: int) -> int:
    """
    Calcule un offset deterministe (en secondes) dans la fenetre [0, window_seconds[
    a partir du meter_id. Permet d'etaler les ~100k compteurs sur 15 min
    sans tous declencher en meme temps (jitter / staggered scheduling).
    """
    h = hashlib.md5(meter_id.encode("utf-8")).hexdigest()
    return int(h, 16) % window_seconds


def _build_meter_buckets(
    districts: List[District], num_buckets: int, window_seconds: int
) -> List[List]:
    """
    Pre-calcule les buckets temporels pour la phase 1.

    On decoupe la fenetre de 15 min en `num_buckets` intervalles. Chaque
    compteur est range dans le bucket correspondant a son offset. Cela
    evite de scanner les 100k compteurs a chaque tick.
    """
    buckets: List[List] = [[] for _ in range(num_buckets)]
    bucket_size = window_seconds // num_buckets
    for d in districts:
        for meter in d.meters:
            offset = _meter_offset_seconds(meter.meter_id, window_seconds)
            idx = min(offset // bucket_size, num_buckets - 1)
            buckets[idx].append(meter)
    return buckets


# ============================================================================
# SIMULATEUR
# ============================================================================


class TetouanSimulator:
    """
    Orchestre le cycle complet :
      Compteurs -> Distributeurs -> Concentrateurs -> Centre.
    """

    def __init__(
        self,
        client: Optional[BaseKafkaClient] = None,
        seed: int = config.RANDOM_SEED,
        start_time: Optional[datetime] = None,
        # nombre de buckets temporels pour etaler les compteurs (defaut: 15
        # buckets de 1 min). Plus le nombre est eleve, plus l'etalement est
        # fin (mais plus de ticks a executer).
        num_buckets: int = 15,
        # fichier optionnel qui recoit l'historique des fenetres 15 min :
        # une ligne JSON par (quartier x fenetre), idealement consomme par
        # le dashboard pour afficher les tendances.
        history_file: Optional[str] = None,
        # nombre maximal de fenetres conservees dans le fichier d'historique
        # (rolling window). 0 = illimite.
        history_max_windows: int = 96,  # 96 fenetres de 15 min = 24h
    ):
        self.client = client if client is not None else get_client()
        self.rng = random.Random(seed)
        # heure simulee de demarrage (par defaut: maintenant)
        self.simulated_clock: datetime = start_time or datetime.utcnow().replace(
            second=0, microsecond=0
        )
        self.num_buckets = num_buckets
        self.cycle_count = 0

        # --- fichier d'historique des fenetres (pour le dashboard) ---------
        self._history_path: Optional[Path] = None
        self._history_max_windows = history_max_windows
        if history_file:
            self._history_path = Path(history_file)
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Historique des fenetres ecrit dans : %s", self._history_path)

        # construction de la topologie
        logger.info("Construction de la topologie Tetouan...")
        self.districts: List[District] = build_topology()
        summary = topology_summary(self.districts)
        logger.info(
            "Topologie : %d quartiers / %d concentrateurs / %d distributeurs / %d compteurs",
            summary["districts"],
            summary["concentrators"],
            summary["distributors"],
            summary["meters"],
        )

        # index pratiques
        self._distributor_lookup = {
            dist.distributor_id: dist
            for d in self.districts
            for dist in d.distributors
        }
        self._concentrator_lookup = {
            d.concentrator.concentrator_id: d.concentrator
            for d in self.districts
        }

        # pre-calcul des buckets pour la phase 1
        window_seconds = config.PHASE_METERS_TO_DISTRIBUTORS_MIN * 60
        self._meter_buckets = _build_meter_buckets(
            self.districts, num_buckets, window_seconds
        )
        logger.info(
            "Compteurs repartis en %d buckets temporels (fenetre %d min)",
            num_buckets,
            config.PHASE_METERS_TO_DISTRIBUTORS_MIN,
        )

    # ------------------------------------------------------------------ utils
    def _sleep(self, simulated_minutes: float) -> None:
        """Endort le thread en respectant l'acceleration eventuelle."""
        time.sleep(config.real_seconds(simulated_minutes))

    def _advance_clock(self, minutes: float) -> None:
        self.simulated_clock += timedelta(minutes=minutes)

    # ============================================================== phase 1
    def _phase1_meters_to_distributors(self) -> Dict[str, List[MeterReading]]:
        """
        PHASE 1 : compteurs -> distributeurs (etalement sur 15 min).

        Renvoie un dict { distributor_id : [MeterReading, ...] } qui sera
        utilise par la phase 2 pour l'agregation.
        """
        cycle_start = self.simulated_clock
        readings_by_distributor: Dict[str, List[MeterReading]] = defaultdict(list)
        total_sent = 0

        logger.info(
            "[PHASE 1] %s -> compteurs envoient au distributeur (etale sur %d min)",
            cycle_start.isoformat(),
            config.PHASE_METERS_TO_DISTRIBUTORS_MIN,
        )

        bucket_minutes = config.PHASE_METERS_TO_DISTRIBUTORS_MIN / self.num_buckets

        for bucket_idx, meters in enumerate(self._meter_buckets):
            # timestamp simule du bucket
            bucket_time = cycle_start + timedelta(minutes=bucket_idx * bucket_minutes)
            for meter in meters:
                reading = generate_meter_reading(meter, bucket_time, self.rng)
                self.client.send(
                    config.TOPIC_METER_READINGS,
                    reading,
                    key=meter.meter_id,
                )
                readings_by_distributor[meter.distributor_id].append(reading)
                total_sent += 1

            # progression visible toutes les 3 buckets pour ne pas spammer
            if bucket_idx % 3 == 0 or bucket_idx == self.num_buckets - 1:
                logger.info(
                    "  bucket %2d/%d  | %5d compteurs ce bucket | %d total",
                    bucket_idx + 1,
                    self.num_buckets,
                    len(meters),
                    total_sent,
                )

            # attendre la duree du bucket en temps simule
            self._sleep(bucket_minutes)

        # avancer l'horloge a la fin de la phase 1
        self.simulated_clock = cycle_start + timedelta(
            minutes=config.PHASE_METERS_TO_DISTRIBUTORS_MIN
        )
        logger.info(
            "[PHASE 1] termine : %d mesures publiees sur '%s'",
            total_sent,
            config.TOPIC_METER_READINGS,
        )
        return readings_by_distributor

    # ============================================================== phase 2
    def _phase2_distributors_to_concentrators(
        self,
        readings_by_distributor: Dict[str, List[MeterReading]],
        window_start: datetime,
        window_end: datetime,
    ) -> Dict[str, List[dict]]:
        """
        PHASE 2 : distributeurs -> concentrateurs (rafale 1 min).

        Chaque distributeur agrege ses compteurs sur la fenetre 15 min
        [window_start, window_end] et publie un message.
        """
        ws = window_start.isoformat()
        we = window_end.isoformat()
        logger.info(
            "[PHASE 2] %s -> distributeurs agregent fenetre [%s -> %s]",
            self.simulated_clock.isoformat(), ws, we,
        )

        aggregations_by_concentrator: Dict[str, List[dict]] = defaultdict(list)
        total_distributors = 0

        # parcourir TOUS les distributeurs (meme ceux sans readings dans ce
        # cycle, par robustesse)
        for distributor_id, distributor in self._distributor_lookup.items():
            readings = readings_by_distributor.get(distributor_id, [])
            if not readings:
                continue  # pas de mesures dans ce cycle
            agg = aggregate_distributor(readings, window_start=ws, window_end=we)
            self.client.send(
                config.TOPIC_DISTRIBUTOR_AGG,
                agg,
                key=distributor_id,
            )
            aggregations_by_concentrator[distributor.concentrator_id].append(agg)
            total_distributors += 1

        # phase courte : 1 min simulee de transmission
        self._sleep(config.PHASE_DISTRIBUTORS_TO_CONCENTRATORS_MIN)
        self._advance_clock(config.PHASE_DISTRIBUTORS_TO_CONCENTRATORS_MIN)

        logger.info(
            "[PHASE 2] termine : %d agregations distributeur publiees sur '%s'",
            total_distributors,
            config.TOPIC_DISTRIBUTOR_AGG,
        )
        return aggregations_by_concentrator

    # ============================================================== phase 3
    def _phase3_concentrators_to_center(
        self,
        aggregations_by_concentrator: Dict[str, List[dict]],
        window_start: datetime,
        window_end: datetime,
    ) -> List[dict]:
        """
        PHASE 3 : concentrateurs -> centre de traitement (rafale 1 min).

        Chaque concentrateur agrege les messages de ses distributeurs et
        publie un message au niveau du quartier, conservant les bornes de
        fenetre 15 min [window_start, window_end].
        """
        ws = window_start.isoformat()
        we = window_end.isoformat()
        logger.info(
            "[PHASE 3] %s -> concentrateurs agregent fenetre [%s -> %s]",
            self.simulated_clock.isoformat(), ws, we,
        )

        district_aggs: List[dict] = []
        for concentrator_id, dist_aggs in aggregations_by_concentrator.items():
            agg = aggregate_concentrator(dist_aggs, window_start=ws, window_end=we)
            self.client.send(
                config.TOPIC_CONCENTRATOR_AGG,
                agg,
                key=concentrator_id,
            )
            district_aggs.append(agg)

        self._sleep(config.PHASE_CONCENTRATORS_TO_CENTER_MIN)
        self._advance_clock(config.PHASE_CONCENTRATORS_TO_CENTER_MIN)

        logger.info(
            "[PHASE 3] termine : %d agregations concentrateur publiees sur '%s'",
            len(district_aggs),
            config.TOPIC_CONCENTRATOR_AGG,
        )
        return district_aggs

    # ============================================================== phase 4
    def _phase4_idle_and_summary(
        self,
        district_aggs: List[dict],
        cycle_start: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """
        PHASE 4 : idle (13 min) + publication d'un recap global du cycle
        et ecriture de l'historique des fenetres pour le dashboard.
        """
        ws = window_start.isoformat()
        we = window_end.isoformat()

        # construire un message recap du cycle pour le centre
        total_energy = sum(a.get("total_energy_kwh", 0) for a in district_aggs)
        total_meters = sum(a.get("total_meters", 0) for a in district_aggs)
        total_anomalies = sum(a.get("anomalies_count", 0) for a in district_aggs)

        cycle_recap = {
            "cycle_id": self.cycle_count,
            "cycle_start": cycle_start.isoformat(),
            "cycle_end": self.simulated_clock.isoformat(),
            # ----- fenetrage 15 min ------------------------------------
            "window_start": ws,
            "window_end":   we,
            "window_duration_min": 15,
            # ----- agregations globales --------------------------------
            "districts_reported": len(district_aggs),
            "total_meters": total_meters,
            "total_energy_kwh": round(total_energy, 4),
            "anomalies_count": total_anomalies,
            "districts": district_aggs,
        }

        self.client.send(
            config.TOPIC_CENTER_INGEST,
            cycle_recap,
            key=f"cycle-{self.cycle_count}",
        )
        self.client.flush()

        # ecrire l'historique des fenetres pour le dashboard
        self._write_window_history(district_aggs, cycle_recap)

        logger.info(
            "[PHASE 4] %s -> recap fenetre [%s -> %s] publie "
            "(energie=%.2f kWh, anomalies=%d) | idle %d min",
            self.simulated_clock.isoformat(),
            ws, we,
            total_energy,
            total_anomalies,
            config.PHASE_IDLE_MIN,
        )

        self._sleep(config.PHASE_IDLE_MIN)
        self._advance_clock(config.PHASE_IDLE_MIN)

    # ============================================================== history
    def _write_window_history(
        self, district_aggs: List[dict], cycle_recap: dict
    ) -> None:
        """
        Ecrit dans le fichier d'historique :
          - 1 ligne JSON par quartier (kind=district) avec les agregations
            de la fenetre 15 min courante
          - 1 ligne JSON globale (kind=cycle) avec le recap du cycle

        Si self._history_max_windows > 0, on tronque le fichier pour ne
        garder que les N dernieres fenetres (rolling window) — pratique
        pour ne pas faire grossir indefiniment le fichier en mode
        --cycles 0 (boucle infinie).
        """
        if self._history_path is None:
            return

        # 1) appendre les nouvelles lignes
        with self._history_path.open("a", encoding="utf-8") as f:
            for d in district_aggs:
                f.write(to_json_str({"kind": "district", **d}) + "\n")
            f.write(to_json_str({"kind": "cycle", **{
                k: v for k, v in cycle_recap.items() if k != "districts"
            }}) + "\n")

        # 2) tronquer le fichier si on depasse la limite
        if self._history_max_windows > 0:
            self._truncate_history_file()

    def _truncate_history_file(self) -> None:
        """
        Garde uniquement les `history_max_windows` dernieres fenetres (cycles)
        dans le fichier d'historique. Decoupe les lignes en blocs separes
        par les marqueurs kind=cycle.
        """
        if self._history_path is None or not self._history_path.exists():
            return

        try:
            lines = self._history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        # decouper en blocs (1 bloc = toutes les lignes jusqu'au prochain "cycle")
        blocks: List[List[str]] = []
        current: List[str] = []
        for ln in lines:
            current.append(ln)
            try:
                obj = json.loads(ln)
                if obj.get("kind") == "cycle":
                    blocks.append(current)
                    current = []
            except (json.JSONDecodeError, ValueError):
                continue
        if current:
            blocks.append(current)

        if len(blocks) <= self._history_max_windows:
            return

        # garder les N dernieres fenetres
        kept = blocks[-self._history_max_windows:]
        self._history_path.write_text(
            "\n".join(ln for block in kept for ln in block) + "\n",
            encoding="utf-8",
        )

    # ================================================================ cycle
    def run_cycle(self) -> None:
        """
        Execute un cycle complet de 30 minutes simulees.

        La fenetre 15 min de Spark Structured Streaming est defini par :
            window_start = cycle_start
            window_end   = cycle_start + 15 minutes
        ce qui correspond exactement a la phase 1 de collecte. Toutes les
        agregations (distributeur, concentrateur, recap centre) portent
        ces bornes pour materialiser le fenetrage.
        """
        self.cycle_count += 1
        cycle_start = self.simulated_clock
        # fenetre 15 min = phase 1 (collecte des compteurs)
        window_start = cycle_start
        window_end = cycle_start + timedelta(
            minutes=config.PHASE_METERS_TO_DISTRIBUTORS_MIN
        )

        logger.info(
            "================ CYCLE %d demarre — fenetre 15 min : [%s -> %s] ================",
            self.cycle_count,
            window_start.isoformat(),
            window_end.isoformat(),
        )

        readings_by_distributor = self._phase1_meters_to_distributors()
        aggs_by_concentrator = self._phase2_distributors_to_concentrators(
            readings_by_distributor, window_start, window_end,
        )
        district_aggs = self._phase3_concentrators_to_center(
            aggs_by_concentrator, window_start, window_end,
        )
        self._phase4_idle_and_summary(
            district_aggs, cycle_start, window_start, window_end,
        )

        logger.info(
            "================ CYCLE %d termine a %s ================",
            self.cycle_count, self.simulated_clock.isoformat(),
        )

    def run(self, num_cycles: Optional[int] = None) -> None:
        """
        Lance la simulation.

        :param num_cycles: nombre de cycles a executer. None = boucle infinie.
        """
        try:
            if num_cycles is None:
                while True:
                    self.run_cycle()
            else:
                for _ in range(num_cycles):
                    self.run_cycle()
        except KeyboardInterrupt:
            logger.warning("Interruption clavier — arret propre du simulateur")
        finally:
            self.client.flush()
            self.client.close()
