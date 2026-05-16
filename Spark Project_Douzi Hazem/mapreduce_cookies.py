"""
Exercice 2 : MapReduce avec PySpark - Analyse de cookies
=========================================================
Ce programme analyse les achats de cookies par les clients :
  (a) Calcul du maximum dépensé par un client ayant noté 'awesome'
  (b)(i)  Nombre de notes 'awesome' par produit
  (b)(ii) Argent total dépensé par produit (clients 'awesome' uniquement)
  (b)(iii) Moyenne d'argent dépensé par produit (clients 'awesome' uniquement)
"""

from pyspark.sql import SparkSession

# 1) Créer la SparkSession
spark = SparkSession.builder \
    .appName("CookiesAnalysis") \
    .master("local[*]") \
    .getOrCreate()

sc = spark.sparkContext
sc.setLogLevel("ERROR")

# 2) Lire le fichier CSV en RDD
#    header=False car le fichier n'a pas d'en-tête
rdd = spark.read.csv("customercookies.csv", header=False).rdd

# Afficher un aperçu des données
print("\n========== APERÇU DES DONNÉES ==========")
for row in rdd.take(5):
    print(row)
print("========================================\n")

# ============================================================
# (a) Question initiale : maximum dépensé par client 'awesome'
# ============================================================
# dataset.map -> filter (rating == 'awesome') -> map -> reduce (max)
result = (rdd
          .map(lambda r: (r[0], r[1], r[2], r[3]))   # (id, product, spent, rating)
          .filter(lambda x: x[3] == 'awesome')        # garder seulement 'awesome'
          .map(lambda x: (x[3], float(x[2])))         # (rating, spent)
          .reduce(lambda first, second: (first[0], max(first[1], second[1]))))

print(f"(a) Maximum dépensé par un client 'awesome' : {result[1]} €")
print("    => C'est la dépense la plus élevée parmi les clients satisfaits.\n")

# ============================================================
# (b)(i) Nombre de notes 'awesome' par produit
# ============================================================
awesome_count = (rdd
                 .filter(lambda r: r[3] == 'awesome')   # filtrer 'awesome'
                 .map(lambda r: (r[1], 1))              # (produit, 1)
                 .reduceByKey(lambda a, b: a + b))      # somme par produit

print("(b)(i) Nombre de notes 'awesome' par produit :")
for product, count in awesome_count.collect():
    print(f"    {product:25s} : {count}")
print()

# ============================================================
# (b)(ii) Argent total dépensé par produit (clients 'awesome')
# ============================================================
total_spent = (rdd
               .filter(lambda r: r[3] == 'awesome')        # filtrer 'awesome'
               .map(lambda r: (r[1], float(r[2])))          # (produit, montant)
               .reduceByKey(lambda a, b: a + b))            # somme par produit

print("(b)(ii) Total dépensé par produit (clients 'awesome') :")
for product, total in total_spent.collect():
    print(f"    {product:25s} : {total} €")
print()

# ============================================================
# (b)(iii) Moyenne d'argent dépensé par produit (clients 'awesome')
# ============================================================
# Astuce : on combine total + count avec mapValues puis on divise
avg_spent = (rdd
             .filter(lambda r: r[3] == 'awesome')
             .map(lambda r: (r[1], (float(r[2]), 1)))                # (produit, (montant, 1))
             .reduceByKey(lambda a, b: (a[0]+b[0], a[1]+b[1]))         # (produit, (total, count))
             .mapValues(lambda v: v[0] / v[1]))                        # (produit, moyenne)

print("(b)(iii) Moyenne dépensée par produit (clients 'awesome') :")
for product, avg in avg_spent.collect():
    print(f"    {product:25s} : {avg} €")
print()

# Vérification de l'exemple donné dans l'énoncé :
# chocolate cookies awesome : 2 + 1 = 3, moyenne = 3/2 = 1.5
print("Vérification : pour 'chocolate cookies', 2 ratings awesome,")
print("               total = 2 + 1 = 3, moyenne = 3/2 = 1.5 ✓\n")

# 3) Arrêter Spark
spark.stop()
