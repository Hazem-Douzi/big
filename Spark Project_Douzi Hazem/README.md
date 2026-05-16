# TP N°9 — Spark, RDD & MLlib

**ENSA Tétouan** — Fondamentaux de Big Data — Pr. Imad Sassi
**Étudiant :** Douzi Hazem
**Année :** 2025/2026

---

## 📁 Contenu du projet

| Fichier | Description |
|---------|-------------|
| `wordcount.py` | **Exercice 1** : Word Count avec PySpark |
| `customercookies.csv` | Dataset pour l'exercice 2 |
| `mapreduce_cookies.py` | **Exercice 2** : MapReduce sur les cookies (a, b-i, b-ii, b-iii) |
| `kMeans_template.py` | **Exercice 3** : k-Means avec Spark |
| `generate_blobs.py` | Script pour créer le dataset `blobs.csv` |
| `blobs.csv` | Dataset 300 points en 3 clusters (généré) |
| `TP9_Spark_Guide.html` | 📘 **Guide pédagogique pas à pas** |

## 🔧 Installation

```bash
# Java requis
sudo apt install openjdk-11-jdk -y

# Bibliothèques Python
pip install pyspark numpy scikit-learn matplotlib
```

## ▶️ Exécution

```bash
# Exercice 1
python3 wordcount.py

# Exercice 2
python3 mapreduce_cookies.py

# Exercice 3 (générer d'abord les données)
python3 generate_blobs.py
python3 kMeans_template.py
```

## 📘 Guide complet

Ouvrez **`TP9_Spark_Guide.html`** dans votre navigateur pour une explication
détaillée pas à pas de chaque exercice avec les résultats attendus.

## 📅 Rendu

À envoyer avant le **15 mai 2026** à **i.sassi@uae.ac.ma**
