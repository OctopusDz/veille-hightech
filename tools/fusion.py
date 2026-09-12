#!/usr/bin/env python3
"""Fusionne une collecte fraîche dans les données du site, et archive les lots terminés.

Règles :

* un lot **nouveau** est ajouté ;
* un lot **déjà connu** est mis à jour (enchère, statut, dates…) sans perdre ce
  qu'on avait déjà (notamment les photos si la collecte n'en rapporte pas) ;
* un lot connu qui **n'est plus actif** part dans l'archive avec son prix de
  départ, sa dernière enchère et, si on la connaît, la somme adjugée.

L'archive n'est jamais réécrite : chaque lot n'y entre qu'une fois. C'est elle
qui donne la traçabilité — versionnée dans Git, elle garde la trace de chaque
clôture, collecte après collecte.

Usage :
    python3 tools/fusion.py collecte.json [--termines finis.json]

`collecte.json` suit la forme produite par tools/collecte.js : {"lots": [...]}.
`--termines` (facultatif) apporte l'état final des lots clos (prix adjugé).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOTS = ROOT / "site" / "data" / "lots.json"
ARCHIVE = ROOT / "site" / "data" / "archive.json"

STATUTS_ACTIFS = {13, 14}          # 13 = vente à venir, 14 = vente en cours

# Champs qu'une collecte peut rafraîchir sur un lot déjà connu.
CHAMPS_MAJ = (
    "name", "status", "statusLabel", "start", "end", "price", "bid", "reserve",
    "pro", "org", "url", "desc", "city", "cp", "depot", "street",
    "contact", "phone", "email", "hours", "access",
    "bidVerified", "bidCheckedAt",
)


def charger(chemin: Path, defaut):
    if not chemin.exists():
        return defaut
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{chemin} illisible : {exc}")


def ecrire(chemin: Path, donnees) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def entree_archive(lot: dict, final: dict | None, quand: str) -> dict:
    """Fige un lot terminé : ce qu'il valait au départ, et où il a fini."""
    f = final or {}
    adjuge = f.get("bid_winner_amount")
    dernier = f.get("last_bid", lot.get("bid"))
    depart = lot.get("price")
    # Le prix retenu : l'adjudication si on l'a, sinon la dernière enchère vue.
    retenu = adjuge if adjuge not in (None, 0) else dernier
    statut = f.get("lot_status_label") or lot.get("statusLabel") or ""
    # Vendu ou non : le statut final fait foi ; à défaut, l'existence d'un prix.
    if "invendu" in statut.lower():
        vendu = False
    elif adjuge not in (None, 0):
        vendu = True
    else:
        vendu = retenu is not None and retenu != depart
    return {
        "id": lot.get("id"),
        "lot": lot.get("lot"),
        "name": lot.get("name"),
        "desc": lot.get("desc"),
        "pro": bool(lot.get("pro")),
        "img": lot.get("img"),
        "photos": lot.get("photos") or [],
        "city": lot.get("city"),
        "cp": lot.get("cp"),
        "depot": lot.get("depot"),
        "org": lot.get("org"),
        "start": lot.get("start"),
        "end": lot.get("end"),
        "prixDepart": depart,
        "dernierBid": dernier,
        "prixAdjuge": adjuge,
        "prixRetenu": retenu,
        # Marge brute du vendeur : combien la vente a rapporté au-dessus de la mise.
        "ecart": (retenu - depart) if (retenu is not None and depart is not None) else None,
        "vendu": vendu,
        "statutFinal": statut or None,
        "url": lot.get("url"),
        "archiveLe": quand,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("collecte", type=Path, help="JSON de la collecte fraîche")
    ap.add_argument("--termines", type=Path, help="JSON des lots clos (prix adjugé)")
    ap.add_argument("--sec", action="store_true", help="n'écrit rien, montre le bilan")
    args = ap.parse_args()

    fraiche = charger(args.collecte, None)
    if fraiche is None:
        raise SystemExit(f"collecte introuvable : {args.collecte}")
    nouveaux = {int(l["id"]): l for l in fraiche.get("lots", []) if l.get("id") is not None}
    if not nouveaux:
        raise SystemExit("la collecte ne contient aucun lot — on n'écrase rien")

    finis = {}
    if args.termines and args.termines.exists():
        brut = charger(args.termines, {})
        for l in (brut.get("lots") if isinstance(brut, dict) else brut) or []:
            if l.get("id") is not None:
                finis[int(l["id"])] = l

    courant = charger(LOTS, {"lots": []})
    anciens = {int(l["id"]): l for l in courant.get("lots", []) if l.get("id") is not None}

    arch = charger(ARCHIVE, {"lots": []})
    deja = {int(l["id"]) for l in arch.get("lots", []) if l.get("id") is not None}

    quand = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ajoutes, majs, inchanges, archives = [], [], 0, []

    fusionnes: dict[int, dict] = {}
    for lid, neuf in nouveaux.items():
        vieux = anciens.get(lid)
        if vieux is None:
            fusionnes[lid] = neuf
            ajoutes.append(neuf)
            continue
        fusionne = dict(vieux)
        change = {}
        for champ in CHAMPS_MAJ:
            if champ in neuf and neuf[champ] != vieux.get(champ):
                change[champ] = (vieux.get(champ), neuf[champ])
                fusionne[champ] = neuf[champ]
        # Les photos locales ne sont remplacées que si la collecte en apporte.
        if neuf.get("photos"):
            fusionne["photos"] = neuf["photos"]
            fusionne["img"] = neuf.get("img") or neuf["photos"][0]
        fusionnes[lid] = fusionne
        if change:
            majs.append((fusionne, change))
        else:
            inchanges += 1

    # Un lot connu absent de la collecte (ou passé hors 13/14) est terminé.
    for lid, vieux in anciens.items():
        if lid in nouveaux and nouveaux[lid].get("status") in STATUTS_ACTIFS:
            continue
        if lid in nouveaux:
            continue
        if lid in deja:
            continue
        archives.append(entree_archive(vieux, finis.get(lid), quand))

    lots_final = sorted(fusionnes.values(), key=lambda l: (str(l.get("city") or ""), l.get("lot") or 0))

    print(f"collecte : {len(nouveaux)} lots actifs")
    print(f"  nouveaux    : {len(ajoutes)}")
    print(f"  mis à jour  : {len(majs)}")
    print(f"  inchangés   : {inchanges}")
    print(f"  archivés    : {len(archives)}")
    for lot, ch in majs[:15]:
        detail = ", ".join(f"{c} {a}→{b}" for c, (a, b) in ch.items() if c in ("bid", "status", "statusLabel"))
        if detail:
            print(f"    lot {lot.get('lot')} {str(lot.get('name'))[:34]:<34} {detail}")
    for a in archives[:15]:
        print(f"    archivé lot {a['lot']} {str(a['name'])[:30]:<30} "
              f"départ {a['prixDepart']} → retenu {a['prixRetenu']} ({a['statutFinal']})")

    if args.sec:
        print("\n(mode --sec : rien n'a été écrit)")
        return 0

    courant["lots"] = lots_final
    courant["updated"] = fraiche.get("updated") or quand
    courant["count"] = len(lots_final)
    ecrire(LOTS, courant)

    if archives:
        arch.setdefault("lots", []).extend(archives)
        arch["updated"] = quand
        arch["count"] = len(arch["lots"])
        ecrire(ARCHIVE, arch)

    print(f"\nécrit : {LOTS}" + (f"\nécrit : {ARCHIVE}" if archives else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
