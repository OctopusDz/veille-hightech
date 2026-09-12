"""Rafraîchit uniquement les enchères des lots en cours depuis leur fiche.

La liste de catégorie Magento peut conserver un ancien ``last_bid`` en cache.
Ce passage léger interroge donc chaque fiche individuelle. Une baisse confirmée
est acceptée car une offre peut être annulée. Après échec des nouvelles
tentatives sur session propre, le dernier prix connu reste affiché et signalé.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import transport
from .collecte import Collecteur

ROOT = Path(__file__).resolve().parent.parent
LOTS_PATH = ROOT / "site" / "data" / "lots.json"


def prix_effectif(lot: dict) -> float | None:
    valeur = lot.get("bid") if lot.get("bid") is not None else lot.get("price")
    return float(valeur) if valeur is not None else None


def afficher_prix(valeur: float | None) -> str:
    return "—" if valeur is None else f"{valeur:g}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sec", action="store_true", help="contrôle sans écrire le fichier")
    args = parser.parse_args()

    brut = json.loads(LOTS_PATH.read_text(encoding="utf-8"))
    actifs = [lot for lot in brut.get("lots", []) if str(lot.get("status")) == "14"]
    t = transport.creer()
    if not transport.amorcer_session(t):
        print("amorçage de session incertain — poursuite des contrôles")
    collecteur = Collecteur(t)
    controles, changements, erreurs = [], [], []

    for lot in actifs:
        key = lot.get("urlKey") or lot["url"].rsplit("/lot/", 1)[-1].removesuffix(".html")
        try:
            direct = collecteur.final(key)
            if not direct or direct.get("price_auction") is None:
                raise ValueError("fiche sans prix")
            nouveau = dict(lot)
            nouveau.update({
                "status": direct.get("lot_status"),
                "statusLabel": direct.get("lot_status_label"),
                "price": direct.get("price_auction"),
                "bid": direct.get("last_bid"),
                "bidVerified": True,
            })
            avant, apres = prix_effectif(lot), prix_effectif(nouveau)
            controles.append((lot, nouveau))
            if avant != apres:
                changements.append((lot.get("lot"), lot.get("name"), avant, apres))
        except Exception as exc:
            erreurs.append((lot.get("lot"), str(exc)))
            nouveau = dict(lot)
            nouveau["bidVerified"] = False
            nouveau["bidCheckError"] = "fiche officielle momentanément inaccessible"
            controles.append((lot, nouveau))

    collecteur.t.fermer()
    if erreurs:
        for numero, erreur in erreurs:
            print(f"lot {numero} : {erreur}")
        print(f"{len(erreurs)} dernier(s) prix connu(s) conservé(s) et marqué(s) à recontrôler")

    quand = datetime.now(timezone.utc).isoformat(timespec="seconds")
    remplacements = {int(nouveau["id"]): nouveau for _, nouveau in controles}
    for index, lot in enumerate(brut.get("lots", [])):
        neuf = remplacements.get(int(lot["id"]))
        if neuf:
            neuf["bidCheckAttemptedAt"] = quand
            if neuf.get("bidVerified"):
                neuf["bidCheckedAt"] = quand
                neuf.pop("bidCheckError", None)
            brut["lots"][index] = neuf
    brut["updated"] = quand
    brut["count"] = len(brut.get("lots", []))

    print(f"{len(controles) - len(erreurs)}/{len(actifs)} prix en cours vérifiés "
          f"· {len(erreurs)} à recontrôler · {len(changements)} changement(s)")
    for numero, nom, avant, apres in changements:
        print(f"  lot {numero} {str(nom)[:42]} : {afficher_prix(avant)} → {afficher_prix(apres)} EUR")
    if not args.sec:
        temporaire = LOTS_PATH.with_suffix(".json.tmp")
        temporaire.write_text(json.dumps(brut, ensure_ascii=False, indent=1), encoding="utf-8")
        temporaire.replace(LOTS_PATH)
        print(f"écrit : {LOTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
