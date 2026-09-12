#!/usr/bin/env python3
"""Build the one-off, manually researched valuation snapshot for active lots.

This is deliberately not the future automated AI pipeline.  Values below are a
curated market snapshot based on the lot descriptions/photos and the sources
listed in SOURCES.  Running the script only formats that snapshot as JSON/CSV.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOTS_PATH = ROOT / "site" / "data" / "lots.json"
OUT_DIR = ROOT / "reports"
SITE_COTES_PATH = ROOT / "site" / "data" / "cotes.json"
SNAPSHOT_DATE = "2026-09-12"
AUCTION_FEE_RATE = 0.11


def money(value: float | int | None) -> float:
    """Round a monetary amount without losing cents from the 11% fee."""
    return round(float(value or 0), 2)


def acquisition_at_bid(
    bid: float | int,
    fee_rate: float,
    vat_status: str,
    vat_rate: float | None,
) -> tuple[float, float, float]:
    """Return auction fees, explicit VAT and total cost for a hammer bid."""
    hammer = money(bid)
    fees = money(hammer * fee_rate)
    vat = money((hammer + fees) * vat_rate / 100) \
        if vat_status == "mentionnee_a_ajouter" and vat_rate is not None else 0.0
    return fees, vat, money(hammer + fees + vat)


def recommended_max_bid(
    quick_sale: float | int,
    confidence: float | int,
    fee_rate: float,
    vat_status: str,
    vat_rate: float | None,
) -> int:
    """Return a conservative hammer-price ceiling, before auction fees.

    The all-in acquisition budget is 50% to 75% of the quick-sale valuation,
    depending on confidence. This keeps a 25% minimum reserve for transport,
    testing, repairs, resale costs and work, with a larger reserve when the
    estimate is uncertain. Auction fees and explicit VAT are then removed so
    the displayed result is the bid amount the user can enter at auction.
    """
    bounded_confidence = min(100.0, max(0.0, float(confidence)))
    acquisition_ratio = 0.50 + bounded_confidence / 400
    divisor = 1 + fee_rate
    if vat_status == "mentionnee_a_ajouter" and vat_rate is not None:
        divisor *= 1 + vat_rate / 100
    raw_bid = float(quick_sale) * acquisition_ratio / divisor
    return max(0, math.floor(raw_bid / 5) * 5)


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
    "market_dynabook_c40": {
        "title": "Dynabook C40-H/C40-J d'occasion — Fnac et eBay",
        "url": "https://www.fnac.com/mp45752415/Dynabook-Toshiba-Satellite-Pro-C40-H-115-Intel-Core-i3-1005G1-1-2-GHz-Win-10-Familiale-64-bits-UHD-Graphics-8-Go-RAM-256-Go-SSD-14-1920-x-1080-Full-HD-Wi-Fi-5-bleu-fonce-noir-clavier/w-4",
        "observed": "C40-H-115 reconditionné testé à 149 EUR; C40-J i3 11e/8/256 d'occasion observé autour de 172 EUR avant transport. Relevé du 12/09/2026.",
    },
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
    "lbc_e595": {
        "title": "ThinkPad E595 Ryzen 5 3500U d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/ryzen-3500u",
        "observed": "E595 16/256 vu à 220 EUR et 8/256 à 245 EUR; prix demandés à l'unité, avant décote de gros. Relevé du 12/09/2026.",
    },
    "lbc_l580": {
        "title": "ThinkPad L580 i5-8250U d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/lenovo-thinkpad-l580",
        "observed": "Environ 140 à 250 EUR selon RAM, état et vendeur; plusieurs 16/256 particuliers autour de 200 à 230 EUR. Relevé du 12/09/2026.",
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
    "lbc_iphone_locked_parts": {
        "title": "iPhone bloqués et pour pièces — leboncoin",
        "url": "https://www.leboncoin.fr/ck/telephones_objets_connectes/bloque",
        "observed": "Comparables très dispersés: iPhone 13 Pro Max iCloud à 100 EUR, iPhone 15 Plus bloqué à 180 EUR et iPhone 17 bloqué autour de 450 à 600 EUR. Prix demandés, pas ventes certifiées. Relevé du 12/09/2026.",
    },
    "imeicheck_20260912": {
        "title": "Contrôles IMEI, liste noire et Find My — IMEICheck.com",
        "url": "https://imeicheck.com/imei-check",
        "observed": "21 IMEI iPhone publiés dans les annonces ont été contrôlés le 12/09/2026: 10 Find My OFF et 11 Find My ON. Les résultats sont datés et affichés appareil par appareil.",
    },
    "lbc_iphone13_current": {
        "title": "iPhone 13 et 13 Pro d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/recherche?category=17&text=iphone%2013&sort=time&order=desc",
        "observed": "Relevé trié par annonces récentes le 12/09/2026: iPhone 13 principalement autour de 185 à 230 EUR; 13 Pro autour de 235 à 320 EUR, avant décote pour écran cassé ou appareil non testé.",
    },
    "lbc_iphone12pro_current": {
        "title": "iPhone 12 Pro d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/telephones_objets_connectes/phone_brand%3Aapple%2Bphone_model%3Aiphone12pro",
        "observed": "Relevé du 12/09/2026: offres récentes généralement autour de 160 à 280 EUR; exemplaires pour pièces ou endommagés autour de 95 à 190 EUR.",
    },
    "lbc_iphone15_current": {
        "title": "iPhone 15 128 Go d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/recherche?category=17&text=iphone%2015%20128go&sort=time&order=desc",
        "observed": "Relevé trié par annonces récentes le 12/09/2026: nombreux iPhone 15 128 Go entre 320 et 490 EUR selon état, batterie et garantie.",
    },
    "lbc_iphone17pm_current": {
        "title": "iPhone 17 Pro Max d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/recherche?category=17&text=iphone%2017%20pro%20max&sort=time&order=desc",
        "observed": "Relevé trié par annonces récentes le 12/09/2026: 256 Go vu à 1 050 EUR, 512 Go à 1 400 EUR et 1 To à 1 359 EUR. Une forte décote reste appliquée au lot non testé.",
    },
    "ebay_iphone_locked_parts": {
        "title": "iPhone bloqués pour pièces — eBay France",
        "url": "https://www.ebay.fr/b/Iphone-bloque/bn_7006314156",
        "observed": "Offres actives pour appareils iCloud/HS, utilisées uniquement comme contrôle de valeur des composants récupérables. Relevé du 12/09/2026.",
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
    "lbc_ipad_parts": {
        "title": "iPad récents pour pièces — leboncoin",
        "url": "https://www.leboncoin.fr/ck/tablettes_liseuses/ipad-air-5",
        "observed": "iPad Air 5 fonctionnel souvent 320 à 400 EUR; exemplaires pour pièces observés autour de 125 à 170 EUR. Relevé du 12/09/2026.",
    },
    "lbc_ipad_pro11": {
        "title": "iPad Pro 11 pouces d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/tablettes_liseuses/ipad-pro-11-pouces",
        "observed": "Modèles 2018 à M2 affichés approximativement de 315 à 700 EUR selon génération, capacité et accessoires. Relevé du 12/09/2026.",
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
    "lbc_jbl_flip6": {
        "title": "JBL Flip 6 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/jbl-flip6",
        "observed": "184 annonces relevées; exemples récents principalement autour de 45 à 100 EUR selon l'état.",
    },
    "lbc_apple_watch_se2": {
        "title": "Apple Watch SE 2 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/telephones_objets_connectes/apple-watch-se-2",
        "observed": "981 annonces relevées; une SE 2 fonctionnelle et non bloquée est souvent affichée autour de 90 à 150 EUR.",
    },
    "lbc_apple_watch_parts": {
        "title": "Apple Watch pour pièces — leboncoin",
        "url": "https://www.leboncoin.fr/ck/telephones_objets_connectes/apple-watch-pour-piece",
        "observed": "251 annonces relevées; exemples pour pièces autour de 25 à 60 EUR, avec forte variation selon le modèle et les composants récupérables.",
    },
    "apple_watch_activation_lock": {
        "title": "Verrouillage d'activation de l'Apple Watch — Assistance Apple",
        "url": "https://support.apple.com/fr-fr/102542",
        "observed": "Apple confirme que l'ancien propriétaire doit retirer le verrouillage d'activation pour que la montre puisse être configurée et utilisée.",
    },
    "apple_mac_activation_lock": {
        "title": "Verrouillage d'activation du Mac — Assistance Apple",
        "url": "https://support.apple.com/fr-fr/102541",
        "observed": "Apple confirme qu'un Mac Apple Silicon ou T2 peut rester impossible à réactiver après effacement sans le compte Apple ou le code de l'ancien propriétaire.",
    },
    "lbc_recent_mac_parts": {
        "title": "MacBook récents pour pièces — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/macbook-pour-pieces/p-5",
        "observed": "MacBook Air M3 A3114 pour pièces observé à 300 EUR; MacBook Pro M4 A3401 pour pièces observé à 450 EUR. Relevé du 12/09/2026.",
    },
    "market_yoga_pro9": {
        "title": "Lenovo Yoga Pro 9 16IAH10 d'occasion",
        "url": "https://www.ebay.com/itm/366408149760",
        "observed": "Un exemplaire fonctionnel en excellent état vendu 1 192,84 GBP en mai 2026; le prix neuf français relevé dépasse 2 400 EUR. La cote du lot reste fortement décotée car non testé et sans chargeur.",
    },
    "lbc_samsung_s25": {
        "title": "Samsung Galaxy S25 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/telephones_objets_connectes/phone_brand%3Asamsung%2Bphone_model%3Asamsung_galaxys25",
        "observed": "Plus de 500 annonces; exemples 128/256 Go principalement autour de 420 à 500 EUR. Relevé du 12/09/2026.",
    },
    "lbc_samsung_midrange": {
        "title": "Samsung A54/A55 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/c/telephones_objets_connectes/phone_brand%3Asamsung%2Bphone_model%3Asamsung_galaxya5",
        "observed": "A54 128 Go observé à 150 EUR et A55 128 Go autour de 200 EUR. Relevé du 12/09/2026.",
    },
    "lbc_rtx2060": {
        "title": "PC et cartes RTX 2060 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/rtx-2060",
        "observed": "Carte RTX 2060 seule autour de 125 à 185 EUR; tours complètes principalement 350 à 600 EUR selon CPU/RAM. Relevé du 12/09/2026.",
    },
    "lbc_airpods": {
        "title": "AirPods d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/telephones_objets_connectes/airpods",
        "observed": "AirPods 3 autour de 85 EUR et AirPods Pro 2 autour de 70 à 120 EUR dans les exemples observés. Relevé du 12/09/2026.",
    },
    "lbc_xbox360": {
        "title": "Xbox 360 avec deux manettes — leboncoin",
        "url": "https://www.leboncoin.fr/ck/consoles/2-manettes-xbox-360",
        "observed": "Packs Xbox 360 avec deux manettes et accessoires principalement autour de 75 à 80 EUR. Relevé du 12/09/2026.",
    },
    "lbc_rollei35": {
        "title": "Rollei 35 argentiques d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/photo_audio_video/rollei-35",
        "observed": "Rollei 35 courants autour de 170 à 300 EUR testés; variantes LED/XF nettement moins chères et appareils pour pièces autour de 25 à 40 EUR. Relevé du 12/09/2026.",
    },
    "lbc_hp_probook_450_g9": {
        "title": "HP ProBook 450 G9 d'occasion — leboncoin",
        "url": "https://www.leboncoin.fr/ck/ordinateurs/hp-probook-450-g9",
        "observed": "Exemples particuliers autour de 240 à 400 EUR selon processeur, RAM et état; offres professionnelles plus élevées. Relevé du 12/09/2026.",
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


# Un appareil sans IMEI n'est ni déclaré ON ni OFF. Sa cote avant achat est
# construite à partir de la description, des photos et de la valeur des pièces.
def activation_unknown(device):
    return {
        "device": device,
        "imei_suffix": None,
        "imei_count": 0,
        "find_my_iphone": "INCONNU",
        "verification_basis": "description_only",
        "checked_on": None,
        "source": "Aucun IMEI publié — analyse de la description et des photos",
        "valuation_effect": "Cote prudente fondée sur l'état annoncé et les pièces récupérables ; l'absence de verrouillage n'est pas supposée.",
    }


def verified_imei(device, suffix, find_my, sim_lock, blacklist, description_state):
    return {
        "device": device,
        "imei_suffix": suffix,
        "find_my_iphone": find_my,
        "sim_lock": sim_lock,
        "blacklist": blacklist,
        "description_state": description_state,
    }


def verified_batch(device, items):
    on_count = sum(item["find_my_iphone"] == "ON" for item in items)
    off_count = sum(item["find_my_iphone"] == "OFF" for item in items)
    if on_count and off_count:
        status = f"{off_count} OFF · {on_count} ON"
        effect = f"{off_count} appareil(s) peuvent être cotés selon leur état ; {on_count} restent limités à la valeur des pièces."
    elif off_count:
        status = f"OFF ({off_count}/{len(items)})"
        effect = "Le verrouillage d'activation n'est pas détecté ; la décote restante vient de l'état décrit et du fonctionnement non testé."
    else:
        status = f"ON ({on_count}/{len(items)})"
        effect = "Valeur pièces uniquement tant que l'ancien propriétaire ne retire pas le verrouillage d'activation."
    return {
        "device": device,
        "imei_suffix": None,
        "imei_count": len(items),
        "find_my_iphone": status,
        "verification_basis": "verified",
        "checked_on": SNAPSHOT_DATE,
        "source": "IMEICheck.com — contrôles IMEI, liste noire et Find My effectués dans le navigateur",
        "valuation_effect": effect,
        "items": items,
    }


def mac_activation_risk(device):
    return {
        "device": device,
        "imei_suffix": None,
        "imei_count": 0,
        "find_my_iphone": "À vérifier",
        "verification_basis": "assumed",
        "checked_on": None,
        "source": "Assistance Apple — les Mac Apple Silicon et T2 peuvent rester verrouillés après effacement",
        "valuation_effect": "La valeur réutilisable n'est pas retenue sans démarrage et écran d'activation contrôlés.",
    }


DEVICE_CHECKS = {
    "302000": [activation_unknown("iPhone 16 128 Go")],
    "296119": [
        activation_unknown("iPhone X ou XS, écran HS"),
        activation_unknown("3 iPad mini, écrans HS"),
    ],
    "336701": [activation_unknown("10 iPhone du lot")],
    "340354": [activation_unknown("7 iPhone du lot")],
    "314274": [activation_unknown("iPhone 13 Pro Max, vitre arrière cassée")],
    "314267": [activation_unknown("iPhone 13 Pro Max annoncé en bon état")],
    "304783": [verified_batch("6 iPhone du lot", [
        verified_imei("iPhone 13 A2633", "9573", "OFF", "Unlocked", "Clean", "écran et coque à revoir · non testé"),
        verified_imei("iPhone SE 2 (2020) A2296", "1306", "ON", "Unlocked", "Clean", "non testé"),
        verified_imei("iPhone 13 Pro A2638", "7518", "ON", "Unlocked", "Clean", "écran à revoir · non testé"),
        verified_imei("iPhone XR A2105", "0211", "OFF", "Unlocked", "Clean", "non testé"),
        verified_imei("iPhone 12 A2403", "6972", "ON", "Unlocked", "Clean", "écran à revoir · non testé"),
        verified_imei("iPhone 11 A2221", "9620", "OFF", "Unlocked", "Clean", "écran à revoir · non testé"),
    ])],
    "306168": [
        verified_batch("3 iPhone avec IMEI sur les 5 du lot", [
            verified_imei("iPhone 16 Pro Max A3084", "2017", "ON", "Locked", "Clean", "écran à revoir · non testé"),
            verified_imei("iPhone XS Max A2101", "9523", "ON", "Unlocked", "Clean", "non testé"),
            verified_imei("iPhone 8 Plus A1897", "4614", "OFF", "Unlocked", "Clean", "non testé"),
        ]),
        activation_unknown("iPhone 14 écran à revoir et iPhone 16 sans IMEI"),
    ],
    "308035": [
        verified_batch("9 iPhone avec IMEI sur les 15 du lot", [
            verified_imei("iPhone SE 2 (2020) A2296", "6424", "ON", "Unlocked", "Clean", "non testé"),
            verified_imei("iPhone XR A2105", "1406", "OFF", "Unlocked", "Clean", "non testé"),
            verified_imei("iPhone 12 Pro A2407", "0492", "OFF", "Unlocked", "Clean", "non testé"),
            verified_imei("iPhone 12 Pro Max A2412", "2517", "ON", "Unlocked", "Clean", "non testé"),
            verified_imei("iPhone XR A2105", "7362", "OFF", "Unlocked", "Non retourné", "écran et coque à revoir · non testé"),
            verified_imei("iPhone 11 A2221", "4591", "ON", "Unlocked", "Clean", "écran à revoir · non testé"),
            verified_imei("iPhone 11 A2221", "4337", "ON", "Unlocked", "Clean", "écran à revoir · non testé"),
            verified_imei("iPhone 13 A2633", "9026", "OFF", "Unlocked", "Clean", "écran à revoir · non testé"),
            verified_imei("iPhone 17 Pro Max A3526", "6589", "OFF", "Unlocked", "Clean", "boîte ouverte · non testé"),
        ]),
        activation_unknown("6 iPhone sans IMEI : deux 17, 14 Pro Max, A3293, 12 probable et 14"),
    ],
    "309023": [verified_batch("iPhone 15 A3090", [
        verified_imei("iPhone 15 A3090", "5089", "OFF", "Non retourné", "Clean", "non testé · potentiellement bloqué selon l'annonce"),
    ])],
    "309881": [activation_unknown("2 Apple Watch du lot, dont une SE 2 40 mm A2722 identifiée sur les photos")],
    "288890": [activation_unknown("3 iPad du lot (2 iPad 10 et 1 iPad 9)")],
    "336669": [activation_unknown("7 iPad du lot, dont Air 5 et modèle A16")],
    "340268": [activation_unknown("7 iPad du lot, dont 2 iPad Pro")],
    "314403": [activation_unknown("iPad 7 Cellular 32 Go")],
    "314379": [activation_unknown("iPad Pro 12,9 pouces M2 Cellular")],
    "314372": [activation_unknown("iPad 7 Cellular 32 Go")],
    "314336": [activation_unknown("iPad 7 Cellular 32 Go")],
    "314296": [activation_unknown("iPad 7 Cellular 32 Go")],
    "314363": [activation_unknown("iPad 7 Cellular 32 Go")],
    "311309": [activation_unknown("iPad 10 A2696")],
    "318313": [activation_unknown("22 iPad du lot")],
    "336599": [activation_unknown("iPad 9 A2602")],
    "318430": [mac_activation_risk("MacBook Air M1 A2337 et MacBook Air Intel T2 A2179")],
    "318523": [mac_activation_risk("MacBook Air M1 A2337 et second MacBook Air non identifié")],
    "328386": [mac_activation_risk("MacBook Pro M4 A3401 et MacBook Air M3 A3114")],
    "338443": [verified_batch("Les 2 iPhone du lot", [
        verified_imei("iPhone 11 Pro A2160", "8592", "ON", "Unlocked", "Clean", "sans câble · fonctionnement non indiqué"),
        verified_imei("iPhone 12 A2403", "4229", "ON", "Unlocked", "Clean", "sans câble · fonctionnement non indiqué"),
    ])],
    "343959": [activation_unknown("iPhone 14 Pro")],
}


# id: (vente rapide du lot, recette normale après test/détail, confiance,
#      demande, délai min/max en jours, méthode, risques, sources)
VALUES: dict[str, tuple] = {}


def v(lot_id, quick, normal, confidence, demand, days, method, risks, sources):
    VALUES[str(lot_id)] = (
        quick, normal, confidence, demand, days[0], days[1], method, risks, sources
    )


for lot_id, qty in ((302468, 19), (302466, 30), (302464, 20)):
    v(lot_id, qty * 80, qty * 145, 72, "moyenne", (14, 75),
      "80 EUR/unité en sortie de lot sans chargeur; 145 EUR/unité testée et vendue séparément.",
      "Chargeurs absents; état fonctionnel non garanti; modèle peu présent sur leboncoin.",
      ["market_dynabook_c40"])

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
v(302442, 600, 960, 72, "moyenne", (14, 60),
  "100 EUR/unité en lot; 160 EUR/unité testée avec chargeur et sacoche.",
  "État batterie et génération exacte du Core i3 à confirmer.", ["market_dynabook_c40"])
for lot_id, qty in ((302440, 17), (302439, 20), (302436, 11), (302434, 19), (302433, 16), (302432, 10)):
    v(lot_id, qty * 100, qty * 160, 72, "moyenne", (14, 75),
      "100 EUR/unité en lot; 160 EUR/unité testée avec chargeur/sacoche.",
      "État batteries non documenté; forte quantité du même modèle sur le marché local.", ["market_dynabook_c40"])
v(302437, 1680, 2940, 75, "moyenne", (14, 75),
  "80 EUR/unité en lot; 140 EUR/unité testée pour le C40-H-115, sous le comparable reconditionné à 149 EUR.",
  "Génération plus ancienne et état batteries non documenté.", ["market_dynabook_c40"])
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
v(302000, 160, 300, 58, "moyenne", (21, 90),
  "La photo montre l'iPhone 16 allumé et la description confirme un 128 Go, mais le fonctionnement complet et l'activation restent inconnus; cote prudente d'état/pièces, plus la batterie externe.",
  "Aucun IMEI publié; un écran allumé ne prouve pas l'absence de verrouillage, ni l'état de la batterie, de Face ID ou des composants.", ["lbc_iphone16", "lbc_iphone_locked_parts"])
v(296119, 160, 300, 48, "moyenne", (30, 150),
  "Valeur des pièces récupérables du MacBook, des trois iPad mini et de l'iPhone X/XS dont l'écran est annoncé HS; aucun statut d'activation n'est inventé.",
  "Écrans HS, modèles/capacités incomplets, aucun IMEI ni chargeur et tout non testé.", ["lbc_macbook_m1"])
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
  "CPU, RAM, carte mère et alimentation inconnus; PC poussiéreux et non testé.", ["lbc_rtx2060"])
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
v(322440, 55, 100, 78, "faible", (21, 90),
  "Deux Xbox 360 S 4 Go, deux manettes et câblage.",
  "Faible stockage, consoles anciennes, état seulement décrit comme usage.", ["lbc_xbox360"])
v(322018, 250, 380, 74, "forte", (7, 30),
  "PS5 avec boîte, câbles et Modern Warfare III.",
  "État de fonctionnement inconnu; manette non explicitement listée.", ["lbc_ps5", "lbc_ps5_bundles"])
v(351136, 145, 205, 78, "forte", (7, 30),
  "AirPods 3 et AirPods Pro 2 en parfait état annoncé, avec boîtes.",
  "Authenticité et santé des batteries à vérifier; description des AirPods 3 contient des fonctions incohérentes.", ["lbc_airpods"])
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
v(348147, 160, 330, 64, "faible", (30, 150),
  "Rollei 35 domine la valeur, complété par Nikon F65, Yashica et flash.",
  "Tout non testé; version exacte du Rollei, cellule, obturateur et optiques à contrôler.", ["lbc_rollei35"])
v(336701, 850, 1500, 52, "moyenne", (45, 180),
  "Inventaire précis des dix iPhone (16 à SE), valorisé par état d'usage, risque de panne et valeur des pièces; aucun verrouillage ON/OFF n'est supposé sans IMEI.",
  "Aucun IMEI fourni; fonctionnement, activation, capacités, batteries et authenticité inconnus; mini-réplique sans valeur.", ["lbc_iphone16", "lbc_iphone_locked_parts", "ebay_iphone_locked_parts"])
v(336751, 380, 820, 55, "moyenne", (30, 150),
  "Dix Android de générations variées, A54/A55/Edge 30 étant les principaux contributeurs.",
  "Tout non testé, aucune capacité, aucun chargeur, risque de comptes/verrouillages.", ["lbc_samsung_midrange"])
v(288890, 350, 650, 58, "moyenne", (30, 120),
  "Les deux iPad 10 et l'iPad 9 sont cotés prudemment d'après leur état non testé et leurs pièces; valeur ajoutée pour Tab S4, Lenovo M10 et P11.",
  "Aucun IMEI iPad; activation et capacités inconnues, aucun chargeur, batteries et comptes Android non vérifiés.", ["lbc_ipad10", "lbc_ipad_parts"])
v(340354, 550, 950, 52, "moyenne", (45, 180),
  "Inventaire des sept iPhone 14 Pro à SE valorisé par état d'usage, risque de panne et pièces récupérables; aucun statut iCloud n'est supposé.",
  "Aucun IMEI fourni; fonctionnement, activation, capacités et batteries inconnus; aucun chargeur.", ["lbc_iphone13_current", "lbc_iphone_locked_parts", "ebay_iphone_locked_parts"])
v(340341, 450, 900, 49, "forte", (21, 120),
  "S25 et S22 portent l'essentiel de la valeur; six smartphones milieu/entrée de gamme.",
  "Tout non testé; authenticité du S25, capacités, comptes et IMEI à contrôler.", ["lbc_samsung_s25"])
v(336669, 600, 1000, 52, "moyenne", (30, 150),
  "Les sept iPad, dont Air 5 et modèle A16, sont cotés selon l'état non testé et la valeur des composants; valeur prudente ajoutée aux trois autres tablettes.",
  "Aucun IMEI iPad; activation/capacités inconnues, aucun chargeur, pannes possibles et modèle 'iPad A16' à confirmer.", ["lbc_ipad10", "lbc_ipad_parts"])
v(340268, 400, 800, 43, "moyenne", (45, 180),
  "Les sept iPad sont valorisés d'après leur état non testé et les pièces récupérables; les deux Pro non identifiés créent une large fourchette.",
  "Générations/capacités des Pro et Air inconnues; aucun IMEI ni statut d'activation, batteries et écrans non testés.", ["lbc_ipad_parts", "lbc_ipad_pro11"])
v(328386, 1250, 2500, 47, "moyenne", (30, 150),
  "Le Yoga Pro 9 16IAH10 domine la valeur; MacBook Pro M4 A3401 et Air M3 A3114 sont retenus à leur valeur pièces tant que l'écran d'activation n'est pas contrôlé.",
  "Cinq portables non testés, aucun chargeur, configurations exactes inconnues; Activation Lock possible sur les deux Mac récents.", ["market_yoga_pro9", "lbc_recent_mac_parts", "apple_mac_activation_lock"])
v(300877, 350, 800, 58, "faible", (45, 180),
  "M806 annoncé en marche; décote forte pour manutention, transport et clientèle professionnelle.",
  "Compteur pages, consommables et options non indiqués; machine très lourde.", [])
v(300859, 600, 1200, 56, "faible", (45, 180),
  "30 OfficeJet 8210/8100 annoncées en marche, 20-40 EUR/unité selon canal.",
  "Annonce les appelle LaserJet à tort; état des têtes/cartouches inconnu; trois palettes à transporter.", [])
v(314403, 35, 60, 72, "faible", (30, 120),
  "iPad 7 Cellular 32 Go coté d'après l'état non testé et les pièces récupérables; aucun bonus d'accessoire.",
  "Aucun IMEI; activation et fonctionnement inconnus, sans chargeur ni boîte.", ["lbc_ipad10", "lbc_ipad_parts"])
v(314391, 60, 100, 72, "faible", (21, 90),
  "Ancienne Intuos Pro Medium PTH-651.",
  "Stylet et câbles non explicitement listés; génération ancienne.", [])
v(314385, 90, 140, 80, "moyenne", (14, 60),
  "Magic Keyboard 12,9 pouces 2021 avec boîte.",
  "État cosmétique et disposition clavier à confirmer.", ["lbc_ipadpro12"])
v(314379, 250, 400, 61, "moyenne", (30, 120),
  "iPad Pro 12,9 M2 Cellular coté selon le bon état cosmétique annoncé, le risque non testé et les composants; boîte présente.",
  "Aucun IMEI; le bon état ne prouve ni fonctionnement ni dissociation du compte; capacité et batterie inconnues.", ["lbc_ipadpro12", "lbc_ipad_parts"])
for lot_id in (314372, 314336, 314296):
    v(lot_id, 55, 85, 73, "faible", (30, 120),
      "iPad 7 Cellular 32 Go coté d'après le bon état annoncé et les pièces; 20-30 EUR conservés pour boîte, clavier et chargeur.",
      "Aucun IMEI; le bon état cosmétique ne confirme ni fonctionnement ni dissociation du compte; clavier probablement tiers.", ["lbc_ipad10", "lbc_ipad_parts"])
v(314295, 30, 60, 82, "faible", (30, 120),
  "Time Capsule A1409 2 To fonctionnelle supposée, avec cordon.",
  "Produit réseau 2012 obsolète; disque dur ancien.", [])
v(314274, 55, 110, 62, "moyenne", (21, 90),
  "iPhone 13 Pro Max coté d'après le mauvais état annoncé, la vitre arrière à remplacer, l'écran rayé et les pièces récupérables.",
  "Aucun IMEI; activation, fonctionnement, capacité, batterie, Face ID et état interne inconnus.", ["lbc_iphone13pm", "lbc_iphone_locked_parts"])
v(314267, 100, 180, 57, "moyenne", (21, 90),
  "iPhone 13 Pro Max avec chargeur coté d'après le bon état annoncé et une forte réserve pour activation/fonctionnement non contrôlés.",
  "Aucun IMEI; capacité, activation, fonctionnement, santé batterie et authenticité des composants inconnus.", ["lbc_iphone13pm", "lbc_iphone_locked_parts"])
v(314363, 45, 70, 72, "faible", (30, 120),
  "iPad 7 Cellular 32 Go coté d'après l'état non testé et les pièces récupérables; petit bonus pour le clavier.",
  "Aucun IMEI; activation et fonctionnement inconnus, sans chargeur ni boîte.", ["lbc_ipad10", "lbc_ipad_parts"])
v(304783, 600, 1100, 64, "moyenne", (45, 180),
  "Six IMEI contrôlés: iPhone 13, XR et 11 sont Find My OFF et cotés selon leurs dommages/non-test; SE 2020, 13 Pro et 12 sont ON et restent en pièces. Les 18 autres téléphones sont inventoriés avec décote de gros.",
  "Trois iPhone restent verrouillés; plusieurs écrans/coques sont à revoir, aucun appareil n'est testé et le tri de 24 unités est important.", ["imeicheck_20260912", "lbc_iphone13_current", "lbc_iphone_locked_parts", "lbc_samsung_midrange"])
v(306168, 500, 850, 62, "moyenne", (45, 180),
  "Trois IMEI contrôlés: iPhone 8 Plus OFF, 16 Pro Max et XS Max ON. L'iPhone 14 écran à revoir et l'iPhone 16 sans IMEI restent cotés par état/pièces, avec le Galaxy A15.",
  "Deux iPhone sans IMEI; tout est non testé, le 16 Pro Max est aussi SimLock Locked et son écran est à revoir.", ["imeicheck_20260912", "lbc_iphone16", "lbc_iphone_locked_parts"])
v(308035, 1800, 3200, 61, "moyenne", (45, 240),
  "Neuf IMEI contrôlés: cinq OFF dont le 17 Pro Max propre/désimlocké en boîte, le 12 Pro, deux XR et le 13; quatre ON restent en pièces. Les six iPhone sans IMEI sont cotés par description et risque.",
  "Tous les appareils restent non testés; six iPhone sans IMEI, plusieurs écrans/coques endommagés, modèles 17/A3293 à authentifier et ventes nombreuses.", ["imeicheck_20260912", "lbc_iphone17pm_current", "lbc_iphone12pro_current", "lbc_iphone13_current", "lbc_iphone_locked_parts"])
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
v(309881, 80, 130, 58, "moyenne", (21, 120),
  "Photos contrôlées : une Apple Watch SE 2 40 mm A2722 et une seconde Watch non identifiée, cotées par état et pièces sans inventer leur activation; valeur ajoutée pour la JBL Flip 6 et la mini-imprimante LG PD233.",
  "Aucun identifiant de montre ni preuve de dissociation, aucun chargeur visible, seconde Watch non identifiée et fonctionnement de tous les appareils inconnu.", ["lbc_apple_watch_se2", "lbc_apple_watch_parts", "lbc_jbl_flip6", "apple_watch_activation_lock"])
v(304101, 300, 420, 79, "forte", (7, 30),
  "PS5 Slim CFI-2016 et deux manettes, non testées.",
  "Fonctionnement et dérive des sticks non vérifiés.", ["lbc_ps5", "lbc_ps5_bundles"])
v(310961, 220, 420, 62, "moyenne", (21, 90),
  "Écrans BenQ XL2540K/AOC 24G1, portable Asus ancien et disque 1 To.",
  "Tout non testé; configuration du portable inconnue.", [])
v(311309, 130, 250, 60, "moyenne", (30, 120),
  "Galaxy Tab A9+ non testée, iPad 10 coté par état/pièces faute d'IMEI et faible valeur pour les deux caméras génériques.",
  "Capacités, activation et fonctionnement non testés; caméras mal identifiées.", ["lbc_ipad10", "lbc_ipad_parts"])
v(309023, 280, 400, 74, "forte", (7, 45),
  "IMEI contrôlé: iPhone 15 A3090 Find My OFF et liste noire Clean. Cote placée sous les annonces 128 Go fonctionnelles car l'appareil reste non testé.",
  "SimLock non retourné faute de numéro de série; capacité, batterie, authenticité, caméras et état interne inconnus.", ["imeicheck_20260912", "lbc_iphone15_current"])
v(317922, 700, 1800, 46, "moyenne", (60, 240),
  "58 casques dont plusieurs Bose/Sony haut de gamme, deux écouteurs, baladeurs et 30 vinyles.",
  "Tout non testé; batteries/coussinets; inventaire textuel possiblement imprécis; très nombreuses ventes.", ["lbc_sony_xm4"])
v(318200, 350, 750, 52, "moyenne", (45, 180),
  "Neuf JBL dont Charge 4/5, treize enceintes entrée de gamme et trois baladeurs.",
  "Modèles JBL incomplets, batteries et fonctionnement non testés.", ["lbc_jbl"])
v(318313, 1300, 2800, 57, "moyenne", (90, 300),
  "Les 22 iPad sont identifiés par référence et cotés selon l'état non testé et les pièces; A2377, A2230, A2588/A2589 et A2602 portent la valeur. Android et liseuses sont décotés.",
  "Aucun IMEI iPad; activation, écrans et batteries inconnus. Le titre annonce 23 liseuses mais le détail n'en énumère que 22, soit 54 appareils détaillés contre 55 annoncés; ventes séparées très longues.", ["lbc_ipad_parts", "lbc_ipad_pro11", "lbc_ipadpro12"])
v(318327, 300, 600, 61, "forte", (21, 90),
  "PS5, Switch, 3DS XL, 3DS, Wii et deux jeux.",
  "Tout non testé; accessoires et chargeurs non détaillés.", ["lbc_ps5", "lbc_switch_oled"])
v(318370, 250, 550, 49, "moyenne", (45, 180),
  "Projecteur Epson, micro AT2035, cinq appareils photo, caméscope et divers.",
  "Tout non testé; objets hétérogènes; nombreuses ventes de faible montant.", ["lbc_sony_a6000"])
v(318430, 550, 1050, 45, "moyenne", (45, 180),
  "Six portables et accessoires; les MacBook Air M1/T2 sont retenus à valeur pièces sans contrôle de l'écran d'activation, le Pro A1502 restant reformattable.",
  "Tout non testé; spécifications inconnues; Activation Lock possible sur A2337/A2179 et seule une partie a des chargeurs.", ["lbc_macbook_m1", "apple_mac_activation_lock"])
v(318523, 450, 900, 43, "moyenne", (45, 180),
  "Cinq portables et divers; le MacBook Air M1 est retenu à valeur pièces, tandis que l'Asus X1404Z et les PC Windows portent la revente testée.",
  "Tout non testé; second MacBook Air non identifié, Activation Lock possible et configurations inconnues.", ["lbc_macbook_m1", "apple_mac_activation_lock"])
v(318544, 850, 1900, 44, "forte", (60, 240),
  "Treize portables hétérogènes, dont T14, T480s, HP 855 G7, Surface 1960 et MacBook.",
  "Tout non testé; configurations/activation inconnues; travail de tri important.", ["lbc_dell_7490", "lbc_macbook_m1"])
v(336599, 100, 200, 52, "moyenne", (30, 120),
  "iPad 9 A2602 coté par état/pièces faute d'IMEI, plus Olympus E-P2 et petits appareils non testés.",
  "Activation et fonctionnement inconnus; référence Samsung probablement mal saisie et batterie de l'appareil photo ancienne.", ["lbc_ipad10", "lbc_ipad_parts"])
v(282679, 320, 420, 87, "forte", (7, 30),
  "Switch OLED Splatoon complète, sept jeux et deux sacoches.",
  "Fonctionnement non explicitement garanti; titres des jeux à pondérer selon demande.", ["lbc_switch_oled"])
v(309638, 300, 380, 84, "forte", (7, 30),
  "PS5 complète en boîte avec manette et câbles.",
  "Modèle disque/digital et fonctionnement à vérifier.", ["lbc_ps5"])
v(84173, 240, 350, 84, "forte", (7, 30),
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
v(347842, 300, 450, 86, "forte", (7, 30),
  "Sony A6000 et objectif kit 16-50 OSS.",
  "Déclenchements, capteur, autofocus et batterie à vérifier.", ["lbc_sony_a6000"])
v(303291, 250, 350, 72, "forte", (14, 45),
  "ProBook 450 G9 avec chargeur, calé sous les annonces comparables faute de configuration précise.",
  "CPU, RAM et SSD non indiqués; compte BIOS/entreprise et batterie à vérifier.", ["lbc_hp_probook_450_g9"])
v(41076, 150, 220, 78, "moyenne", (14, 45),
  "IdeaPad Slim 3 Chromebook 14IAN8, 8/128 Go avec chargeur.",
  "État batterie et éventuelle gestion scolaire/entreprise à vérifier.", [])
v(126221, 140, 220, 65, "moyenne", (14, 60),
  "Asus M509D 8/512 Go avec chargeur, estimation médiane faute de CPU.",
  "Processeur exact, batterie et état écran non indiqués.", [])
v(338443, 35, 70, 68, "moyenne", (21, 90),
  "Les deux IMEI sont contrôlés: iPhone 11 Pro et iPhone 12 sont tous deux Find My ON, liste noire Clean et désimlockés; valeur des pièces uniquement.",
  "Aucune valeur d'usage ou de déblocage; capacité, batterie, écrans, cartes mères et autres composants récupérables restent inconnus.", ["imeicheck_20260912", "lbc_iphone_locked_parts", "ebay_iphone_locked_parts"])
v(343959, 110, 190, 50, "moyenne", (30, 120),
  "iPhone 14 Pro sans IMEI coté par état et pièces, sans inventer son activation; faible valeur ajoutée pour le second téléphone non identifié.",
  "Modèle 'SAMSUNG ONE' incohérent; activation, capacités, batteries et fonctionnement inconnus.", ["lbc_iphone14pro", "lbc_iphone_locked_parts"])
v(321714, 80, 170, 68, "faible", (30, 120),
  "Wii, PS3 Slim, DS Lite et casque filaire.",
  "Tout non testé; câbles PS3 absents; faible valeur unitaire.", [])
v(329193, 350, 750, 62, "moyenne", (21, 90),
  "Xiaomi Mi 4K Laser Projector 150, décoté comme non testé sans cordon.",
  "Panne laser/DMD coûteuse possible; télécommande et cordon absents/non listés.", ["lbc_xiaomi_4k"])
v(304620, 200, 500, 43, "faible", (60, 240),
  "Douze anciennes tours Acer, vingt alimentations et sept cartes graphiques anciennes.",
  "Configurations et fonctionnement inconnus; GPU 512 Mo obsolètes; logistique lourde.", [])
v(294796, 10000, 18000, 76, "moyenne", (45, 240),
  "100 E595 complets: 100 EUR/unité en sortie professionnelle, 180 EUR/unité testée/vendue.",
  "Très gros volume, pas d'OS, batteries à contrôler; recette normale exige 100 ventes et une garantie vendeur.", ["lbc_e595", "bm_e595"])
v(294805, 1200, 2000, 77, "moyenne", (30, 150),
  "11 L580 i5-8250U et un L570: environ 100 EUR/unité en lot et 160-180 EUR au détail, sous les prix particuliers observés.",
  "Pas d'OS; état des batteries/écrans à vérifier; volume de 12 unités.", ["lbc_l580"])


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
        vat_status, vat_rate = vat_from_description(lot.get("desc"))
        auction_fees, vat_amount, purchase_total = acquisition_at_bid(
            current, AUCTION_FEE_RATE, vat_status, vat_rate
        )
        max_bid = recommended_max_bid(
            quick, confidence, AUCTION_FEE_RATE, vat_status, vat_rate
        )
        max_bid_fees, max_bid_vat, max_purchase_total = acquisition_at_bid(
            max_bid, AUCTION_FEE_RATE, vat_status, vat_rate
        )
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
            "photos_reviewed": True,
            "photos_reviewed_on": SNAPSHOT_DATE,
            "market_checked_on": SNAPSHOT_DATE,
            "quick_sale_lot_eur": quick,
            "normal_resale_gross_eur": normal,
            "recommended_max_bid_eur": max_bid,
            "recommended_max_bid_fees_eur": max_bid_fees,
            "recommended_max_bid_vat_eur": max_bid_vat,
            "recommended_max_purchase_total_eur": max_purchase_total,
            "quick_margin_at_recommended_max_bid_eur": money(quick - max_purchase_total),
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
            "recommended_max_bid_eur": "Montant marteau maximal conseillé, affiché hors 11 % de frais. Il limite le coût d'acquisition complet à 50–75 % de la cote de vente rapide selon la confiance, conserve donc 25–50 % de réserve, puis retire les frais d'enchère et l'éventuelle TVA explicitement indiquée. Arrondi par prudence aux 5 EUR inférieurs.",
            "recommended_max_purchase_total_eur": "Coût total au plafond conseillé : enchère maximale + 11 % de frais + TVA uniquement lorsqu'elle est explicitement indiquée.",
            "quick_margin_at_recommended_max_bid_eur": "Cote de vente rapide moins le coût total au plafond conseillé, avec les 11 % de frais et l'éventuelle TVA inclus dans le calcul.",
            "quick_margin_before_other_costs_eur": "Cote de vente rapide moins le coût d'achat incluant les 11 % de frais d'enchère et l'éventuelle TVA explicitement indiquée.",
            "normal_margin_before_other_costs_eur": "Cote de revente normale moins le coût d'achat incluant les 11 % de frais d'enchère et l'éventuelle TVA explicitement indiquée.",
            "confidence_percent": "Confiance dans l'ordre de grandeur, pas probabilité de vente.",
            "apple_phone_policy": "Quand un IMEI iPhone est publié, le statut Find My est contrôlé et daté: ON limite la cote aux pièces, OFF permet une cote d'après l'état tout en conservant la décote non testé. Sans IMEI, le statut reste INCONNU et la cote prudente s'appuie sur la description, les photos et les pièces récupérables.",
            "apple_tablet_policy": "Sans IMEI ou contrôle d'activation, un iPad est marqué INCONNU et non ON. Sa cote avant achat est prudente et fondée sur la référence, l'état décrit, les photos et les pièces.",
            "apple_watch_policy": "Sans identifiant ou preuve de dissociation, une Apple Watch est marquée INCONNU. Sa cote reste fondée sur l'état et les composants, sans supposer un déblocage.",
            "apple_mac_policy": "Un Mac Apple Silicon ou T2 peut rester sous verrouillage d'activation après effacement. Sans contrôle de l'écran d'activation, sa valeur réutilisable n'est pas retenue comme certaine.",
            "photos_reviewed": "Les photos publiées pour le lot ont été relues lors de cette passe afin de relever les références visibles, les accessoires, les écrans allumés et les dommages apparents.",
        },
        "limitations": [
            "Les frais d'enchère sont calculés au taux demandé de 11 % sur le prix courant. Aucune TVA n'est ajoutée sans mention explicite dans la description du lot.",
            "Les 21 IMEI iPhone publiés ont été contrôlés le 12/09/2026: 10 Find My OFF et 11 ON. Un appareil sans IMEI reste INCONNU; aucun statut ON ou OFF n'est inventé.",
            "IMEICheck est une source tierce: un statut peut évoluer et la confirmation la plus forte reste le démarrage physique après effacement jusqu'à l'écran Bonjour, sans demande du compte de l'ancien propriétaire.",
            "Les prix leboncoin relevés sont surtout des prix demandés, pas des prix de transaction certifiés.",
            "La date de mise en ligne et le délai réel de vente ne sont pas exposés de façon fiable pour chaque comparable; aucun délai n'est présenté comme une mesure leboncoin exacte.",
            "Un écran allumé sur une photo ne prouve ni le fonctionnement complet, ni l'absence de compte, de MDM ou de verrouillage d'activation.",
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
