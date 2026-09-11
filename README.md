# Veille High-Tech — enchères du Domaine

Suivi des lots high-tech de [encheres-domaine.gouv.fr](https://encheres-domaine.gouv.fr),
regroupés **par ville de dépôt** et classés **du plus proche au plus loin** de chez moi.

**Site : <https://octopusdz.github.io/veille-hightech/>**

Tout tourne sur GitHub — rien à lancer en local.

## Fonctionnement

```
GitHub Actions — 5 passages par jour (06h, 09h30, 13h, 17h, 21h Paris) + bouton « Collecter »
  scraper/collecte.py   récupère les lots actifs + le détail de chaque lot (dépôt, contact, photos)
                        et l'état final des lots disparus (prix adjugé)
  tools/fusion.py       fusionne avec l'existant, met à jour les enchères,
                        archive les lots terminés (prix de départ → prix adjugé)
  tools/distances.py    distance de chaque dépôt (API Adresse, adresse en secret)
  → commit lots.json + archive.json, puis déploiement du site sur GitHub Pages
```

Le collecteur rejoue les appels GraphQL que la page fait elle-même, en franchissant
la redirection à jeton du contrôle anti-robot (`scraper/transport.py`, méthode
reprise du projet véhicules). Aucun CAPTCHA n'est résolu : le site n'en présente pas
à une session HTTP normale.

## Interface

- **Deux onglets** : « En cours » et « À venir ».
- **Regroupement par ville de dépôt** — pas par organisateur : Rennes éclate ses lots
  sur Saint-Grégoire, Plérin, Vannes, Le Mans et Guilers.
- **Distance depuis chez moi** sur chaque dépôt, tri du plus proche au plus loin.
- **Filtre par date de clôture** (aujourd'hui, sous 3 j, sous 7 j, ou date exacte).
- **Poubelle** : écarter un lot le masque sans le supprimer ; réversible, mémorisé
  dans le navigateur, conservé d'une collecte à l'autre (on garde l'identifiant).
- **Détail d'un dépôt** : adresse, itinéraire, horaires, retrait, contact — puis les
  lots avec photos, prix, description et lien vers l'annonce officielle.
- **🔄 Collecter** : lance un passage immédiat (onglet Actions → *Run workflow*).

## Données

| Fichier | Contenu |
| --- | --- |
| `site/data/lots.json` | Les lots actifs (en cours + à venir) |
| `site/data/archive.json` | Les lots terminés : prix de départ, dernière enchère, prix adjugé, vendu ou non |
| `site/img/` | Photos — hors Git, conservées dans le cache Actions, publiées avec le site |

L'archive est versionnée : chaque clôture laisse une trace dans l'historique Git.

## Vie privée

L'adresse de départ est un **secret GitHub** (`CHEZ_MOI`). Elle n'apparaît ni dans le
code, ni dans les données, ni dans les journaux — seuls les kilomètres par dépôt sont
publiés. La poubelle et les réglages restent dans le navigateur.

## En local (facultatif, pour développer)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
CHEZ_MOI="Ville 12345" .venv/bin/python -m scraper.collecte --photos
.venv/bin/python tools/fusion.py data/collecte.json --termines data/termines.json
python3 tools/serve.py        # http://localhost:8800, sans cache
```
