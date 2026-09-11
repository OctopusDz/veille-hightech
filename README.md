# Veille High-Tech — enchères du Domaine

Interface locale pour suivre les lots high-tech de
[encheres-domaine.gouv.fr](https://encheres-domaine.gouv.fr), regroupés **par ville de
dépôt** et classés **du plus proche au plus loin** de chez moi.

## Lancer le site

```bash
python3 tools/serve.py
```

→ <http://localhost:8800>

Ce serveur envoie `Cache-Control: no-store` : un simple `Cmd+R` suffit toujours à voir
les changements (contrairement à `python3 -m http.server`, qui laisse le navigateur
garder l'ancien JS en cache).

## Ce que fait l'interface

- **Deux onglets** : « En cours » et « À venir ».
- **Regroupement par ville de dépôt** — pas par organisateur : Rennes éclate ses lots
  sur Saint-Grégoire, Plérin, Vannes, Le Mans et Guilers.
- **Distance depuis chez moi** sur chaque dépôt, tri du plus proche au plus loin.
- **Filtre par date de clôture** (aujourd'hui, sous 3 j, sous 7 j, ou date exacte).
- **Poubelle** : écarter un lot le masque sans le supprimer ; réversible, mémorisé
  dans le navigateur, et conservé d'une collecte à l'autre (on garde l'identifiant).
- **Détail d'un dépôt** : adresse, itinéraire, horaires, conditions de retrait,
  contact — puis les lots avec photos, prix, description et lien vers l'annonce.

## Collecte des données

> **Pourquoi pas GitHub Actions ?** Le site est protégé par un anti-bot qui renvoie un
> CAPTCHA (403) aux navigateurs automatisés sans interface. La collecte doit donc
> tourner dans un **vrai navigateur, sur cette machine**. Aucun contournement n'est
> tenté : on rejoue simplement les appels que la page fait déjà elle-même.

| Fichier | Rôle |
| --- | --- |
| `tools/collecte.js` | Le collecteur, exécuté **dans la page** du site |
| `tools/collecteur.mjs` | Pilote un vrai Chrome et déclenche la collecte |
| `tools/importer.py` | Range les lots et les photos téléchargés |
| `tools/fusion.py` | Fusionne avec l'existant et **archive les lots terminés** |
| `tools/distances.py` | Calcule la distance de chaque dépôt (API Adresse, BAN) |
| `tools/serve.py` | Sert le site + expose la collecte manuelle |

## Données

| Fichier | Contenu |
| --- | --- |
| `site/data/lots.json` | Les lots actifs (en cours + à venir) |
| `site/data/archive.json` | Les lots terminés : prix de départ, dernière enchère, prix adjugé |
| `site/img/` | Photos (hors dépôt Git — régénérées par la collecte) |

L'archive est versionnée dans Git : chaque collecte qui clôture des lots laisse une
trace dans l'historique.
