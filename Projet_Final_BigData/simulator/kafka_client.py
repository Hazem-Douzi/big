"""
Wrapper Kafka pour le simulateur.

Deux implementations interchangeables :
  - KafkaClient   : producer reel base sur kafka-python
  - MockKafkaClient : ecrit les messages sur stdout / fichier (tests sans broker)

Le choix est fait via la variable de configuration KAFKA_ENABLED dans config.py.
On expose une fabrique get_client() qui renvoie l'implementation appropriee.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import config

logger = logging.getLogger(__name__)


# ============================================================================
# SERIALISATION
# ============================================================================


def _default_encoder(obj: Any) -> Any:
    """Encoder JSON tolerant pour datetime et dataclasses."""
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def to_json_bytes(payload: Any) -> bytes:
    """Serialise un payload Python en bytes UTF-8 JSON."""
    return json.dumps(payload, default=_default_encoder, ensure_ascii=False).encode("utf-8")


def to_json_str(payload: Any) -> str:
    """Serialise un payload en string JSON."""
    return json.dumps(payload, default=_default_encoder, ensure_ascii=False)


# ============================================================================
# INTERFACE COMMUNE
# ============================================================================


class BaseKafkaClient:
    """Interface minimale d'un producer Kafka."""

    def send(self, topic: str, payload: Any, key: Optional[str] = None) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.flush()
        finally:
            self.close()


# ============================================================================
# IMPLEMENTATION KAFKA REEL (kafka-python)
# ============================================================================


class KafkaClient(BaseKafkaClient):
    """Producer Kafka reel — necessite que le paquet kafka-python soit installe."""

    def __init__(self, bootstrap_servers: str = config.KAFKA_BOOTSTRAP_SERVERS):
        try:
            from kafka import KafkaProducer  # import paresseux
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "kafka-python n'est pas installe. "
                "Installez-le avec : pip install kafka-python"
            ) from e

        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=to_json_bytes,
            key_serializer=lambda k: None if k is None else str(k).encode("utf-8"),
            linger_ms=20,           # petit batching
            compression_type="gzip",  # compresse les messages
            acks=1,
        )
        logger.info("KafkaClient initialise (bootstrap=%s)", bootstrap_servers)

    def send(self, topic: str, payload: Any, key: Optional[str] = None) -> None:
        self._producer.send(topic, value=payload, key=key)

    def flush(self) -> None:
        self._producer.flush()

    def close(self) -> None:
        self._producer.close()


# ============================================================================
# IMPLEMENTATION MOCK (sans broker — pour tests / demo)
# ============================================================================


class MockKafkaClient(BaseKafkaClient):
    """
    Producer factice qui ecrit les messages sur stdout ou un fichier JSON-lines.
    Utile pour developper et tester le simulateur sans avoir Kafka installe.
    """

    def __init__(
        self,
        output_file: Optional[str] = None,
        verbose_topics: Optional[set] = None,
    ):
        self._counts: dict = {}
        self._output_path: Optional[Path] = None
        self._fh = None
        # par defaut, on n'affiche en clair sur stdout que les niveaux 2/3/4
        # (le niveau 1 = ~100k messages par cycle, trop verbeux)
        self.verbose_topics = verbose_topics or {
            config.TOPIC_DISTRIBUTOR_AGG,
            config.TOPIC_CONCENTRATOR_AGG,
            config.TOPIC_CENTER_INGEST,
        }

        if output_file:
            self._output_path = Path(output_file)
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self._output_path.open("a", encoding="utf-8")
            logger.info("MockKafkaClient ecrit dans %s", self._output_path)
        else:
            logger.info("MockKafkaClient en mode stdout (verbose_topics=%s)",
                        self.verbose_topics)

    def send(self, topic: str, payload: Any, key: Optional[str] = None) -> None:
        self._counts[topic] = self._counts.get(topic, 0) + 1
        # ecriture fichier (tous les topics)
        if self._fh is not None:
            line = to_json_str({"topic": topic, "key": key, "value": payload})
            self._fh.write(line + "\n")
        # affichage stdout (uniquement topics verbeux)
        if topic in self.verbose_topics:
            print(f"[KAFKA-MOCK] topic={topic} key={key} -> {to_json_str(payload)}",
                  file=sys.stdout)

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        # mini-recap a la fermeture
        if self._counts:
            total = sum(self._counts.values())
            logger.info("MockKafkaClient ferme — %d messages au total :", total)
            for topic, count in sorted(self._counts.items()):
                logger.info("  %-40s %8d msgs", topic, count)

    @property
    def counts(self) -> dict:
        """Compteurs de messages par topic (utile pour les tests)."""
        return dict(self._counts)


# ============================================================================
# FABRIQUE
# ============================================================================


def get_client(
    force_mock: bool = False,
    output_file: Optional[str] = None,
) -> BaseKafkaClient:
    """
    Renvoie un client Kafka en respectant la config :
      - KAFKA_ENABLED=1 -> KafkaClient reel
      - sinon ou force_mock=True -> MockKafkaClient

    Si MockKafkaClient et output_file fourni, les messages sont ecrits dans
    ce fichier (au format JSON-lines).
    """
    if force_mock or not config.KAFKA_ENABLED:
        out = output_file or os.getenv("MOCK_OUTPUT_FILE")
        return MockKafkaClient(output_file=out)
    return KafkaClient()
