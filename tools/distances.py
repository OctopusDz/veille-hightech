#!/usr/bin/env python3
"""Calcule la distance de chaque dépôt depuis chez toi et l'écrit dans lots.json.

Géocodage : API Adresse (BAN) de data.gouv.fr — ouverte, sans anti-bot.
La distance routière est estimée par la distance à vol d'oiseau × 1,30
(sinuosité moyenne du réseau français). Suffisant pour classer les dépôts.

Le point de départ vient de la variable d'environnement CHEZ_MOI (secret GitHub
Actions en production) : il n'apparaît ni dans le code, ni dans les données —
seuls les kilomètres par dépôt sont écrits.

Usage : CHEZ_MOI="Ville 12345" python3 tools/distances.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOTS = ROOT / "site" / "data" / "lots.json"
CACHE = ROOT / "tools" / ".geocache.json"

CHEZ_MOI = os.environ.get("CHEZ_MOI", "").strip() or (sys.argv[1] if len(sys.argv) > 1 else "")
SINUOSITE = 1.30          # trajet réel / vol d'oiseau
VITESSE_KMH = 95.0        # moyenne porte-à-porte (mix nationale / autoroute)


def geocode(query: str, cache: dict) -> tuple[float, float] | None:
    q = " ".join(query.split())
    if q in cache:
        v = cache[q]
        return (v[0], v[1]) if v else None
    url = "https://api-adresse.data.gouv.fr/search/?limit=1&q=" + urllib.parse.quote(q)
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.load(r)
        feats = data.get("features") or []
        if not feats:
            cache[q] = None
            return None
        lon, lat = feats[0]["geometry"]["coordinates"]
        cache[q] = [lat, lon, feats[0]["properties"]["label"]]
        return lat, lon
    except Exception as exc:  # réseau indisponible : on n'invente rien
        print(f"  échec géocodage {q!r} : {exc}")
        return None
    finally:
        time.sleep(0.15)


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def main() -> int:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    if not CHEZ_MOI:
        print("CHEZ_MOI non défini (variable d'environnement ou argument)")
        return 1
    home = geocode(CHEZ_MOI, cache)
    if not home:
        print("point de départ introuvable")
        return 1
    print("départ : configuré (non affiché)")

    data = json.loads(LOTS.read_text(encoding="utf-8"))
    lots = data["lots"]

    # Un dépôt = une adresse. On géocode l'adresse la plus précise disponible.
    depots: dict[tuple, str] = {}
    for lot in lots:
        key = (lot.get("city"), lot.get("cp"))
        if key not in depots:
            depots[key] = " ".join(x for x in (lot.get("street"), lot.get("cp"), lot.get("city")) if x)

    coords: dict[tuple, tuple[float, float] | None] = {}
    for key, addr in depots.items():
        c = geocode(addr, cache)
        if not c:  # repli : commune seule
            c = geocode(f"{key[1]} {key[0]}", cache)
        coords[key] = c

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    lignes = []
    for key, c in coords.items():
        if c is None:
            for lot in lots:
                if (lot.get("city"), lot.get("cp")) == key:
                    lot["km"] = lot["heures"] = None
            lignes.append((10**9, f"  {key[0]} ({key[1]}) : distance inconnue"))
            continue
        km = round(haversine(home, c) * SINUOSITE)
        heures = round(km / VITESSE_KMH, 2)
        for lot in lots:
            if (lot.get("city"), lot.get("cp")) == key:
                lot["km"] = km
                lot["heures"] = heures
                lot["lat"], lot["lon"] = c[0], c[1]
        h = int(heures)
        lignes.append((km, f"  {key[0]} ({key[1]}) : {km} km · {h}h{round((heures - h) * 60):02d}"))

    data.pop("home", None)          # jamais d'adresse personnelle dans les données
    LOTS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    for _, ligne in sorted(lignes):
        print(ligne)
    print(f"\nécrit : {LOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
