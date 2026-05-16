"""
Exercice 1 : Word Count avec PySpark
=====================================
Ce programme compte le nombre d'occurrences de chaque mot dans un texte.
C'est l'exemple "Hello World" du Big Data avec Spark.
"""

from pyspark import SparkContext, SparkConf

# 1) Créer la configuration Spark et le contexte
conf = SparkConf().setAppName("WordCount").setMaster("local[*]")
sc = SparkContext(conf=conf)
sc.setLogLevel("ERROR")  # Réduire les messages de log

# 2) Texte d'exemple (on peut aussi lire un fichier avec sc.textFile("fichier.txt"))
text = [
    "Apache Spark is a fast and general engine for big data processing",
    "Spark provides high level APIs in Java Scala Python and R",
    "Spark is fast Spark is powerful Spark is easy to use",
    "Big data processing with Spark is awesome"
]

# 3) Créer un RDD à partir du texte
rdd = sc.parallelize(text)

# 4) Pipeline MapReduce pour compter les mots
#    - flatMap : découpe chaque ligne en mots
#    - map     : transforme chaque mot en paire (mot, 1)
#    - reduceByKey : additionne les 1 pour chaque mot identique
word_counts = (rdd
               .flatMap(lambda line: line.lower().split(" "))
               .map(lambda word: (word, 1))
               .reduceByKey(lambda a, b: a + b))

# 5) Trier par nombre d'occurrences (décroissant) et afficher
results = word_counts.sortBy(lambda x: -x[1]).collect()

print("\n========== RÉSULTAT WORD COUNT ==========")
for word, count in results:
    print(f"{word:20s} : {count}")
print("=========================================\n")

# 6) Arrêter le contexte Spark
sc.stop()
