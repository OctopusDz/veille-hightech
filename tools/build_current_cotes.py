#!/usr/bin/env python3
"""Build the one-off, manually researched valuation snapshot for active lots.

This is deliberately not the future automated AI pipeline.  Values below are a
curated market snapshot based on the lot descriptions/photos and the sources
listed in SOURCES.  Running the script only formats that snapshot as JSON/CSV.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOTS_PATH = ROOT / "site" / "data" / "lots.json"
OUT_DIR = ROOT / "reports"
SITE_COTES_PATH = ROOT / "site" / "data" / "cotes.json"
SNAPSHOT_DATE = "2026-09-11"
AUCTION_FEE_RATE = 0.11


def money(value: float | int | None) -> float:
    """Round a monetary amount without losing cents from the 11% fee."""
    return round(float(value or 0), 2)


def vat_from_description(description: str | None) -> tuple[str, float | None]:
    """Only flag VAT when the lot description explicitly requires it.

    The current catalogue contains no such mention.  The strict rules below are
    intentionally conservative so a word containing the letters "tva" cannot
    create tax by accident.
    """
    text = description or ""
    if re.search(r"\bTVA\s+(?:comprise|incluse|non\s+applicable)\b", text, re.I):
        return "incluse_ou_non_applicable", None
    if not re.search(r"\b(?:TVA|prix\s+HT|hors\s+taxes?)\b", text, re.I):
        return "non_mentionnee", None

    rate_match = re.search(
        r"\bTVA\b[^.%]{0,35}?(\d{1,2}(?:[.,]\d+)?)\s*%",
        text,
        re.I,
    )
    rate = float(rate_match.group(1).replace(",", ".")) if rate_match else None
    return "mentionnee_a_ajouter", rate


SOURCES = {
    "lbc_dell_7490": {
        "title": "Dell Latitude 7490 i5 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/pc-portable-dell-latitude-7490-i5",
        "observed": "54 annonces; exemples 150 à 259 EUR selon état, RAM et garantie.",
    },
    "bm_e595": {
        "title": "Lenovo ThinkPad E595 Ryzen 5 16/256 — Back Market",
        "url": "https://www.backmarket.fr/fr-fr/p/lenovo-e595-15-ryzen-5-3500u-ghz-ssd-256-go-16-go/7c3dcefc-9ebf-48df-8d27-50ff8082cddb",
        "observed": "407 EUR reconditionné avec chargeur et garantie; la valeur entre particuliers ou en gros est inférieure.",
    },
    "lbc_iphone16": {
        "title": "iPhone 16 128 Go d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/telephones_objets_connectes/phone_brand%3Aapple%2Bphone_memory%3A128go%2Bphone_model%3Aiphone16",
        "observed": "1 476 annonces; majorité des exemples pertinents entre 460 et 600 EUR.",
    },
    "lbc_iphone13pm": {
        "title": "iPhone 13 Pro Max d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/telephones_objets_connectes/iphone13-pro-max",
        "observed": "Exemples courants autour de 320 à 500 EUR selon capacité, batterie et état.",
    },
    "lbc_iphone14pro": {
        "title": "iPhone 14 Pro d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/telephones_objets_connectes/phone_brand%3Aapple%2Bphone_model%3Aiphone14pro",
        "observed": "Marché actif mais très concurrentiel; prix fortement dépendant de la capacité, de la batterie et du verrouillage.",
    },
    "lbc_ipad10": {
        "title": "iPad 10e génération d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/tablettes_liseuses/ipad-10eme-generation",
        "observed": "313 annonces; exemples 64 Go autour de 250 à 280 EUR, 256 Go autour de 400 EUR.",
    },
    "lbc_ipadpro12": {
        "title": "iPad Pro 12,9 pouces Cellular d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/ipad-pro-12-9-cellular",
        "observed": "6 annonces dans la recherche ciblée; 6e génération vue entre 650 et 939 EUR.",
    },
    "lbc_ps5": {
        "title": "Console Sony PS5 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/consoles/console_brand%3Asony%2Bconsole_model%3Aps5",
        "observed": "Exemples de consoles autour de 330 à 400 EUR; annonces atypiques exclues.",
    },
    "lbc_ps5_bundles": {
        "title": "PS5 avec jeux et manettes — leboncoin",
        "url": "https://www.leboncoin.fr/ck/consoles/ps5-jeux-manettes",
        "observed": "3 462 annonces; packs comparables principalement autour de 400 à 500 EUR, davantage pour gros packs.",
    },
    "lbc_switch_oled": {
        "title": "Nintendo Switch OLED d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/consoles/nintendo-switch-oled",
        "observed": "5 132 annonces; console couramment affichée entre 150 et 210 EUR; packs avec jeux plus élevés.",
    },
    "lbc_xbox_x": {
        "title": "Xbox Series X avec deux manettes — leboncoin",
        "url": "https://www.leboncoin.fr/ck/consoles/xbox-serie-x-avec-2-manette",
        "observed": "513 annonces; exemples simples autour de 400 à 540 EUR.",
    },
    "lbc_xbox_s": {
        "title": "Xbox Series S d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/consoles/console_brand%3Amicrosoft%2Bconsole_model%3Axboxseriess%2Bvideo_game_type%3Aconsole",
        "observed": "3 798 annonces; exemples pertinents autour de 170 à 230 EUR.",
    },
    "lbc_gopro10": {
        "title": "GoPro Hero 10 Black d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/gopro-10-black",
        "observed": "412 annonces; nombreux exemples autour de 180 à 250 EUR; accessoires valorisés séparément.",
    },
    "lbc_fuji_xt20": {
        "title": "Fujifilm X-T20 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/fujifilm-x-t20",
        "observed": "66 annonces; boîtier et kit 18-55 très dispersés, exemples pertinents autour de 450 à 800 EUR.",
    },
    "lbc_sony_a6000": {
        "title": "Sony Alpha 6000 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/sony-alpha-6000",
        "observed": "135 annonces; kit 16-50 généralement affiché autour de 390 à 450 EUR.",
    },
    "lbc_ddj_rev7": {
        "title": "Pioneer DDJ-REV7 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/ddj-rev7",
        "observed": "22 annonces; contrôleur autour de 1 300 à 1 750 EUR, flight-case seul autour de 220 à 250 EUR.",
    },
    "lbc_marshall": {
        "title": "Marshall Stanmore d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/enceinte-marshall-stanmore",
        "observed": "109 annonces; versions I/II en bon état généralement autour de 150 à 220 EUR.",
    },
    "lbc_xiaomi_4k": {
        "title": "Xiaomi Mi Laser Projector 150 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/xiaomi-mi-laser",
        "observed": "28 annonces; 4K fonctionnel souvent affiché autour de 700 à 1 200 EUR; pour pièces vu à 180 EUR.",
    },
    "lbc_aruba": {
        "title": "Matériel Aruba d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/accessoires_informatique/aruba/p-3",
        "observed": "552 annonces; 2530-24G PoE+ vu à 70-131 EUR et 2920-48G à 110 EUR.",
    },
    "lbc_jbl": {
        "title": "JBL Charge 5 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/jbl-charge-5",
        "observed": "590 annonces; la majorité des exemples pertinents est autour de 80 à 120 EUR.",
    },
    "lbc_sony_xm4": {
        "title": "Sony WH-1000XM4 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/casque-sony-wh-1000xm4",
        "observed": "250 annonces; exemples principalement autour de 120 à 180 EUR.",
    },
    "lbc_g435": {
        "title": "Logitech G435 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/casque-g435",
        "observed": "45 annonces; majorité autour de 20 à 35 EUR, dont une annonce marquée vendue à 25 EUR.",
    },
    "lbc_macbook_m1": {
        "title": "MacBook Air M1 A2337 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/macbook-air-a2337",
        "observed": "95 annonces; fonctionnel souvent 350 à 560 EUR, pour pièces fréquemment 70 à 270 EUR.",
    },
}


# Politique prudente demandée : tout iPhone est valorisé comme iCloud/FMI ON,
# sauf si l'annonce affirme explicitement qu'il est fonctionnel ET non bloqué.
# Aucune des annonces ci-dessous ne réunit ces deux preuves. Un seul contrôle
# réel a été communiqué (iPhone 12 du lot 338443) ; les autres lignes sont donc
# clairement marquées comme hypothèses et non comme résultats de vérification.
def assumed_icloud_on(device):
    return {
        "device": device,
        "imei_suffix": None,
        "find_my_iphone": "ON",
        "verification_basis": "assumed",
        "checked_on": None,
        "source": "Règle prudente demandée — aucun contrôle IMEI revendiqué",
        "valuation_effect": "Valeur pièces uniquement ; aucune valeur d'usage ni déblocage futur n'est supposé.",
    }


DEVICE_CHECKS = {
    "302000": [assumed_icloud_on("iPhone 16 128 Go")],
    "296119": [assumed_icloud_on("iPhone X ou XS, écran HS")],
    "336701": [assumed_icloud_on("10 iPhone du lot")],
    "340354": [assumed_icloud_on("7 iPhone du lot")],
    "314274": [assumed_icloud_on("iPhone 13 Pro Max, vitre arrière cassée")],
    "314267": [assumed_icloud_on("iPhone 13 Pro Max")],
    "304783": [assumed_icloud_on("6 iPhone du lot")],
    "306168": [assumed_icloud_on("5 iPhone du lot")],
    "308035": [assumed_icloud_on("15 iPhone du lot")],
    "309023": [assumed_icloud_on("iPhone 15 A3090")],
    "338443": [
        assumed_icloud_on("iPhone 11 Pro"),
        {
            "device": "iPhone 12 A2403",
            "imei_suffix": "4229",
            "find_my_iphone": "ON",
            "verification_basis": "verified",
            "checked_on": SNAPSHOT_DATE,
            "source": "IMEICheck.com — résultat communiqué par l'utilisateur",
            "valuation_effect": "Valeur pièces uniquement tant que le propriétaire d'origine ne retire pas le verrouillage d'activation.",
        },
    ],
    "343959": [assumed_icloud_on("iPhone 14 Pro")],
}


# id: (vente rapide du lot, recette normale après test/détail, confiance,
#      demande, délai min/max en jours, méthode, risques, sources)
VALUES: dict[str, tuple] = {}


def v(lot_id, quick, normal, confidence, demand, days, method, risks, sources):
    VALUES[str(lot_id)] = (
        quick, normal, confidence, demand, days[0], days[1], method, risks, sources
    )


for lot_id, qty in ((302468, 19), (302466, 30), (302464, 20)):
    v(lot_id, qty * 95, qty * 150, 68, "moyenne", (14, 75),
      "95 EUR/unité en sortie de lot; 150 EUR/unité testée et vendue séparément.",
      "Chargeurs absents; état fonctionnel non garanti; modèle peu présent sur leboncoin.",
      ["lbc_dell_7490"])

v(302462, 1600, 2350, 74, "moyenne", (14, 60),
  "Mélange de 11 Latitude à 130-210 EUR testés, plus 8 docks; décote de lot.",
  "Répartition exacte 7400/7490/7480/E7470 et état batteries inconnus.", ["lbc_dell_7490"])
v(302459, 1000, 1800, 61, "faible", (30, 150),
  "Somme des valeurs par modèle avec forte décote de gros et d'obsolescence.",
  "Références PoE/non-PoE ambiguës; matériel non présenté comme testé; acheteurs spécialisés.", ["lbc_aruba"])
v(302453, 120, 300, 58, "faible", (45, 180),
  "Anciennes bornes 802.11n valorisées 4-11 EUR/unité selon vente en bloc ou détail.",
  "AP-105 obsolètes, alimentations absentes, configuration entreprise potentiellement bloquante.", ["lbc_aruba"])
v(302452, 500, 800, 66, "faible", (30, 120),
  "50 EUR/unité en lot; 70-90 EUR/unité testée avec chargeur.",
  "Machines anciennes à disque dur mécanique; batteries et RAM non précisées.", ["lbc_dell_7490"])
for lot_id, qty in ((302451, 14), (302450, 13), (302449, 10), (302446, 11), (302443, 20)):
    v(lot_id, qty * 45, qty * 75, 67, "faible", (30, 120),
      "45 EUR/unité en lot; 75 EUR/unité après test et nettoyage.",
      "Core i3 de génération non précisée, HDD 500 Go, batterie inconnue.", ["lbc_dell_7490"])
v(302442, 720, 1020, 70, "moyenne", (14, 60),
  "120 EUR/unité en lot; 170 EUR/unité testée avec chargeur et sacoche.",
  "État batterie et génération exacte du Core i3 à confirmer.", ["lbc_dell_7490"])
for lot_id, qty in ((302440, 17), (302439, 20), (302436, 11), (302434, 19), (302433, 16), (302432, 10)):
    v(lot_id, qty * 130, qty * 180, 70, "moyenne", (14, 75),
      "130 EUR/unité en lot; 180 EUR/unité testée avec chargeur/sacoche.",
      "État batteries non documenté; forte quantité du même modèle sur le marché local.", ["lbc_dell_7490"])
v(302437, 2300, 3150, 68, "moyenne", (14, 75),
  "110 EUR/unité en lot; 150 EUR/unité testée pour le C40-H-115.",
  "Génération plus ancienne et état batteries non documenté.", ["lbc_dell_7490"])
v(302420, 3500, 6000, 58, "faible", (45, 180),
  "Valorisation moyenne 60-100 EUR par tour selon configuration, avec décote logistique.",
  "CPU/RAM/stockage non détaillés, câbles absents, transport de 59 unités.", ["bm_e595"])
v(338394, 120, 220, 69, "moyenne", (14, 60),
  "Valeur d'une X1030 non testée avec petit défaut mécanique, contre une revente testée.",
  "Batterie et moteur non testés; vis de guidon manquante; transport contraignant.", [])
v(300850, 1800, 3000, 56, "faible", (45, 240),
  "Plateforme M210, Cendence, écran, batteries et valise; décote forte car sans caméra/payload récent.",
  "Ancienne plateforme entreprise, batteries TB55 vieillissantes, aucune caméra Zenmuse listée, marché étroit.", [])
v(297104, 250, 420, 70, "forte", (7, 30),
  "PS5 et deux manettes dominent la valeur; TV LG endommagée presque sans valeur.",
  "PS5 non testée et sans câble; TV rayée et pieds défectueux.", ["lbc_ps5", "lbc_ps5_bundles"])
v(297230, 220, 350, 66, "moyenne", (14, 60),
  "PS4, deux manettes, home-cinéma et 17 jeux anciens valorisés séparément.",
  "Jeux de plateformes différentes; TV ancienne sans télécommande.", ["lbc_ps5_bundles"])
v(324131, 300, 520, 67, "moyenne", (14, 60),
  "PS4, Xbox One S et TV 55 pouces, avec décote de lot encombrant.",
  "Deux consoles non testées; TV sans télécommande; enlèvement local.", ["lbc_ps5_bundles", "lbc_xbox_s"])
v(324273, 280, 500, 64, "moyenne", (14, 75),
  "Deux PS4 et deux manettes représentent l'essentiel de la valeur.",
  "Consoles non testées; TV rayée et encombrante.", ["lbc_ps5_bundles"])
v(324364, 150, 260, 68, "moyenne", (14, 60),
  "PS4 avec manette; TV décotée pour défaut de dalle.",
  "Console non testée; ligne verticale de pixels sur la TV.", ["lbc_ps5_bundles"])
v(324538, 170, 300, 67, "moyenne", (14, 60),
  "PS4, deux manettes et casque; TV ancienne fortement décotée.",
  "Ensemble non testé, câble console absent, TV rayée.", ["lbc_ps5_bundles"])
v(297974, 400, 800, 54, "moyenne", (21, 90),
  "Écran gaming, tour inconnue, manette Astro C40, disques LaCie et petit matériel.",
  "CPU/RAM de la tour inconnus; tout est non testé; nombreuses petites pièces lentes à écouler.", [])
v(302000, 105, 180, 58, "moyenne", (21, 90),
  "iPhone 16 valorisé uniquement comme donneur de pièces sous hypothèse iCloud ON; 5-10 EUR pour la batterie externe.",
  "Aucune valeur d'usage: fonctionnement, authenticité des pièces, batterie et état interne inconnus.", ["lbc_iphone16"])
v(296119, 160, 300, 48, "moyenne", (30, 150),
  "Valeur pièces du MacBook et des trois iPad mini; l'iPhone X/XS écran HS est aussi limité aux pièces sous hypothèse iCloud ON.",
  "Écrans HS, modèles/capacités incomplets, aucun chargeur, tout non testé; aucune valeur d'usage pour l'iPhone.", ["lbc_macbook_m1"])
v(324620, 180, 340, 59, "moyenne", (14, 75),
  "AirPods Pro, deux Jabra Elite 5 et deux anciennes GoPro valorisés après test.",
  "Authenticité, batteries et fonctionnement non vérifiés.", ["lbc_gopro10"])
v(340395, 600, 950, 78, "moyenne", (21, 120),
  "Environ 21 EUR/unité pour écoulement en lot; 34 EUR/unité en ventes séparées.",
  "28 unités non testées; risque de retours; concurrence élevée malgré emballages.", ["lbc_g435"])
v(311011, 120, 180, 80, "moyenne", (7, 30),
  "Enceinte visuellement proche d'une Stanmore, annoncée fonctionnelle, avec défaut cosmétique.",
  "Version exacte non inscrite dans l'annonce; cuir abîmé.", ["lbc_marshall"])
v(341436, 100, 220, 55, "faible", (30, 120),
  "Somme prudente du Sony GTK, des éléments LG et des petites enceintes.",
  "Tout non testé, câbles LG absents, ensemble hétérogène et encombrant.", ["lbc_jbl"])
v(306147, 180, 350, 46, "moyenne", (21, 90),
  "RTX 2060 et disque 1 To donnent une valeur plancher; bonus si configuration complète correcte.",
  "CPU, RAM, carte mère et alimentation inconnus; PC poussiéreux et non testé.", [])
v(303750, 1200, 1650, 83, "moyenne", (14, 60),
  "DDJ-REV7 décoté car non testé, flight-case et casque inclus.",
  "Contrôleur non testé; réparation potentiellement chère; enlèvement spécialisé.", ["lbc_ddj_rev7"])
v(304500, 20, 80, 25, "faible", (60, 240),
  "Valeur de récupération d'un ancien ensemble Tandberg non inventorié.",
  "Modèles, complétude et fonctionnement inconnus; technologie probablement obsolète.", [])
v(299305, 3200, 6200, 58, "moyenne", (30, 180),
  "24 E595, deux Latitude 5300, 10 barrettes 16 Go et disques, avec forte décote non-testé/gros.",
  "Configurations E595 non précisées; 26 portables non testés; travail de tri et d'effacement.", ["bm_e595", "lbc_dell_7490"])
v(319895, 200, 360, 67, "moyenne", (21, 90),
  "Douze rééditions Beatles, pour la plupart scellées, plus photo de faible valeur.",
  "Pressages/années exacts inconnus; état des pochettes à vérifier.", [])
v(315491, 260, 400, 74, "forte", (7, 30),
  "PS5, DualSense camouflage et trois jeux de sport anciens.",
  "Fonctionnement inconnu; jeux annuels à faible valeur résiduelle.", ["lbc_ps5", "lbc_ps5_bundles"])
v(322440, 60, 130, 75, "faible", (21, 90),
  "Deux Xbox 360 S 4 Go, deux manettes et câblage.",
  "Faible stockage, consoles anciennes, état seulement décrit comme usage.", [])
v(322018, 250, 380, 74, "forte", (7, 30),
  "PS5 avec boîte, câbles et Modern Warfare III.",
  "État de fonctionnement inconnu; manette non explicitement listée.", ["lbc_ps5", "lbc_ps5_bundles"])
v(351136, 170, 260, 72, "forte", (7, 30),
  "AirPods 3 et AirPods Pro 2 en parfait état annoncé, avec boîtes.",
  "Authenticité et santé des batteries à vérifier; description des AirPods 3 contient des fonctions incohérentes.", [])
v(322431, 80, 180, 48, "faible", (30, 120),
  "DJI Phantom ancien avec radiocommande, valorisé surtout après test.",
  "Version/compatibilité de la radiocommande ambiguë, batterie et chargeur non listés.", [])
v(336780, 100, 250, 43, "faible", (30, 150),
  "Trois Kindle, sept casques et quatre montres inconnues vendus après tri.",
  "Modèles partiels, aucun chargeur et tout non testé.", ["lbc_sony_xm4"])
v(319661, 20, 40, 80, "faible", (30, 120),
  "Petit AED Trainer de formation, pas un défibrillateur médical opérationnel.",
  "Marché de niche; faible valeur unitaire neuve.", [])
v(336845, 200, 420, 62, "moyenne", (21, 90),
  "Canon 450D avec deux objectifs, Sony HDR-PJ540 et Lumix TZ10.",
  "Tout non testé, sans chargeurs; batteries anciennes.", ["lbc_sony_a6000"])
v(348147, 160, 350, 58, "faible", (30, 150),
  "Rollei 35 domine la valeur, complété par Nikon F65, Yashica et flash.",
  "Tout non testé; cellule, obturateur et optiques à contrôler.", [])
v(336701, 350, 750, 55, "moyenne", (45, 180),
  "Dix iPhone valorisés exclusivement comme donneurs de pièces sous hypothèse iCloud ON; décote supplémentaire pour vente en lot non testé.",
  "Aucune valeur d'usage ou de déblocage; capacités, batteries, authenticité et état des composants inconnus; mini-réplique sans valeur.", ["lbc_iphone16", "lbc_iphone14pro", "lbc_iphone13pm"])
v(336751, 350, 750, 48, "moyenne", (30, 150),
  "Dix Android de générations variées, A54/A55/Edge 30 étant les principaux contributeurs.",
  "Tout non testé, aucune capacité, aucun chargeur, risque de comptes/verrouillages.", [])
v(288890, 450, 850, 54, "forte", (21, 90),
  "Deux iPad 10, iPad 9, Tab S4, Lenovo M10 et P11 après décote non-testé.",
  "Capacités inconnues, aucun chargeur, activation et batteries non vérifiées.", ["lbc_ipad10"])
v(340354, 220, 480, 56, "moyenne", (45, 180),
  "Sept iPhone valorisés exclusivement comme donneurs de pièces sous hypothèse iCloud ON, avec décote de lot non testé.",
  "Aucune valeur d'usage ou de déblocage; capacités, batteries et état des composants inconnus; aucun chargeur.", ["lbc_iphone14pro", "lbc_iphone13pm"])
v(340341, 450, 900, 49, "forte", (21, 120),
  "S25 et S22 portent l'essentiel de la valeur; six smartphones milieu/entrée de gamme.",
  "Tout non testé; authenticité du S25, capacités, comptes et IMEI à contrôler.", [])
v(336669, 750, 1450, 49, "forte", (21, 120),
  "Dix tablettes, dont iPad récents et Air 5, valorisées après test individuel.",
  "Modèle 'iPad A16' ambigu, capacités et activation inconnues, aucun chargeur.", ["lbc_ipad10", "lbc_ipadpro12"])
v(340268, 650, 1300, 44, "forte", (21, 120),
  "Sept iPad; deux Pro non identifiés représentent la plus grande incertitude.",
  "Générations/capacités des Pro et Air inconnues; activation, batteries et écrans non testés.", ["lbc_ipad10", "lbc_ipadpro12"])
v(328386, 1000, 2300, 38, "forte", (30, 150),
  "Cinq portables récents/premium, dont MacBook Pro A3401 et Air A3114, très décotés car non testés.",
  "Spécifications/capacités inconnues, aucun chargeur, activation Apple et pannes possibles.", ["lbc_macbook_m1"])
v(300877, 350, 800, 58, "faible", (45, 180),
  "M806 annoncé en marche; décote forte pour manutention, transport et clientèle professionnelle.",
  "Compteur pages, consommables et options non indiqués; machine très lourde.", [])
v(300859, 600, 1200, 56, "faible", (45, 180),
  "30 OfficeJet 8210/8100 annoncées en marche, 20-40 EUR/unité selon canal.",
  "Annonce les appelle LaserJet à tort; état des têtes/cartouches inconnu; trois palettes à transporter.", [])
v(314403, 100, 150, 78, "moyenne", (14, 45),
  "iPad 7 Cellular 32 Go sans chargeur ni boîte.",
  "État/batterie non qualifiés; activation à vérifier.", ["lbc_ipad10"])
v(314391, 60, 100, 72, "faible", (21, 90),
  "Ancienne Intuos Pro Medium PTH-651.",
  "Stylet et câbles non explicitement listés; génération ancienne.", [])
v(314385, 90, 140, 80, "moyenne", (14, 60),
  "Magic Keyboard 12,9 pouces 2021 avec boîte.",
  "État cosmétique et disposition clavier à confirmer.", ["lbc_ipadpro12"])
v(314379, 600, 800, 72, "forte", (14, 45),
  "iPad Pro 12,9 M2 Cellular avec boîte; valeur médiane faute de capacité indiquée.",
  "Capacité de stockage, batterie et présence du chargeur non indiquées.", ["lbc_ipadpro12"])
for lot_id in (314372, 314336, 314296):
    v(lot_id, 110, 170, 79, "moyenne", (14, 45),
      "iPad 7 Cellular 32 Go en bon état, boîte/clavier/chargeur inclus.",
      "Batterie et activation à vérifier; clavier probablement tiers.", ["lbc_ipad10"])
v(314295, 30, 60, 82, "faible", (30, 120),
  "Time Capsule A1409 2 To fonctionnelle supposée, avec cordon.",
  "Produit réseau 2012 obsolète; disque dur ancien.", [])
v(314274, 55, 110, 62, "moyenne", (21, 90),
  "iPhone 13 Pro Max valorisé uniquement pour pièces sous hypothèse iCloud ON, avec décote pour vitre arrière cassée et écran rayé.",
  "Aucune valeur d'usage; capacité, batterie, Face ID et état des composants récupérables inconnus.", ["lbc_iphone13pm"])
v(314267, 95, 180, 64, "moyenne", (21, 90),
  "Malgré le bon état annoncé, l'iPhone 13 Pro Max reste valorisé uniquement pour pièces: l'annonce ne confirme ni fonctionnement ni absence de blocage.",
  "Aucune valeur d'usage ou de déblocage; capacité, santé batterie et authenticité des composants inconnues.", ["lbc_iphone13pm"])
v(314363, 100, 150, 78, "moyenne", (14, 45),
  "iPad 7 Cellular 32 Go avec clavier, sans chargeur ni boîte.",
  "Batterie et activation à vérifier.", ["lbc_ipad10"])
v(304783, 200, 450, 48, "moyenne", (60, 240),
  "Les six iPhone sont limités aux pièces sous hypothèse iCloud ON; les 18 autres téléphones non testés sont valorisés après tri avec forte décote.",
  "Nombreux écrans/coques cassés, certains appareils annoncés bloqués, pannes et comptes Android possibles; travail de tri important.", ["lbc_iphone13pm", "lbc_iphone14pro"])
v(306168, 260, 560, 50, "moyenne", (45, 180),
  "Les cinq iPhone, y compris 16 Pro Max/16/14, sont valorisés uniquement pour pièces sous hypothèse iCloud ON; le Galaxy A15 reste non testé.",
  "Aucune valeur d'usage pour les iPhone; écrans à revoir, capacités, batteries, authenticité et état interne inconnus.", ["lbc_iphone16", "lbc_iphone14pro"])
v(308035, 550, 1250, 45, "moyenne", (60, 300),
  "Les quinze iPhone sont valorisés exclusivement comme donneurs de pièces sous hypothèse iCloud ON; S23 et Redmi restent fortement décotés non testés.",
  "Plusieurs écrans/coques endommagés, modèles iPhone 17/A3293 à authentifier, pièces potentiellement non récupérables et démontage très chronophage.", ["lbc_iphone16", "lbc_iphone14pro", "lbc_iphone13pm"])
v(176842, 110, 170, 72, "forte", (7, 30),
  "Switch OLED non testée; valeur basse faute d'accessoires explicitement confirmés.",
  "Fonctionnement, dock, chargeur et Joy-Con à confirmer.", ["lbc_switch_oled"])
v(308277, 170, 260, 76, "forte", (7, 30),
  "Switch OLED avec manette Pro, ensemble non testé.",
  "État écran, Joy-Con, dock et batterie à contrôler.", ["lbc_switch_oled"])
v(308310, 180, 320, 70, "forte", (7, 45),
  "Switch standard et huit jeux, sans accessoires clairement listés.",
  "Ensemble non testé; titres/boîtes/accessoires à confirmer.", ["lbc_switch_oled"])
v(308750, 600, 950, 71, "forte", (14, 75),
  "PS5, trois manettes, quinze jeux PS5, PS TV et casque, après décote non-testé.",
  "Tout non testé; titres des jeux non détaillés; vente séparée nécessaire pour atteindre la cote normale.", ["lbc_ps5_bundles"])
v(309602, 270, 400, 78, "forte", (7, 30),
  "Xbox Series X récente avec deux manettes et chargeur, non testée.",
  "Fonctionnement et état des manettes non vérifiés.", ["lbc_xbox_x"])
v(309616, 120, 200, 76, "forte", (7, 30),
  "Xbox Series S avec manette et casque, non testée.",
  "Capacité 512 Go/1 To non indiquée; fonctionnement inconnu.", ["lbc_xbox_s"])
v(309654, 250, 360, 78, "forte", (7, 30),
  "Xbox Series X avec manette, casque Sony et câbles.",
  "Fonctionnement non testé; une seule manette.", ["lbc_xbox_x"])
v(309881, 150, 300, 39, "moyenne", (30, 120),
  "Deux Apple Watch inconnues, JBL Flip 6 et mini-imprimante LG.",
  "Modèles/tailles des montres inconnus, boîtes parfois vides, tout non testé.", ["lbc_jbl"])
v(304101, 300, 420, 79, "forte", (7, 30),
  "PS5 Slim CFI-2016 et deux manettes, non testées.",
  "Fonctionnement et dérive des sticks non vérifiés.", ["lbc_ps5", "lbc_ps5_bundles"])
v(310961, 220, 420, 62, "moyenne", (21, 90),
  "Écrans BenQ XL2540K/AOC 24G1, portable Asus ancien et disque 1 To.",
  "Tout non testé; configuration du portable inconnue.", [])
v(311309, 180, 350, 60, "forte", (21, 90),
  "Galaxy Tab A9+ SM-X210, iPad 10 A2696 et deux caméras génériques.",
  "Capacités, activation et fonctionnement non testés; caméras mal identifiées.", ["lbc_ipad10"])
v(309023, 45, 90, 58, "moyenne", (21, 90),
  "iPhone 15 valorisé uniquement comme donneur de pièces sous hypothèse iCloud ON; aucun déblocage futur supposé.",
  "Non testé et potentiellement bloqué selon l'annonce; capacité, batterie, authenticité et état interne inconnus.", ["lbc_iphone16"])
v(317922, 700, 1800, 46, "moyenne", (60, 240),
  "58 casques dont plusieurs Bose/Sony haut de gamme, deux écouteurs, baladeurs et 30 vinyles.",
  "Tout non testé; batteries/coussinets; inventaire textuel possiblement imprécis; très nombreuses ventes.", ["lbc_sony_xm4"])
v(318200, 350, 750, 52, "moyenne", (45, 180),
  "Neuf JBL dont Charge 4/5, treize enceintes entrée de gamme et trois baladeurs.",
  "Modèles JBL incomplets, batteries et fonctionnement non testés.", ["lbc_jbl"])
v(318313, 1500, 3500, 42, "moyenne", (90, 300),
  "22 iPad, 10 autres tablettes, 14 Kindle et 8 Kobo, selon valeurs par numéro de modèle.",
  "55 appareils non testés, activation/batteries/écrans inconnus; vente et effacement très chronophages.", ["lbc_ipad10", "lbc_ipadpro12"])
v(318327, 300, 600, 61, "forte", (21, 90),
  "PS5, Switch, 3DS XL, 3DS, Wii et deux jeux.",
  "Tout non testé; accessoires et chargeurs non détaillés.", ["lbc_ps5", "lbc_switch_oled"])
v(318370, 250, 550, 49, "moyenne", (45, 180),
  "Projecteur Epson, micro AT2035, cinq appareils photo, caméscope et divers.",
  "Tout non testé; objets hétérogènes; nombreuses ventes de faible montant.", ["lbc_sony_a6000"])
v(318430, 500, 1050, 41, "forte", (45, 180),
  "Six portables dont deux MacBook Air 2020/M1 et un Pro, plus accessoires.",
  "Tout non testé; spécifications et activation inconnues; seul une partie a des chargeurs.", ["lbc_macbook_m1"])
v(318523, 450, 950, 39, "forte", (45, 180),
  "Cinq portables dont MacBook Air M1 et Asus récent, plus petite tour/écran/tablette.",
  "Tout non testé; modèle du second MacBook Air et configurations inconnus.", ["lbc_macbook_m1"])
v(318544, 850, 1900, 44, "forte", (60, 240),
  "Treize portables hétérogènes, dont T14, T480s, HP 855 G7, Surface 1960 et MacBook.",
  "Tout non testé; configurations/activation inconnues; travail de tri important.", ["lbc_dell_7490", "lbc_macbook_m1"])
v(336599, 120, 280, 48, "moyenne", (30, 120),
  "iPad 9 A2602, ancienne Samsung/Logicom, Olympus E-P2 et petite enceinte.",
  "Tout non testé; référence Samsung probablement mal saisie.", ["lbc_ipad10"])
v(282679, 320, 500, 84, "forte", (7, 30),
  "Switch OLED Splatoon complète, sept jeux et deux sacoches.",
  "Fonctionnement non explicitement garanti; titres des jeux à pondérer selon demande.", ["lbc_switch_oled"])
v(309638, 300, 380, 84, "forte", (7, 30),
  "PS5 complète en boîte avec manette et câbles.",
  "Modèle disque/digital et fonctionnement à vérifier.", ["lbc_ps5"])
v(84173, 250, 380, 82, "forte", (7, 30),
  "Switch complète, quatre Joy-Con et six jeux.",
  "Version de la Switch, dérive des Joy-Con et titres à vérifier.", ["lbc_switch_oled"])
v(309642, 300, 380, 84, "forte", (7, 30),
  "PS5 complète en boîte avec manette et câbles.",
  "Modèle disque/digital et fonctionnement à vérifier.", ["lbc_ps5"])
v(347811, 180, 250, 86, "forte", (7, 30),
  "GoPro Hero 10 et accessoires visibles.",
  "Batterie, étanchéité et liste exacte des accessoires à tester.", ["lbc_gopro10"])
v(347828, 500, 700, 83, "forte", (14, 45),
  "Fujifilm X-T20 avec objectif XF 18-55 f/2.8-4.",
  "Déclenchements, capteur, autofocus et état optique à vérifier.", ["lbc_fuji_xt20"])
v(347842, 300, 400, 86, "forte", (7, 30),
  "Sony A6000 et objectif kit 16-50 OSS.",
  "Déclenchements, capteur, autofocus et batterie à vérifier.", ["lbc_sony_a6000"])
v(303291, 350, 500, 64, "forte", (14, 45),
  "ProBook 450 G9 professionnel récent avec chargeur, valeur médiane faute de spécifications.",
  "CPU, RAM et SSD non indiqués; compte BIOS/entreprise et batterie à vérifier.", ["lbc_dell_7490"])
v(41076, 150, 220, 78, "moyenne", (14, 45),
  "IdeaPad Slim 3 Chromebook 14IAN8, 8/128 Go avec chargeur.",
  "État batterie et éventuelle gestion scolaire/entreprise à vérifier.", [])
v(126221, 140, 220, 65, "moyenne", (14, 60),
  "Asus M509D 8/512 Go avec chargeur, estimation médiane faute de CPU.",
  "Processeur exact, batterie et état écran non indiqués.", [])
v(338443, 35, 70, 68, "moyenne", (21, 90),
  "iPhone 12 contrôlé FMI ON et iPhone 11 Pro supposé iCloud ON: les deux sont valorisés uniquement comme donneurs de pièces.",
  "Aucune valeur d'usage ou de déblocage; capacité, batterie, écrans, cartes mères et autres composants récupérables restent inconnus.", ["lbc_iphone13pm"])
v(343959, 70, 160, 48, "moyenne", (30, 120),
  "iPhone 14 Pro valorisé uniquement pour pièces sous hypothèse iCloud ON; faible valeur prudente ajoutée pour le second téléphone non identifié.",
  "Modèle 'SAMSUNG ONE' incohérent; aucune valeur d'usage pour l'iPhone; capacités, batteries et fonctionnement inconnus.", ["lbc_iphone14pro"])
v(321714, 80, 170, 68, "faible", (30, 120),
  "Wii, PS3 Slim, DS Lite et casque filaire.",
  "Tout non testé; câbles PS3 absents; faible valeur unitaire.", [])
v(329193, 350, 750, 62, "moyenne", (21, 90),
  "Xiaomi Mi 4K Laser Projector 150, décoté comme non testé sans cordon.",
  "Panne laser/DMD coûteuse possible; télécommande et cordon absents/non listés.", ["lbc_xiaomi_4k"])
v(304620, 200, 500, 43, "faible", (60, 240),
  "Douze anciennes tours Acer, vingt alimentations et sept cartes graphiques anciennes.",
  "Configurations et fonctionnement inconnus; GPU 512 Mo obsolètes; logistique lourde.", [])
v(294796, 10000, 18000, 72, "moyenne", (45, 240),
  "100 E595 complets: 100 EUR/unité en sortie professionnelle, 180 EUR/unité testée/vendue.",
  "Très gros volume, pas d'OS, batteries à contrôler; recette normale exige 100 ventes et une garantie vendeur.", ["bm_e595"])
v(294805, 1200, 1900, 72, "moyenne", (30, 150),
  "11 L580 i5-8250U et un L570, environ 100 EUR/unité en lot et 155-165 EUR au détail.",
  "Pas d'OS; état des batteries/écrans à vérifier; volume de 12 unités.", ["lbc_dell_7490"])


def main() -> None:
    payload = json.loads(LOTS_PATH.read_text(encoding="utf-8"))
    lots = payload["lots"]
    active_ids = {str(lot["id"]) for lot in lots}
    missing = sorted(active_ids - VALUES.keys())
    extra = sorted(VALUES.keys() - active_ids)
    if missing or extra:
        raise SystemExit(f"Valuation coverage mismatch. missing={missing} extra={extra}")

    rows = []
    for lot in lots:
        lot_id = str(lot["id"])
        quick, normal, confidence, demand, dmin, dmax, method, risks, source_ids = VALUES[lot_id]
        current = lot.get("bid") if lot.get("bid") is not None else lot.get("price")
        current = money(current)
        auction_fees = money(current * AUCTION_FEE_RATE)
        vat_status, vat_rate = vat_from_description(lot.get("desc"))
        # Add VAT only when both its applicability and exact rate are explicit.
        # There is deliberately no guessed default rate.
        vat_amount = money((current + auction_fees) * vat_rate / 100) \
            if vat_status == "mentionnee_a_ajouter" and vat_rate is not None else 0.0
        purchase_total = money(current + auction_fees + vat_amount)
        rows.append({
            "id": lot_id,
            "sku": lot.get("sku"),
            "lot": lot.get("lot"),
            "name": lot.get("name"),
            "auction_url": lot.get("url"),
            "auction_end": lot.get("end"),
            "current_auction_eur": current,
            "auction_fee_rate_percent": money(AUCTION_FEE_RATE * 100),
            "auction_fees_eur": auction_fees,
            "vat_status": vat_status,
            "vat_rate_percent": vat_rate,
            "vat_eur": vat_amount,
            "purchase_total_eur": purchase_total,
            "photo_count": len(lot.get("photos") or []),
            "quick_sale_lot_eur": quick,
            "normal_resale_gross_eur": normal,
            "quick_margin_before_other_costs_eur": money(quick - purchase_total),
            "normal_margin_before_other_costs_eur": money(normal - purchase_total),
            "confidence_percent": confidence,
            "demand": demand,
            "estimated_sale_days_min": dmin,
            "estimated_sale_days_max": dmax,
            "valuation_method": method,
            "main_risks": risks,
            "device_checks": DEVICE_CHECKS.get(lot_id, []),
            "source_ids": source_ids,
            "source_titles": [SOURCES[source_id]["title"] for source_id in source_ids],
            "source_urls": [SOURCES[source_id]["url"] for source_id in source_ids],
        })

    OUT_DIR.mkdir(exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = {
        "snapshot_date": SNAPSHOT_DATE,
        "generated_at": generated_at,
        "currency": "EUR",
        "lot_count": len(rows),
        "photo_count": sum(row["photo_count"] for row in rows),
        "auction_fee_rate_percent": money(AUCTION_FEE_RATE * 100),
        "totals": {
            "current_auction_eur": money(sum(row["current_auction_eur"] for row in rows)),
            "auction_fees_eur": money(sum(row["auction_fees_eur"] for row in rows)),
            "vat_eur": money(sum(row["vat_eur"] for row in rows)),
            "purchase_total_eur": money(sum(row["purchase_total_eur"] for row in rows)),
            "quick_sale_lot_eur": money(sum(row["quick_sale_lot_eur"] for row in rows)),
            "normal_resale_gross_eur": money(sum(row["normal_resale_gross_eur"] for row in rows)),
        },
        "definitions": {
            "purchase_total_eur": "Prix d'enchère courant ou mise à prix + 11 % de frais d'enchère + TVA uniquement si son application et son taux sont explicitement indiqués dans la description.",
            "quick_sale_lot_eur": "Prix brut plausible pour céder rapidement le lot dans son état annoncé, sans garantie.",
            "normal_resale_gross_eur": "Recette brute plausible après contrôle, nettoyage et ventes séparées lorsque pertinent; transport, réparations, commissions de revente et temps de travail non déduits.",
            "quick_margin_before_other_costs_eur": "Cote de vente rapide moins le coût d'achat incluant les 11 % de frais d'enchère et l'éventuelle TVA explicitement indiquée.",
            "normal_margin_before_other_costs_eur": "Cote de revente normale moins le coût d'achat incluant les 11 % de frais d'enchère et l'éventuelle TVA explicitement indiquée.",
            "confidence_percent": "Confiance dans l'ordre de grandeur, pas probabilité de vente.",
            "apple_phone_policy": "Tout iPhone est supposé iCloud/Find My ON et valorisé uniquement pour pièces, sauf si la description affirme explicitement qu'il est fonctionnel et non bloqué.",
        },
        "limitations": [
            "Les frais d'enchère sont calculés au taux demandé de 11 % sur le prix courant. Aucune TVA n'est ajoutée sans mention explicite dans la description du lot.",
            "La mention iCloud/Find My ON affichée comme hypothèse prudente n'est pas un contrôle IMEI. Seul un statut explicitement marqué contrôlé provient d'un résultat communiqué.",
            "Les prix leboncoin relevés sont surtout des prix demandés, pas des prix de transaction certifiés.",
            "La date de mise en ligne et le délai réel de vente ne sont pas exposés de façon fiable pour chaque comparable; aucun délai n'est présenté comme une mesure leboncoin exacte.",
            "Les lots non testés, bloqués ou incomplets peuvent valoir nettement moins après contrôle.",
            "Les valeurs sont un instantané de marché, pas une garantie ni une expertise officielle.",
        ],
        "sources": SOURCES,
        "lots": rows,
    }

    json_path = OUT_DIR / f"cotes_lots_actifs_{SNAPSHOT_DATE}.json"
    csv_path = OUT_DIR / f"cotes_lots_actifs_{SNAPSHOT_DATE}.csv"
    json_output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    json_path.write_text(json_output, encoding="utf-8")
    SITE_COTES_PATH.write_text(json_output, encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0].keys()),
            delimiter=";",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["device_checks"] = json.dumps(row["device_checks"], ensure_ascii=False)
            csv_row["source_ids"] = ",".join(row["source_ids"])
            csv_row["source_titles"] = json.dumps(row["source_titles"], ensure_ascii=False)
            csv_row["source_urls"] = " | ".join(row["source_urls"])
            writer.writerow(csv_row)

    print(json_path)
    print(csv_path)
    print(SITE_COTES_PATH)
    print(f"{len(rows)} lots / {sum(row['photo_count'] for row in rows)} photos")


if __name__ == "__main__":
    main()
