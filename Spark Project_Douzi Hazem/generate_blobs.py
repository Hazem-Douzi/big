"""
Script pour générer le dataset blobs.csv (utilisé par kMeans_template.py).

Version 1 : avec sklearn (recommandée si disponible)
Version 2 : sans sklearn, avec random pur (fallback)
"""

import random
import math

try:
    # --- Version 1 : avec sklearn ---
    from sklearn.datasets import make_blobs
    import numpy as np

    X, y = make_blobs(n_samples=300, centers=3, n_features=2,
                      cluster_std=1.0, random_state=42)
    np.savetxt("blobs.csv", X, delimiter=",", fmt="%.6f")
    print("Fichier blobs.csv généré avec sklearn.")
    print(f"Forme : {X.shape}")

except ImportError:
    # --- Version 2 : sans sklearn ---
    print("sklearn non disponible, génération avec random pur...")
    random.seed(42)

    # 3 centres autour desquels on va générer des points
    centers = [(2.0, 2.0), (8.0, 3.0), (5.0, 8.0)]
    n_per_cluster = 100
    std = 1.0

    points = []
    for cx, cy in centers:
        for _ in range(n_per_cluster):
            # Génération gaussienne autour du centre
            x = random.gauss(cx, std)
            y = random.gauss(cy, std)
            points.append((x, y))

    # Mélanger les points
    random.shuffle(points)

    # Sauvegarder
    with open("blobs.csv", "w") as f:
        for x, y in points:
            f.write(f"{x:.6f},{y:.6f}\n")

    print(f"Fichier blobs.csv généré avec succès ({len(points)} points).")
