"""Configuration du collecteur high-tech (API GraphQL Magento d'encheres-domaine).

Projet INDÉPENDANT. Ne dépend d'aucun autre projet. Rejoue fidèlement la requête
publique du site sur des données par ailleurs publiées en open data (Etalab 2.0).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

BASE_URL = "https://encheres-domaine.gouv.fr"
GRAPHQL_URL = f"{BASE_URL}/gateway/magento/graphql/"
STORE = "default"

# Catégories HIGH-TECH : identifiant Magento -> libellé.
# category_uid attendu par l'API = base64 de l'identifiant (47 -> "NDc=").
CATEGORIES = {
    46: "High tech",
    47: "Informatique",
    48: "TV, Vidéo, Son",
    49: "Smartphones et téléphonie",
    50: "Photo",
    51: "Consoles et jeux vidéo",
    52: "Objets connectés",
}
CATEGORIE_PARENTE = 46
DEFAULT_CATEGORIES = [47, 48, 49, 51, 52]  # tout sauf parent + Photo (souvent vide)

# Statuts de lot (13,14,15 = ventes à venir / en cours / etc.). Adaptable.
DEFAULT_LOT_STATUS = ["13", "14", "15", "1", "2", "3", "6", "8", "11", "19"]


def category_uid(categorie_id: int) -> str:
    return base64.b64encode(str(categorie_id).encode()).decode()


# --- Politesse réseau (rejeu fidèle du front) -------------------------------
USER_AGENT = os.environ.get(
    "SCRAPER_UA",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/26.5.2 Mobile/15E148 Safari/604.1",
)
# Empreinte de cache que le front joint à chaque appel. Peut se périmer ;
# surchargeable par variable d'env. Le collecteur fonctionne sans, mais le
# contrôle se réarme un peu plus souvent.
MAGENTO_CACHE_ID = os.environ.get("SCRAPER_CACHE_ID", "")

# Referer plausible : une page de catégorie high-tech du site.
PAGE_CATEGORIE = os.environ.get(
    "SCRAPER_REFERER",
    BASE_URL + "/categorie-de-produit/high-tech.html?lot_status=13%2C14%2C15&page=1",
)

REQUEST_TIMEOUT = 45
REQUEST_DELAY = 1.5        # délai minimum entre deux appels (s)
MAX_RETRIES = 4            # back-off 2,4,8,16 s
PAGE_SIZE = 60             # lots par appel (le front utilise 8, l'API accepte plus)
MAX_PAGES = 500

# --- Chemins ----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PAGES_DIR = DATA_DIR / "pages"          # cache brut des pages (reprise)
PORTAL_DATA_DIR = ROOT / "portal" / "data"
STATE_PATH = DATA_DIR / "state.json"
COTE_PATH = DATA_DIR / "cote.json"
