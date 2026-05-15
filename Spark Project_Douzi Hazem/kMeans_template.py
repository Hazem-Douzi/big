"""
Exercice 3 : k-Means avec PySpark
==================================
Implémentation manuelle de l'algorithme k-Means avec Spark.

Principe de k-Means :
  1) Choisir k centroïdes initiaux (au hasard).
  2) Affecter chaque point au centroïde le plus proche.
  3) Recalculer les centroïdes (moyenne des points de chaque cluster).
  4) Répéter 2-3 jusqu'à convergence (les centroïdes ne bougent plus).
"""

import numpy as np
from pyspark import SparkContext, SparkConf

# ============================================================
# FONCTIONS À IMPLÉMENTER (TODO de l'énoncé)
# ============================================================

def assign_to_centroid(point, centroids):
    """
    TODO 1 : Affecter un point au centroïde le plus proche.

    Paramètres :
        point     : np.array, coordonnées du point
        centroids : liste de np.array, les k centroïdes courants

    Retour :
        (index_centroide, point) -> sera utilisé comme paire (clé, valeur)
    """
    # Calcul de la distance euclidienne entre le point et chaque centroïde
    distances = [np.linalg.norm(point - c) for c in centroids]
    # On prend l'index du centroïde dont la distance est minimale
    closest_index = int(np.argmin(distances))
    return (closest_index, point)


def calculate_new_centroid(points):
    """
    TODO 2 : Calculer le nouveau centroïde d'un cluster.

    Paramètre :
        points : liste de np.array, tous les points appartenant au cluster

    Retour :
        np.array : moyenne (centre de gravité) des points
    """
    points_array = np.array(list(points))
    return points_array.mean(axis=0)


# ============================================================
# ALGORITHME PRINCIPAL k-MEANS
# ============================================================

def kmeans(rdd_points, k=3, max_iter=20, tolerance=1e-4):
    """
    Exécute l'algorithme k-Means.

    Paramètres :
        rdd_points : RDD de np.array
        k          : nombre de clusters
        max_iter   : nombre maximum d'itérations
        tolerance  : seuil de convergence
    """
    # 1) Initialisation : on prend k points au hasard comme centroïdes initiaux
    centroids = rdd_points.takeSample(False, k, seed=42)
    print(f"\nCentroïdes initiaux :\n{np.array(centroids)}\n")

    for iteration in range(max_iter):
        # 2) Affecter chaque point au centroïde le plus proche
        clusters = rdd_points.map(lambda p: assign_to_centroid(p, centroids))

        # 3) Regrouper les points par cluster et calculer les nouveaux centroïdes
        new_centroids_rdd = (clusters
                             .groupByKey()
                             .mapValues(calculate_new_centroid)
                             .collect())

        # On reconstruit la liste triée par index de cluster
        new_centroids = [None] * k
        for idx, c in new_centroids_rdd:
            new_centroids[idx] = c

        # Si un cluster est vide, on garde l'ancien centroïde
        for i in range(k):
            if new_centroids[i] is None:
                new_centroids[i] = centroids[i]

        # 4) Vérifier la convergence
        shift = sum(np.linalg.norm(np.array(new_centroids[i]) - np.array(centroids[i]))
                    for i in range(k))
        print(f"Itération {iteration+1:2d} | déplacement total = {shift:.6f}")

        centroids = new_centroids
        if shift < tolerance:
            print(f"\n>>> Convergence atteinte à l'itération {iteration+1}")
            break

    return centroids


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

if __name__ == "__main__":
    # 1) Initialiser Spark
    conf = SparkConf().setAppName("kMeansSpark").setMaster("local[*]")
    sc = SparkContext(conf=conf)
    sc.setLogLevel("ERROR")

    # 2) Charger le dataset blobs.csv (chaque ligne : x,y)
    raw = sc.textFile("blobs.csv")
    points_rdd = raw.map(lambda line: np.array([float(x) for x in line.strip().split(",")]))

    print(f"Nombre de points : {points_rdd.count()}")
    print(f"Exemple de points : {points_rdd.take(3)}")

    # 3) Lancer k-Means avec k=3
    final_centroids = kmeans(points_rdd, k=3, max_iter=20)

    # 4) Afficher les centroïdes finaux
    print("\n========== CENTROÏDES FINAUX ==========")
    for i, c in enumerate(final_centroids):
        print(f"  Cluster {i} : {c}")
    print("========================================\n")

    # 5) Compter le nombre de points par cluster
    cluster_sizes = (points_rdd
                     .map(lambda p: assign_to_centroid(p, final_centroids))
                     .map(lambda x: (x[0], 1))
                     .reduceByKey(lambda a, b: a + b)
                     .collect())

    print("Répartition des points par cluster :")
    for cluster_id, size in sorted(cluster_sizes):
        print(f"  Cluster {cluster_id} : {size} points")

    sc.stop()
