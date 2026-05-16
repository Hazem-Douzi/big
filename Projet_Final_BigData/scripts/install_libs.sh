#!/usr/bin/env bash
#
# install_libs.sh — Installe TOUTES les librairies Python du projet
#                   en une seule commande.
#
# Lance ceci APRES avoir installe Python 3 et pip via :
#   sudo apt install -y python3 python3-pip python3-venv
#
# Usage :
#   chmod +x scripts/install_libs.sh
#   ./scripts/install_libs.sh           # installe tout dans le user pip
#   ./scripts/install_libs.sh --venv    # cree d'abord un venv et installe dedans
#   ./scripts/install_libs.sh --with-dl # ajoute torch (~2 Go) pour les LSTM
#
set -e

# ============================================================================
# OPTIONS
# ============================================================================
USE_VENV=0
WITH_DL=0
for arg in "$@"; do
    case "$arg" in
        --venv)    USE_VENV=1 ;;
        --with-dl) WITH_DL=1 ;;
        -h|--help)
            echo "Usage : $0 [--venv] [--with-dl]"
            echo "  --venv      cree un venv ./venv et installe dedans"
            echo "  --with-dl   ajoute torch (deep learning, ~2 Go)"
            exit 0
            ;;
    esac
done

GREEN='\033[1;32m'; YELLOW='\033[1;33m'; CYAN='\033[1;36m'; NC='\033[0m'

# ============================================================================
# VERIFS PRELIMINAIRES
# ============================================================================
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERREUR : python3 introuvable. Installe-le d'abord :"
    echo "  sudo apt install -y python3 python3-pip python3-venv"
    exit 1
fi

if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "ERREUR : pip introuvable. Installe-le d'abord :"
    echo "  sudo apt install -y python3-pip"
    exit 1
fi

# ============================================================================
# CREATION DU VENV (optionnel)
# ============================================================================
if [ "$USE_VENV" -eq 1 ]; then
    echo -e "${CYAN}=== Creation d'un environnement virtuel ./venv ===${NC}"
    if [ ! -d venv ]; then
        python3 -m venv venv
    fi
    # shellcheck disable=SC1091
    source venv/bin/activate
    echo "venv active : $(which python3)"
fi

PIP="python3 -m pip"

echo -e "${CYAN}=== Mise a jour de pip ===${NC}"
$PIP install --upgrade pip

# ============================================================================
# LIBRAIRIES OBLIGATOIRES
# ============================================================================
echo -e "${CYAN}=== Installation des librairies obligatoires ===${NC}"
$PIP install \
    "kafka-python==2.0.2" \
    "numpy==1.26.4" \
    "pandas==2.2.2" \
    "pyspark==3.5.1" \
    "pymongo==4.7.2" \
    "scikit-learn==1.4.2" \
    "statsmodels==0.14.2" \
    "matplotlib==3.8.4" \
    "folium==0.16.0" \
    "feedparser==6.0.11" \
    "requests==2.32.3" \
    "faker==25.0.0"

# ============================================================================
# LIBRAIRIES OPTIONNELLES "LEGERES"
# ============================================================================
echo -e "${CYAN}=== Installation des librairies optionnelles legeres ===${NC}"
$PIP install \
    "streamlit==1.35.0" \
    "wordcloud==1.9.3" \
    "plotly==5.22.0" \
    "seaborn==0.13.2"

# ============================================================================
# DEEP LEARNING (--with-dl)
# ============================================================================
if [ "$WITH_DL" -eq 1 ]; then
    echo -e "${CYAN}=== Installation de PyTorch (CPU only, ~600 Mo) ===${NC}"
    echo -e "${YELLOW}Cela peut prendre 5-10 min selon la connexion${NC}"
    $PIP install torch --index-url https://download.pytorch.org/whl/cpu
fi

# ============================================================================
# RECAP
# ============================================================================
echo ""
echo -e "${GREEN}=== Installation terminee ===${NC}"
echo ""
echo "Verification rapide des imports :"
python3 - <<'EOF'
import importlib
mods = [
    "kafka", "numpy", "pandas", "pyspark", "pymongo",
    "sklearn", "statsmodels", "matplotlib", "folium",
    "feedparser", "requests", "streamlit",
]
ok, ko = [], []
for m in mods:
    try:
        importlib.import_module(m)
        ok.append(m)
    except Exception as e:
        ko.append((m, str(e)))
print(f"  OK     : {len(ok)} modules")
print(f"  Echec  : {len(ko)} modules")
for m, err in ko:
    print(f"    - {m}: {err}")
EOF

if [ "$USE_VENV" -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}N'oublie pas d'activer le venv a chaque session :${NC}"
    echo "    source venv/bin/activate"
fi

echo ""
echo "Pour relancer la verification globale :"
echo "    ./scripts/check_env.sh"
