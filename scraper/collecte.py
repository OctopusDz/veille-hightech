"""Collecteur des lots high-tech — version HTTP, sans navigateur.

Rejoue les appels GraphQL que la page fait elle-même, via le transport qui
franchit le contrôle anti-robot (redirection à jeton, cf. transport.py).
Tourne aussi bien sur un runner GitHub Actions qu'en local.

Produit, dans data/ :

* ``collecte.json``  — les lots actifs (à venir + en cours), même forme que
  tools/collecte.js : id, lot, name, status, start, end, price, bid, dépôt…
* ``termines.json``  — l'état final des lots qu'on suivait et qui ont disparu
  (prix adjugé, dernière enchère, statut) — pour l'archive.

Usage :
    python3 -m scraper.collecte            # données seulement
    python3 -m scraper.collecte --photos   # + télécharge les photos manquantes

Étapes suivantes : tools/fusion.py data/collecte.json --termines data/termines.json
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import re
import sys
import time
import urllib.parse
from pathlib import Path

from . import config, transport

log = logging.getLogger("collecte")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_LOTS = ROOT / "site" / "data" / "lots.json"
IMG_DIR = ROOT / "site" / "img"
MEDIA = config.BASE_URL + "/admin/media/catalog/product"

CAT_HIGH_TECH = "46"
STATUTS_ACTIFS = ["13", "14"]          # 13 = vente à venir, 14 = vente en cours
DELAI = 0.6                            # entre deux appels (s) — on reste poli
MAX_PX, QUALITE = 1100, 82             # redimensionnement des photos

# Le serveur exige la signature complète (currentPage + sort), sinon 500.
Q_LISTE = (
    "query getCategoryLots($currentPage:Int$filter:ProductAttributeFilterInput!"
    "$pageSize:Int$sort:ProductAttributeSortInput){products(currentPage:$currentPage "
    "filter:$filter pageSize:$pageSize sort:$sort){items{id sku lot_number name url_key "
    "lot_status lot_status_label start_auction_lot_at end_auction_lot_at start_date "
    "end_date price_auction last_bid reserve_price bid_winner_amount professional_only "
    "auction description{html}short_description{html}small_image{url}"
    "sales_inspector_data{cav_name}}page_info{total_pages}total_count}}"
)
# dropoff_location est NULL dans la liste : il n'est rempli que sur le détail.
Q_DETAIL = (
    "query getProductPageMain($urlKey:String!){products(filter:{url_key:{eq:$urlKey}})"
    "{items{id lot_status lot_status_label last_bid bid_winner_amount price_auction "
    "reserve_price dropoff_location_id dropoff_location{city postcode}"
    "dropoff_location_fo{name address city postcode}"
    "contact_dropoff_location{name email telephone physical_schedule tel_schedule}"
    "media_gallery_entries{file position disabled}}}}"
)
# État final d'un lot (prix adjugé, dernière enchère, statut) — pour l'archive.
Q_FINAL = (
    "query getProductPageSide($urlKey:String!){products(filter:{url_key:{eq:$urlKey}})"
    "{items{id lot_status lot_status_label last_bid bid_winner_amount price_auction "
    "end_auction_lot_at}}}"
)

STRIP = re.compile(r"<[^>]*>")


def _texte(html: str | None) -> str:
    s = STRIP.sub(" ", html or "")
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#039;", "'")
          .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    return " ".join(s.split())


class Collecteur:
    def __init__(self, t: transport.Transport):
        self.t = t
        self.appels = 0

    def gql(self, query: str, op: str, variables: dict) -> dict:
        url = (config.GRAPHQL_URL + "?query=" + urllib.parse.quote(query)
               + "&operationName=" + op
               + "&variables=" + urllib.parse.quote(json.dumps(variables)))
        derniere: Exception | None = None
        for essai in range(config.MAX_RETRIES):
            try:
                brut = transport.resoudre_challenge(self.t, url)
                self.appels += 1
                d = json.loads(brut)
                if d.get("errors") and not (d.get("data") or {}).get("products"):
                    raise RuntimeError(d["errors"][0].get("message", "erreur GraphQL"))
                time.sleep(DELAI)
                return d
            except Exception as exc:            # réseau, JSON, challenge non résolu
                derniere = exc
                attente = 2 ** (essai + 1)
                log.warning("%s : %s — nouvel essai dans %ss", op, exc, attente)
                time.sleep(attente)
        raise RuntimeError(f"{op} : échec après {config.MAX_RETRIES} essais ({derniere})")

    # ---- 1. liste des lots actifs -------------------------------------
    def lots_actifs(self) -> list[dict]:
        cat = base64.b64encode(CAT_HIGH_TECH.encode()).decode()
        lots, page = [], 1
        while True:
            d = self.gql(Q_LISTE, "getCategoryLots", {
                "currentPage": page, "pageSize": config.PAGE_SIZE,
                "sort": {"start_auction_lot_at": "ASC"},
                "filter": {"category_uid": {"eq": cat}, "lot_status": {"in": STATUTS_ACTIFS}},
            })
            p = d["data"]["products"]
            lots.extend(p["items"])
            log.info("page %d/%d — %d lots", page, p["page_info"]["total_pages"], len(lots))
            if page >= p["page_info"]["total_pages"]:
                break
            page += 1
        return lots

    # ---- 2. détail : dépôt, contact, photos ---------------------------
    def detail(self, url_key: str) -> dict:
        d = self.gql(Q_DETAIL, "getProductPageMain", {"urlKey": url_key})
        items = d["data"]["products"]["items"]
        if not items:
            return {}
        it = items[0]
        fo = it.get("dropoff_location_fo") or {}
        dl = it.get("dropoff_location") or {}
        c = it.get("contact_dropoff_location") or {}
        nettoie = lambda v: (v or "").strip() or None
        photos = sorted((m for m in (it.get("media_gallery_entries") or []) if not m.get("disabled")),
                        key=lambda m: m.get("position") or 0)
        return {
            # Ces champs de prix proviennent de la fiche individuelle. Elle est
            # la source fiable en direct ; la liste de catégorie reste un repli.
            "status": it.get("lot_status"),
            "statusLabel": it.get("lot_status_label"),
            "price": it.get("price_auction"),
            "bid": it.get("last_bid"),
            "reserve": it.get("reserve_price"),
            "bidVerified": True,
            "depotId": it.get("dropoff_location_id"),
            "depot": nettoie(fo.get("name")),
            "street": nettoie(fo.get("address")),
            "city": nettoie(dl.get("city") or fo.get("city")),
            "cp": nettoie(dl.get("postcode") or fo.get("postcode")),
            "contact": nettoie(c.get("name")),
            "phone": nettoie(c.get("telephone")),
            "email": nettoie(c.get("email")),
            "hours": nettoie(c.get("tel_schedule")),
            "access": nettoie(c.get("physical_schedule")),
            "photosDistantes": [MEDIA + m["file"] for m in photos if m.get("file")],
        }

    # ---- 3. état final d'un lot disparu --------------------------------
    def final(self, url_key: str) -> dict | None:
        d = self.gql(Q_FINAL, "getProductPageSide", {"urlKey": url_key})
        items = d["data"]["products"]["items"]
        return items[0] if items else None


def normaliser(b: dict, d: dict) -> dict:
    return {
        "id": b["id"], "sku": b.get("sku"), "lot": b.get("lot_number"),
        "name": (b.get("name") or "").strip(),
        "status": b.get("lot_status"), "statusLabel": b.get("lot_status_label"),
        "start": b.get("start_auction_lot_at") or b.get("start_date"),
        "end": b.get("end_auction_lot_at") or b.get("end_date"),
        "price": b.get("price_auction"), "bid": b.get("last_bid"),
        "reserve": b.get("reserve_price"), "pro": bool(b.get("professional_only")),
        "auction": b.get("auction"),
        "org": (b.get("sales_inspector_data") or {}).get("cav_name"),
        "url": f"{config.BASE_URL}/lot/{b['url_key']}.html",
        "urlKey": b["url_key"],
        "desc": _texte((b.get("description") or {}).get("html"))
                or _texte((b.get("short_description") or {}).get("html")),
        **{k: v for k, v in d.items() if k != "photosDistantes"},
        "photosDistantes": d.get("photosDistantes", []),
    }


def telecharger_photos(t: transport.Transport, lots: list[dict], connus: dict[int, dict]) -> int:
    """Rapatrie les photos des lots qui n'en ont pas encore en local."""
    try:
        from PIL import Image
    except ImportError:
        Image = None
        log.warning("Pillow absent : photos enregistrées sans redimensionnement")
    n = 0
    for lot in lots:
        dossier = IMG_DIR / str(lot["id"])
        deja = connus.get(lot["id"], {}).get("photos") or []
        if deja and dossier.exists() and all((ROOT / "site" / p).exists() for p in deja):
            lot["photos"], lot["img"] = deja, deja[0]
            continue
        locales = []
        for i, url in enumerate(lot.get("photosDistantes") or []):
            try:
                brut = transport.resoudre_challenge(t, url)
                if len(brut) < 500 or brut[:1] == b"<":
                    raise ValueError("pas une image")
                dossier.mkdir(parents=True, exist_ok=True)
                cible = dossier / f"{i}.jpg"
                if Image:
                    im = Image.open(io.BytesIO(brut)).convert("RGB")
                    im.thumbnail((MAX_PX, MAX_PX))
                    im.save(cible, "JPEG", quality=QUALITE, optimize=True)
                else:
                    cible.write_bytes(brut)
                locales.append(f"img/{lot['id']}/{i}.jpg")
                n += 1
                time.sleep(0.15)
            except Exception as exc:
                log.warning("photo %s : %s", url[-40:], exc)
        lot["photos"] = locales
        lot["img"] = locales[0] if locales else None
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--photos", action="store_true", help="télécharge les photos manquantes")
    ap.add_argument("--max", type=int, default=0, help="limite de lots (tests)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    connus: dict[int, dict] = {}
    if SITE_LOTS.exists():
        for l in json.loads(SITE_LOTS.read_text(encoding="utf-8")).get("lots", []):
            if l.get("id") is not None:
                connus[int(l["id"])] = l

    t = transport.creer()
    if not transport.amorcer_session(t):
        log.warning("amorçage de session incertain — on continue")
    col = Collecteur(t)

    bruts = col.lots_actifs()
    if args.max:
        bruts = bruts[: args.max]
    log.info("%d lots actifs — détail de chacun…", len(bruts))

    lots, echecs, prix_non_verifies = [], 0, []
    for i, b in enumerate(bruts, 1):
        try:
            d = col.detail(b["url_key"])
        except Exception as exc:
            echecs += 1
            log.warning("détail lot %s : %s", b.get("lot_number"), exc)
            d = {}
        precedent = connus.get(int(b["id"]), {})
        ancien_effectif = precedent.get("bid") if precedent.get("bid") is not None else precedent.get("price")
        nouveau_effectif = d.get("bid") if d.get("bid") is not None else d.get("price")
        if (str(b.get("lot_status")) == "14" and d.get("bidVerified")
                and ancien_effectif is not None and nouveau_effectif is not None
                and float(nouveau_effectif) < float(ancien_effectif)):
            log.error("lot %s : le prix vérifié recule de %s à %s", b.get("lot_number"),
                      ancien_effectif, nouveau_effectif)
            d["bidVerified"] = False
        if str(b.get("lot_status")) == "14" and not d.get("bidVerified"):
            prix_non_verifies.append(b.get("lot_number"))
        lots.append(normaliser(b, d))
        if i % 20 == 0:
            log.info("  %d/%d", i, len(bruts))

    # Lots suivis qui ne sont plus actifs : on va chercher leur état final.
    actifs = {l["id"] for l in lots}
    disparus = [l for lid, l in connus.items() if lid not in actifs]
    termines = []
    for l in disparus:
        key = l.get("urlKey") or l["url"].rsplit("/lot/", 1)[-1].replace(".html", "")
        try:
            f = col.final(key)
            if f:
                termines.append(f)
        except Exception as exc:
            log.warning("état final lot %s : %s", l.get("lot"), exc)
    log.info("%d lots disparus, %d états finaux récupérés", len(disparus), len(termines))

    nb_photos = 0
    if args.photos:
        nb_photos = telecharger_photos(t, lots, connus)
        log.info("%d photos téléchargées", nb_photos)
    else:
        # Sans téléchargement, on conserve les photos locales déjà connues.
        for l in lots:
            deja = connus.get(l["id"], {})
            l["photos"] = deja.get("photos") or []
            l["img"] = deja.get("img")

    t.fermer()
    DATA.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    quand = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for lot in lots:
        if lot.get("bidVerified"):
            lot["bidCheckedAt"] = quand
    (DATA / "collecte.json").write_text(json.dumps(
        {"updated": quand, "source": "encheres-domaine.gouv.fr — High tech (46)",
         "count": len(lots), "lots": lots}, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "termines.json").write_text(json.dumps(
        {"updated": quand, "lots": termines}, ensure_ascii=False, indent=1), encoding="utf-8")

    en_cours = sum(1 for l in lots if l["status"] == 14)
    print(f"\n{len(lots)} lots actifs ({en_cours} en cours, {len(lots) - en_cours} à venir) "
          f"· {echecs} détail(s) en échec · {len(prix_non_verifies)} prix en cours non vérifié(s) "
          f"· {len(termines)} terminé(s) · {col.appels} appels"
          + (f" · {nb_photos} photos" if args.photos else ""))
    if prix_non_verifies:
        log.error("prix non vérifiés pour les lots en cours : %s", prix_non_verifies)
    return 1 if prix_non_verifies or (echecs and echecs > len(lots) // 4) else 0


if __name__ == "__main__":
    raise SystemExit(main())
