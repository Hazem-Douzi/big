#!/usr/bin/env bash
#
# check_env.sh — Verifie l'environnement de la VM pour le projet Big Data Tetouan
#
# Usage :
#   chmod +x scripts/check_env.sh
#   ./scripts/check_env.sh
#
# Le script verifie en 7 categories :
#   1) Systeme Linux                (uname, RAM, disque)
#   2) Reseau et utilitaires        (curl, wget, ssh, git)
#   3) Java + JVM                   (java -version, JAVA_HOME)
#   4) Python + pip + librairies    (kafka-python, numpy, pyspark, pymongo, ...)
#   5) Hadoop / HDFS                (hadoop version, JPS NameNode/DataNode)
#   6) Spark                        (spark-submit, JPS Master/Worker)
#   7) Kafka                        (kafka-topics, broker actif sur :9092)
#   8) MongoDB                      (mongod, mongosh, connexion)
#
# Pour chaque element :
#   [OK]      = installe et fonctionnel
#   [MANQUE]  = absent, on affiche la commande pour installer
#   [WARN]    = present mais probleme (mauvaise version, service stoppe, etc.)
#
# A la fin, un resume "X/N OK" et la liste des actions a faire.

set +e   # ne pas exit on error : on veut voir TOUS les problemes

# ============================================================================
# COULEURS ANSI
# ============================================================================
if [ -t 1 ]; then
    GREEN='\033[1;32m'
    RED='\033[1;31m'
    YELLOW='\033[1;33m'
    BLUE='\033[1;34m'
    CYAN='\033[1;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    NC='\033[0m'
else
    GREEN='' RED='' YELLOW='' BLUE='' CYAN='' BOLD='' DIM='' NC=''
fi

# ============================================================================
# COMPTEURS GLOBAUX
# ============================================================================
TOTAL=0
OK=0
MISSING=0
WARN=0
MISSING_ACTIONS=()
WARN_ACTIONS=()

# ============================================================================
# HELPERS DE PRINT
# ============================================================================
print_header() {
    echo ""
    echo -e "${BLUE}${BOLD}=========================================================${NC}"
    echo -e "${BLUE}${BOLD}  $1${NC}"
    echo -e "${BLUE}${BOLD}=========================================================${NC}"
}

print_ok() {
    # $1 = nom, $2 = detail (optionnel)
    TOTAL=$((TOTAL + 1))
    OK=$((OK + 1))
    if [ -n "$2" ]; then
        printf "  ${GREEN}[OK]${NC}      %-30s ${DIM}%s${NC}\n" "$1" "$2"
    else
        printf "  ${GREEN}[OK]${NC}      %s\n" "$1"
    fi
}

print_missing() {
    # $1 = nom, $2 = commande pour installer, $3 = detail
    TOTAL=$((TOTAL + 1))
    MISSING=$((MISSING + 1))
    printf "  ${RED}[MANQUE]${NC}  %-30s ${DIM}%s${NC}\n" "$1" "${3:-non installe}"
    if [ -n "$2" ]; then
        printf "             ${YELLOW}-> %s${NC}\n" "$2"
        MISSING_ACTIONS+=("$1 : $2")
    fi
}

print_warn() {
    # $1 = nom, $2 = solution, $3 = detail
    TOTAL=$((TOTAL + 1))
    WARN=$((WARN + 1))
    printf "  ${YELLOW}[WARN]${NC}    %-30s ${DIM}%s${NC}\n" "$1" "${3:-attention}"
    if [ -n "$2" ]; then
        printf "             ${YELLOW}-> %s${NC}\n" "$2"
        WARN_ACTIONS+=("$1 : $2")
    fi
}

# verifie qu'une commande existe
have() { command -v "$1" >/dev/null 2>&1; }

# verifie qu'un port TCP est ouvert localement
port_open() {
    if have ss; then
        ss -tln 2>/dev/null | grep -q ":$1 "
    elif have netstat; then
        netstat -tln 2>/dev/null | grep -q ":$1 "
    else
        # fallback : tenter de se connecter
        timeout 1 bash -c "echo > /dev/tcp/127.0.0.1/$1" 2>/dev/null
    fi
}

# ============================================================================
# 1) SYSTEME
# ============================================================================
check_system() {
    print_header "1) Systeme Linux"

    # OS
    if [ -f /etc/os-release ]; then
        os_name=$(. /etc/os-release; echo "$NAME $VERSION")
        print_ok "OS" "$os_name"
    else
        print_warn "OS" "" "/etc/os-release introuvable"
    fi

    # noyau
    print_ok "Kernel" "$(uname -r)"

    # arch
    arch=$(uname -m)
    if [ "$arch" = "x86_64" ] || [ "$arch" = "aarch64" ]; then
        print_ok "Architecture" "$arch"
    else
        print_warn "Architecture" "" "$arch (les binaires officiels sont x86_64 ou aarch64)"
    fi

    # RAM
    if [ -r /proc/meminfo ]; then
        ram_kb=$(awk '/MemTotal:/{print $2}' /proc/meminfo)
        ram_gb=$(awk -v k="$ram_kb" 'BEGIN{printf "%.1f", k/1024/1024}')
        ram_int=$(awk -v k="$ram_kb" 'BEGIN{printf "%d", k/1024/1024}')
        if [ "$ram_int" -ge 6 ]; then
            print_ok "RAM totale" "${ram_gb} Go"
        elif [ "$ram_int" -ge 3 ]; then
            print_warn "RAM totale" "Augmenter a >=6 Go pour pouvoir lancer Hadoop+Spark+Kafka en parallele" "${ram_gb} Go (juste)"
        else
            print_missing "RAM totale" "Augmenter la VM a >=4 Go RAM" "${ram_gb} Go (insuffisant)"
        fi
    fi

    # Disque libre sur /
    if have df; then
        free_gb=$(df -BG / | awk 'NR==2{gsub("G","",$4); print $4}')
        if [ -n "$free_gb" ] && [ "$free_gb" -ge 20 ]; then
            print_ok "Disque libre /" "${free_gb} Go"
        elif [ -n "$free_gb" ] && [ "$free_gb" -ge 10 ]; then
            print_warn "Disque libre /" "Liberer de l'espace, prevoir 20+ Go" "${free_gb} Go"
        else
            print_warn "Disque libre /" "" "${free_gb:-?} Go"
        fi
    fi

    # CPU cores
    if [ -r /proc/cpuinfo ]; then
        cores=$(grep -c '^processor' /proc/cpuinfo)
        if [ "$cores" -ge 2 ]; then
            print_ok "CPU cores" "$cores cores"
        else
            print_warn "CPU cores" "Augmenter a >=2 vCPU" "$cores core(s)"
        fi
    fi
}

# ============================================================================
# 2) RESEAU ET UTILITAIRES
# ============================================================================
check_network() {
    print_header "2) Reseau et utilitaires"

    # commandes de base
    for cmd in curl wget tar unzip git ssh ssh-keygen; do
        if have "$cmd"; then
            print_ok "$cmd" "$(command -v $cmd)"
        else
            print_missing "$cmd" "sudo apt install -y $cmd"
        fi
    done

    # internet (necessaire pour pip install / wget kafka.tar.gz)
    if curl -s --connect-timeout 4 -o /dev/null https://www.google.com; then
        print_ok "Connexion internet" "OK"
    else
        print_warn "Connexion internet" "Verifier la config reseau de la VM (NAT)" "ping echoue"
    fi

    # SSH localhost (Hadoop l'utilise)
    if have ssh && ssh -o BatchMode=yes -o ConnectTimeout=2 \
        -o StrictHostKeyChecking=no localhost true 2>/dev/null; then
        print_ok "SSH passwordless localhost" "OK (hadoop l'utilisera)"
    else
        print_warn "SSH passwordless localhost" \
            "ssh-keygen -t rsa -P '' -f ~/.ssh/id_rsa && cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys" \
            "non configure"
    fi
}

# ============================================================================
# 3) JAVA
# ============================================================================
check_java() {
    print_header "3) Java (requis pour Hadoop, Spark, Kafka, Zookeeper)"

    if ! have java; then
        print_missing "Java" "sudo apt install -y openjdk-11-jdk"
        return
    fi

    java_ver=$(java -version 2>&1 | head -1 | awk -F\" '{print $2}')
    java_major=$(echo "$java_ver" | awk -F. '{print ($1 == "1") ? $2 : $1}')

    if [ -z "$java_major" ]; then
        print_warn "java" "" "version non parsable : $java_ver"
    elif [ "$java_major" -ge 11 ] && [ "$java_major" -le 17 ]; then
        print_ok "java" "version $java_ver"
    elif [ "$java_major" -lt 11 ]; then
        print_missing "java >= 11" "sudo apt install -y openjdk-11-jdk" "version trouvee : $java_ver"
    else
        print_warn "java" \
            "Hadoop 3.3.6 supporte officiellement Java 8/11. Tester ou repasser a Java 11." \
            "version $java_ver (potentiellement trop recente)"
    fi

    # JAVA_HOME
    if [ -n "$JAVA_HOME" ] && [ -x "$JAVA_HOME/bin/java" ]; then
        print_ok "JAVA_HOME" "$JAVA_HOME"
    else
        # essayer d'auto-detecter le vrai JDK (pas un wrapper comme mise/asdf)
        auto_jh=""
        for candidate in \
            /usr/lib/jvm/java-11-openjdk-amd64 \
            /usr/lib/jvm/java-11-openjdk \
            /usr/lib/jvm/default-java \
            /usr/lib/jvm/java-17-openjdk-amd64 \
            /usr/lib/jvm/java-8-openjdk-amd64; do
            if [ -x "$candidate/bin/java" ]; then
                auto_jh="$candidate"
                break
            fi
        done
        # fallback : remonter le lien symbolique de java
        if [ -z "$auto_jh" ] && have readlink && have which; then
            real_java=$(readlink -f "$(which java)" 2>/dev/null)
            # ne suggerer que si ca ressemble a un vrai JDK (presence de javac)
            jh_candidate=$(echo "$real_java" | sed 's|/bin/java$||')
            if [ -x "$jh_candidate/bin/javac" ]; then
                auto_jh="$jh_candidate"
            fi
        fi
        suggested="${auto_jh:-/usr/lib/jvm/java-11-openjdk-amd64}"
        print_warn "JAVA_HOME" \
            "echo 'export JAVA_HOME=$suggested' >> ~/.bashrc && source ~/.bashrc" \
            "non defini"
    fi
}

# ============================================================================
# 4) PYTHON ET LIBRAIRIES
# ============================================================================
check_python() {
    print_header "4) Python et librairies du projet"

    # Python
    if have python3; then
        py_ver=$(python3 --version 2>&1 | awk '{print $2}')
        py_major=$(echo "$py_ver" | cut -d. -f1)
        py_minor=$(echo "$py_ver" | cut -d. -f2)
        if [ "$py_major" = "3" ] && [ "$py_minor" -ge 8 ]; then
            print_ok "python3" "version $py_ver"
        else
            print_warn "python3" "Mettre a jour vers Python 3.8+" "version $py_ver"
        fi
    else
        print_missing "python3" "sudo apt install -y python3 python3-pip python3-venv"
        return
    fi

    # pip
    if python3 -m pip --version >/dev/null 2>&1; then
        pip_ver=$(python3 -m pip --version 2>&1 | awk '{print $2}')
        print_ok "pip" "version $pip_ver"
    else
        print_missing "pip" "sudo apt install -y python3-pip"
    fi

    # venv (recommande pour ne pas polluer le systeme)
    if python3 -m venv --help >/dev/null 2>&1; then
        print_ok "python3-venv" "disponible"
    else
        print_warn "python3-venv" "sudo apt install -y python3-venv" "manquant (recommande)"
    fi

    # Liste des librairies necessaires
    # Format : "import_name|pip_name|description"
    libs=(
        "kafka|kafka-python|Producteur/consumer Kafka pour le simulateur"
        "numpy|numpy|Calculs numeriques"
        "pandas|pandas|Manipulation de DataFrames (analyse historique, ML)"
        "pyspark|pyspark|Spark Structured Streaming en Python"
        "pymongo|pymongo|Driver MongoDB pour persister les fenetres 15 min"
        "sklearn|scikit-learn|Modele ML : Random Forest"
        "statsmodels|statsmodels|Modele ML : ARIMA"
        "matplotlib|matplotlib|Graphiques pour le rapport"
        "folium|folium|Heatmap geographique de Tetouan"
        "feedparser|feedparser|Producteur RSS (actualite industrielle)"
        "requests|requests|Producteur meteo (API openweathermap)"
    )

    # Librairies optionnelles (DL)
    libs_optional=(
        "torch|torch|Modele ML : LSTM (deep learning)"
        "tensorflow|tensorflow|Alternative LSTM"
        "streamlit|streamlit|Dashboard interactif (alternative)"
        "wordcloud|wordcloud|Word cloud sur les rapports techniques"
    )

    echo ""
    echo -e "  ${BOLD}Librairies obligatoires :${NC}"
    for entry in "${libs[@]}"; do
        IFS='|' read -r imp pkg desc <<< "$entry"
        if python3 -c "import $imp" >/dev/null 2>&1; then
            ver=$(python3 -c "import $imp; print(getattr($imp,'__version__','?'))" 2>/dev/null || echo "?")
            print_ok "$pkg" "v$ver - $desc"
        else
            print_missing "$pkg" "python3 -m pip install $pkg" "$desc"
        fi
    done

    echo ""
    echo -e "  ${BOLD}Librairies optionnelles (selon ce que tu codes) :${NC}"
    for entry in "${libs_optional[@]}"; do
        IFS='|' read -r imp pkg desc <<< "$entry"
        if python3 -c "import $imp" >/dev/null 2>&1; then
            ver=$(python3 -c "import $imp; print(getattr($imp,'__version__','?'))" 2>/dev/null || echo "?")
            print_ok "$pkg" "v$ver - $desc"
        else
            # ne compte pas comme manque, juste un warn doux
            printf "  ${DIM}[opt.]   %-30s pas installe : pip install %s${NC}\n" "$pkg" "$pkg"
        fi
    done

    # requirements.txt si present (le notre)
    if [ -f requirements.txt ] || [ -f Projet_Final_BigData/requirements.txt ]; then
        echo ""
        echo -e "  ${DIM}Astuce : pour tout installer d'un coup :${NC}"
        echo -e "  ${DIM}  python3 -m pip install -r requirements.txt${NC}"
    fi
}

# ============================================================================
# 5) HADOOP
# ============================================================================
check_hadoop() {
    print_header "5) Hadoop / HDFS"

    if ! have hadoop && [ -z "$HADOOP_HOME" ]; then
        print_missing "hadoop" \
            "wget https://dlcdn.apache.org/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz && tar -xzf hadoop-3.3.6.tar.gz -C /opt/" \
            "non installe"
        return
    fi

    # version
    if have hadoop; then
        hadoop_ver=$(hadoop version 2>/dev/null | head -1 | awk '{print $2}')
        print_ok "hadoop" "version $hadoop_ver"
    fi

    # HADOOP_HOME
    if [ -n "$HADOOP_HOME" ] && [ -d "$HADOOP_HOME" ]; then
        print_ok "HADOOP_HOME" "$HADOOP_HOME"
    else
        print_warn "HADOOP_HOME" \
            "echo 'export HADOOP_HOME=/opt/hadoop-3.3.6' >> ~/.bashrc" \
            "non defini"
    fi

    # JPS (le binaire pour voir les daemons Java)
    if ! have jps; then
        print_warn "jps" "" "non disponible (vient avec le JDK)"
        return
    fi

    daemons=$(jps 2>/dev/null)
    for d in NameNode DataNode SecondaryNameNode ResourceManager NodeManager; do
        if echo "$daemons" | grep -q "$d"; then
            print_ok "Daemon $d" "actif"
        else
            # NodeManager / ResourceManager sont YARN, peut etre intentionnel
            if [ "$d" = "ResourceManager" ] || [ "$d" = "NodeManager" ]; then
                printf "  ${DIM}[opt.]   %-30s YARN non demarre (ok si juste HDFS+Spark)${NC}\n" "$d"
            else
                print_warn "Daemon $d" "start-dfs.sh" "non actif (HDFS pas demarre)"
            fi
        fi
    done

    # UI HDFS
    if port_open 9870; then
        print_ok "HDFS UI" "http://localhost:9870 (port 9870 ouvert)"
    else
        # ne pas warner si HDFS pas demarre du tout
        true
    fi
}

# ============================================================================
# 6) SPARK
# ============================================================================
check_spark() {
    print_header "6) Apache Spark"

    if ! have spark-submit && [ -z "$SPARK_HOME" ]; then
        print_missing "spark" \
            "wget https://dlcdn.apache.org/spark/spark-3.5.0/spark-3.5.0-bin-hadoop3.tgz && tar -xzf spark-3.5.0-bin-hadoop3.tgz -C /opt/" \
            "non installe"
        return
    fi

    if have spark-submit; then
        spark_ver=$(spark-submit --version 2>&1 | grep -oE 'version [0-9.]+' | head -1 | awk '{print $2}')
        if [ -n "$spark_ver" ]; then
            print_ok "spark-submit" "version $spark_ver"
        else
            print_warn "spark-submit" "" "version non determinee"
        fi
    fi

    # SPARK_HOME
    if [ -n "$SPARK_HOME" ] && [ -d "$SPARK_HOME" ]; then
        print_ok "SPARK_HOME" "$SPARK_HOME"
    else
        print_warn "SPARK_HOME" \
            "echo 'export SPARK_HOME=/opt/spark-3.5.0-bin-hadoop3' >> ~/.bashrc" \
            "non defini"
    fi

    # daemons
    if have jps; then
        daemons=$(jps 2>/dev/null)
        if echo "$daemons" | grep -qE "Master|org.apache.spark.deploy.master.Master"; then
            print_ok "Spark Master daemon" "actif"
        else
            print_warn "Spark Master daemon" "\$SPARK_HOME/sbin/start-master.sh" "non actif"
        fi
        if echo "$daemons" | grep -qE "Worker|org.apache.spark.deploy.worker.Worker"; then
            print_ok "Spark Worker daemon" "actif"
        else
            printf "  ${DIM}[opt.]   %-30s start-worker.sh spark://localhost:7077${NC}\n" "Spark Worker daemon"
        fi
    fi

    # UI
    if port_open 8080; then
        print_ok "Spark UI" "http://localhost:8080 (port 8080 ouvert)"
    fi
}

# ============================================================================
# 7) KAFKA
# ============================================================================
check_kafka() {
    print_header "7) Apache Kafka"

    # binaires
    if ! have kafka-topics.sh && [ -z "$KAFKA_HOME" ]; then
        print_missing "kafka" \
            "wget https://dlcdn.apache.org/kafka/3.6.0/kafka_2.13-3.6.0.tgz && tar -xzf kafka_2.13-3.6.0.tgz -C /opt/" \
            "non installe"
        return
    fi

    if [ -n "$KAFKA_HOME" ]; then
        print_ok "KAFKA_HOME" "$KAFKA_HOME"
    elif have kafka-topics.sh; then
        kh=$(dirname "$(dirname "$(command -v kafka-topics.sh)")")
        print_ok "kafka-topics.sh" "trouve, KAFKA_HOME possible: $kh"
    fi

    # Zookeeper (port 2181)
    if port_open 2181; then
        print_ok "Zookeeper" "actif sur :2181"
    else
        print_warn "Zookeeper" \
            "\$KAFKA_HOME/bin/zookeeper-server-start.sh -daemon \$KAFKA_HOME/config/zookeeper.properties" \
            "non actif"
    fi

    # Broker Kafka (port 9092)
    if port_open 9092; then
        print_ok "Kafka broker" "actif sur :9092"
    else
        print_warn "Kafka broker" \
            "\$KAFKA_HOME/bin/kafka-server-start.sh -daemon \$KAFKA_HOME/config/server.properties" \
            "non actif"
        return
    fi

    # Topics du projet (s'ils existent deja)
    if have kafka-topics.sh; then
        existing=$(kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null)
        for topic in tetouan.meters.readings tetouan.distributors.aggregated \
                     tetouan.concentrators.aggregated tetouan.center.ingest; do
            if echo "$existing" | grep -q "^$topic\$"; then
                print_ok "Topic $topic" "existe"
            else
                print_warn "Topic $topic" \
                    "kafka-topics.sh --create --bootstrap-server localhost:9092 --topic $topic --partitions 3 --replication-factor 1" \
                    "n'existe pas encore"
            fi
        done
    fi
}

# ============================================================================
# 8) MONGODB
# ============================================================================
check_mongo() {
    print_header "8) MongoDB"

    if ! have mongod && ! have mongo && ! have mongosh; then
        print_missing "MongoDB" \
            "Suivre la doc officielle : https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-ubuntu/" \
            "non installe"
        return
    fi

    # service
    if systemctl is-active --quiet mongod 2>/dev/null; then
        print_ok "Service mongod" "actif (systemctl)"
    elif port_open 27017; then
        print_ok "Service mongod" "actif (port 27017 ouvert)"
    else
        print_warn "Service mongod" "sudo systemctl start mongod" "non actif"
    fi

    # mongosh / mongo
    if have mongosh; then
        m_ver=$(mongosh --version 2>&1 | head -1)
        print_ok "mongosh" "$m_ver"
    elif have mongo; then
        print_ok "mongo (legacy CLI)" "$(mongo --version 2>&1 | head -1)"
    else
        print_warn "mongosh" "Installer mongosh : https://www.mongodb.com/docs/mongodb-shell/install/" "client absent"
    fi

    # connexion
    if port_open 27017 && have mongosh; then
        if echo 'db.runCommand({ping:1}).ok' | mongosh --quiet --norc 2>/dev/null | grep -q "1"; then
            print_ok "Connexion 127.0.0.1:27017" "ping OK"

            # base tetouan_smartgrid existe ?
            collections=$(mongosh tetouan_smartgrid --quiet --norc --eval 'db.getCollectionNames().join(",")' 2>/dev/null)
            if [ -n "$collections" ] && [ "$collections" != "" ]; then
                print_ok "Base tetouan_smartgrid" "collections : $collections"
            else
                print_warn "Base tetouan_smartgrid" \
                    "mongosh tetouan_smartgrid --eval 'db.createCollection(\"measurements_15min\")'" \
                    "vide ou absente"
            fi
        else
            print_warn "Connexion 27017" "Verifier les logs mongod" "ping echoue"
        fi
    fi
}

# ============================================================================
# RESUME FINAL
# ============================================================================
print_summary() {
    print_header "Resume"

    pct=0
    if [ "$TOTAL" -gt 0 ]; then
        pct=$(( OK * 100 / TOTAL ))
    fi

    echo ""
    printf "  Total verifie    : ${BOLD}%d${NC}\n" "$TOTAL"
    printf "  ${GREEN}OK              : %d${NC}\n" "$OK"
    printf "  ${YELLOW}Warnings        : %d${NC}\n" "$WARN"
    printf "  ${RED}Manquants       : %d${NC}\n" "$MISSING"
    echo ""

    # Barre de progression
    bar_size=40
    filled=$(( pct * bar_size / 100 ))
    bar=""
    for i in $(seq 1 $bar_size); do
        if [ "$i" -le "$filled" ]; then bar="${bar}#"; else bar="${bar}."; fi
    done
    if [ "$pct" -ge 90 ]; then color=$GREEN
    elif [ "$pct" -ge 60 ]; then color=$YELLOW
    else color=$RED
    fi
    printf "  Pret a %3d%% : ${color}[%s]${NC}\n" "$pct" "$bar"

    if [ ${#MISSING_ACTIONS[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}${BOLD}=== A INSTALLER ===${NC}"
        for a in "${MISSING_ACTIONS[@]}"; do
            echo "  - $a"
        done
    fi

    if [ ${#WARN_ACTIONS[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}${BOLD}=== A CONFIGURER / DEMARRER ===${NC}"
        for a in "${WARN_ACTIONS[@]}"; do
            echo "  - $a"
        done
    fi

    echo ""
    if [ "$MISSING" -eq 0 ] && [ "$WARN" -eq 0 ]; then
        echo -e "${GREEN}${BOLD}OK : ton environnement est pret pour le projet Tetouan !${NC}"
        echo "Tu peux lancer :"
        echo "  python3 main.py --kafka --cycles 1"
    elif [ "$MISSING" -eq 0 ]; then
        echo -e "${YELLOW}${BOLD}Tout est installe, il reste a demarrer/configurer les services.${NC}"
        echo "Verifie la liste 'A CONFIGURER / DEMARRER' ci-dessus."
    else
        echo -e "${RED}${BOLD}Installe d'abord ce qui est dans la liste 'A INSTALLER' ci-dessus.${NC}"
        echo "Puis relance : ${BOLD}./scripts/check_env.sh${NC}"
    fi
    echo ""
}

# ============================================================================
# MAIN
# ============================================================================
echo ""
echo -e "${CYAN}${BOLD}#####################################################${NC}"
echo -e "${CYAN}${BOLD}# Verification environnement - Big Data Tetouan      #${NC}"
echo -e "${CYAN}${BOLD}# (kafka, hadoop, spark, python, mongodb)            #${NC}"
echo -e "${CYAN}${BOLD}#####################################################${NC}"
echo -e "${DIM}  Hostname : $(hostname)${NC}"
echo -e "${DIM}  User     : $(whoami)${NC}"
echo -e "${DIM}  Date     : $(date)${NC}"

check_system
check_network
check_java
check_python
check_hadoop
check_spark
check_kafka
check_mongo
print_summary

# code de sortie : 0 si tout OK, 1 si il manque des choses
if [ "$MISSING" -gt 0 ]; then
    exit 1
elif [ "$WARN" -gt 0 ]; then
    exit 2
else
    exit 0
fi
