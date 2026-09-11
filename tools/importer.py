#!/usr/bin/env python3
"""Importe les deux fichiers produits par tools/collecte.js dans le site.

Lit ~/Downloads/lots-hightech.json et ~/Downloads/photos-hightech.bin,
écrit site/data/lots.json et site/img/<id>/<n>.jpg, puis réécrit les chemins
photo des lots vers le local (le site fonctionne alors sans réseau).

Usage : python3 tools/importer.py [dossier_des_telechargements]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads"


def main() -> int:
    src_json, src_bin = DL / "lots-hightech.json", DL / "photos-hightech.bin"
    for p in (src_json, src_bin):
        if not p.exists():
            print(f"introuvable : {p}")
            return 1

    data = json.loads(src_json.read_text(encoding="utf-8"))
    lots = data["lots"]

    raw = src_bin.read_bytes()
    mlen = int(raw[:10].decode())
    manifest = json.loads(raw[10 : 10 + mlen])

    img_dir = SITE / "img"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True)

    pos = 10 + mlen
    by_lot: dict[int, list[str]] = {}
    for e in manifest:
        blob = raw[pos : pos + e["len"]]
        pos += e["len"]
        d = img_dir / str(e["id"])
        d.mkdir(exist_ok=True)
        (d / f"{e['n']}.jpg").write_bytes(blob)
        by_lot.setdefault(e["id"], []).append(f"img/{e['id']}/{e['n']}.jpg")

    if pos != len(raw):
        print(f"attention : {len(raw) - pos} octets non consommés")

    sans = 0
    for lot in lots:
        photos = by_lot.get(lot["id"], [])
        lot["photos"] = photos
        lot["img"] = photos[0] if photos else None
        if not photos:
            sans += 1

    out = SITE / "data" / "lots.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    en_cours = sum(1 for l in lots if l["status"] == 14)
    print(f"{len(lots)} lots ({en_cours} en cours, {len(lots) - en_cours} à venir)")
    print(f"{len(manifest)} photos -> {img_dir}")
    if sans:
        print(f"{sans} lot(s) sans photo")
    print(f"écrit : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
