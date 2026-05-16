# Scripts utilitaires VM — Projet Big Data Tétouan

Ce dossier contient les scripts à lancer sur ta VM Ubuntu pour vérifier et préparer l'environnement avant de lancer le projet.

## 📋 Workflow recommandé

```
1) Cloner le repo sur la VM
2) Lancer check_env.sh        → diagnostic complet
3) Installer ce qui manque    (pas-à-pas selon le diagnostic)
4) Relancer check_env.sh      → vérifier que tout est OK
5) Lancer install_libs.sh     → toutes les libs Python d'un coup
6) Lancer le simulateur       → python3 main.py --kafka --cycles 1
```

## 🔍 `check_env.sh` — Diagnostic complet

Vérifie **tout** ce dont tu as besoin pour le projet, en 8 catégories :

| # | Catégorie | Ce qui est vérifié |
|---|---|---|
| 1 | **Système Linux** | OS, kernel, RAM ≥ 6 Go, disque ≥ 20 Go, CPU ≥ 2 cores |
| 2 | **Réseau et utilitaires** | curl, wget, tar, git, ssh, internet, SSH passwordless |
| 3 | **Java** | Java 11/17, JAVA_HOME |
| 4 | **Python + libs** | Python 3.8+, pip, venv, et 11 librairies du projet |
| 5 | **Hadoop / HDFS** | binaire hadoop, HADOOP_HOME, daemons NameNode/DataNode |
| 6 | **Apache Spark** | spark-submit, SPARK_HOME, Master/Worker |
| 7 | **Apache Kafka** | KAFKA_HOME, Zookeeper :2181, Broker :9092, les 4 topics du projet |
| 8 | **MongoDB** | mongod, mongosh, connexion, base `tetouan_smartgrid` |

### Utilisation

```bash
# rendre executable une fois pour toutes
chmod +x scripts/check_env.sh

# lancer le diagnostic
./scripts/check_env.sh
```

### Sortie attendue

```
[OK]      python3                      version 3.10.12
[OK]      kafka-python                 v2.0.2 - Producteur Kafka
[MANQUE]  hadoop                       non installe
          -> wget https://dlcdn.apache.org/hadoop/common/hadoop-3.3.6/...
[WARN]    Daemon NameNode              non actif (HDFS pas demarre)
          -> start-dfs.sh

Total verifie : 35
OK            : 16
Warnings      : 4
Manquants     : 15

Pret a 45% : [##################......................]

=== A INSTALLER ===
  - hadoop : wget https://dlcdn.apache.org/hadoop/common/...
  - spark  : wget https://dlcdn.apache.org/spark/...
  ...
```

### Codes de sortie

| Code | Signification |
|---|---|
| `0` | Tout est OK, prêt à coder |
| `1` | Il manque des composants à installer |
| `2` | Tout est installé, mais des services à démarrer/configurer |

Tu peux donc faire :

```bash
./scripts/check_env.sh && python3 main.py --kafka --cycles 0
```

## 📦 `install_libs.sh` — Installation des librairies Python

Installe **toutes** les librairies Python du projet en une commande.

```bash
chmod +x scripts/install_libs.sh

# install dans le user pip global
./scripts/install_libs.sh

# install dans un environnement virtuel ./venv (recommandé)
./scripts/install_libs.sh --venv

# inclure PyTorch pour le modèle LSTM (~600 Mo, optionnel)
./scripts/install_libs.sh --venv --with-dl
```

### Ce qui est installé

| Catégorie | Librairies |
|---|---|
| **Streaming** | `kafka-python`, `pyspark` |
| **Données** | `numpy`, `pandas`, `pymongo` |
| **ML classique** | `scikit-learn` (Random Forest), `statsmodels` (ARIMA) |
| **Visualisation** | `matplotlib`, `folium`, `seaborn`, `plotly` |
| **Producteurs externes** | `requests` (météo), `feedparser` (RSS) |
| **Dashboards alt.** | `streamlit`, `wordcloud` |
| **Faker** | génération de données complémentaires |
| **DL (avec `--with-dl`)** | `torch` (CPU only) pour LSTM |

## 🔄 Workflow complet sur une VM Ubuntu fraîche

```bash
# 1) prerequis OS (a faire une fois)
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
                    openjdk-11-jdk \
                    curl wget tar unzip git ssh

# 2) cloner le projet
git clone https://github.com/Hazem-Douzi/big.git
cd big/Projet_Final_BigData

# 3) etat des lieux
chmod +x scripts/*.sh
./scripts/check_env.sh

# 4) installer les libs Python du projet
./scripts/install_libs.sh --venv

# 5) (a faire une fois) installer Hadoop / Spark / Kafka / MongoDB
#    -> suivre les sections 7-10 de Guide_Projet_Final.html

# 6) revérifier
./scripts/check_env.sh

# 7) lancer le simulateur
source venv/bin/activate
python3 main.py --cycles 2 --acceleration 60
```

## 🩺 Que faire si `check_env.sh` indique un problème ?

### `RAM ≥ 6 Go` mais ma VM n'a que 4 Go
Augmente la RAM dans VirtualBox : **VM stoppée → Configuration → Système → Mémoire vive**.
Ou bien **n'utilise pas YARN** (juste HDFS + Spark + Kafka, ça passe en 4 Go).

### `Java version 25 (potentiellement trop recente)`
Hadoop 3.3.6 est officiellement validé sur Java 8 et 11. Pour Java 17, ça marche dans 95% des cas. Pour Java >= 21, certaines API JVM ont changé → préfère installer Java 11 :

```bash
sudo apt install -y openjdk-11-jdk
sudo update-alternatives --config java   # selectionner java-11
```

### `JAVA_HOME non défini`
Le script propose la commande exacte. Sinon, version manuelle :

```bash
echo "export JAVA_HOME=$(readlink -f $(which java) | sed 's|/bin/java$||')" >> ~/.bashrc
source ~/.bashrc
```

### `Daemon NameNode non actif`
HDFS n'est pas démarré. Une fois Hadoop installé et configuré :

```bash
# 1ère fois seulement
hdfs namenode -format

# à chaque session
start-dfs.sh
jps    # tu dois voir : NameNode, DataNode, SecondaryNameNode
```

### `Topic tetouan.meters.readings n'existe pas encore`
Une fois le broker Kafka démarré :

```bash
for topic in tetouan.meters.readings tetouan.distributors.aggregated \
             tetouan.concentrators.aggregated tetouan.center.ingest; do
  kafka-topics.sh --create --bootstrap-server localhost:9092 \
    --topic $topic --partitions 3 --replication-factor 1
done

kafka-topics.sh --list --bootstrap-server localhost:9092
```

### `Base tetouan_smartgrid vide ou absente`
Une fois mongod démarré :

```bash
mongosh tetouan_smartgrid --eval '
  db.createCollection("measurements_15min");
  db.createCollection("anomalies");
  db.createCollection("predictions");
  db.createCollection("news_rss");
  db.measurements_15min.createIndex({ window_start: 1, district: 1 });
'
```

## 🪟 Variante Windows / PowerShell

Le script `check_env.sh` est en bash, donc pour Windows il faut soit :
- **WSL** (Windows Subsystem for Linux) — recommandé
- **Git Bash** (livré avec Git for Windows)
- **VirtualBox + Ubuntu** (le plus propre pour ce projet, c'est ce que demande le sujet)

## 📚 Pour aller plus loin

- Sections 6-10 de `Guide_Projet_Final.html` → install pas-à-pas de Java / Hadoop / Spark / Kafka / MongoDB
- `HOW_TO_VIEW.md` → comment visualiser les résultats du simulateur
- `README.md` → architecture et options du simulateur
