"""
Point d'entree CLI du simulateur Big Data Tetouan.

Exemples d'utilisation :

  # 1) Mode demo (sans Kafka) — 2 cycles acceleres en stdout
  python main.py --cycles 2

  # 2) Mode demo + ecriture des messages dans un fichier JSON-lines
  python main.py --cycles 1 --output-file ./out/cycle.jsonl

  # 3) Mode reel avec Kafka (necessite un broker accessible)
  python main.py --kafka --bootstrap localhost:9092 --cycles 5

  # 4) Boucle infinie en demo (utile pour le dashboard)
  python main.py --cycles 0  # 0 = infini

  # 5) Cycle a vitesse reelle (1 cycle = 30 minutes reelles)
  python main.py --no-demo --cycles 1
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

from simulator import config
from simulator.kafka_client import get_client
from simulator.simulator import TetouanSimulator


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulateur Big Data — Smart Grid Tetouan",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="Nombre de cycles a executer (0 = boucle infinie). Defaut: 1.",
    )
    parser.add_argument(
        "--kafka",
        action="store_true",
        help="Active la publication vers un broker Kafka reel (KAFKA_ENABLED=1).",
    )
    parser.add_argument(
        "--bootstrap",
        type=str,
        default=config.KAFKA_BOOTSTRAP_SERVERS,
        help=f"Bootstrap Kafka (defaut: {config.KAFKA_BOOTSTRAP_SERVERS})",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="En mode mock, ecrit les messages dans ce fichier JSON-lines.",
    )
    parser.add_argument(
        "--no-demo",
        action="store_true",
        help="Desactive le mode demo accelere (1 cycle = 30 minutes reelles).",
    )
    parser.add_argument(
        "--acceleration",
        type=int,
        default=None,
        help=(
            "Acceleration temporelle en mode demo (1 sec reelle = X min simulees). "
            f"Defaut: {config.TIME_ACCELERATION}."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=config.RANDOM_SEED,
        help=f"Seed aleatoire (defaut: {config.RANDOM_SEED}).",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help="Heure simulee de demarrage au format ISO (ex: 2026-05-16T19:00:00).",
    )
    parser.add_argument(
        "--num-buckets",
        type=int,
        default=15,
        help=(
            "Nombre de buckets temporels pour etaler les compteurs sur 15 min. "
            "Defaut: 15 (1 bucket par minute)."
        ),
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=config.LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Niveau de log (defaut: {config.LOG_LEVEL}).",
    )
    return parser.parse_args()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    args = _parse_args()
    _configure_logging(args.log_level)
    logger = logging.getLogger("main")

    # ajustements config par variables d'environnement (pour les sous-modules)
    if args.kafka:
        os.environ["KAFKA_ENABLED"] = "1"
        os.environ["KAFKA_BOOTSTRAP"] = args.bootstrap
    else:
        os.environ["KAFKA_ENABLED"] = "0"

    if args.no_demo:
        os.environ["DEMO_MODE"] = "0"
    else:
        os.environ["DEMO_MODE"] = "1"
        if args.acceleration is not None:
            os.environ["TIME_ACCELERATION"] = str(args.acceleration)

    # rechargement du module config pour qu'il relise les variables d'env
    import importlib
    importlib.reload(config)

    # heure de depart
    start_time = None
    if args.start_time:
        try:
            start_time = datetime.fromisoformat(args.start_time)
        except ValueError:
            logger.error("Format --start-time invalide: %s", args.start_time)
            return 2

    logger.info("=== Simulateur Big Data Tetouan ===")
    logger.info("Kafka active        : %s", config.KAFKA_ENABLED)
    logger.info("Mode demo           : %s", config.DEMO_MODE)
    if config.DEMO_MODE:
        logger.info("Acceleration        : 1 sec = %d min simulees",
                    config.TIME_ACCELERATION)
    logger.info("Cycles a executer   : %s",
                "infini" if args.cycles == 0 else args.cycles)
    logger.info("Buckets temporels   : %d", args.num_buckets)

    # client Kafka (vrai ou mock)
    client = get_client(
        force_mock=not args.kafka,
        output_file=args.output_file,
    )

    # construction et lancement du simulateur
    simulator = TetouanSimulator(
        client=client,
        seed=args.seed,
        start_time=start_time,
        num_buckets=args.num_buckets,
    )

    num_cycles = None if args.cycles == 0 else args.cycles
    try:
        simulator.run(num_cycles=num_cycles)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erreur durant la simulation : %s", exc)
        return 1

    logger.info("Simulation terminee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
