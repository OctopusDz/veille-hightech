# Cotes des lots actifs

## Synthèse

L’inventaire analysé comprend **112 lots et 588 photos**. La valeur brute estimée est de **76 065 € en sortie rapide** et de **130 410 € en revente normale**, à condition de contrôler le matériel et de vendre séparément les articles lorsque cela est pertinent.

Au prix courant cumulé de **29 720 €**, les **11 % de frais d’enchère représentent 3 269,20 €**, soit un coût d’achat total observé de **32 989,20 €**. Aucune TVA n’est ajoutée : aucune des 112 descriptions actuelles ne la mentionne explicitement. L’écart brut cumulé est donc de **43 075,80 €** face aux cotes rapides et de **97 420,80 €** face aux cotes normales, avant transport, pièces, retours, commissions de plateforme et temps de travail.

Ces chiffres ne sont pas des bénéfices. Les enchères peuvent encore monter et réduire fortement les écarts affichés.

Les fichiers détaillés sont :

- `cotes_lots_actifs_2026-09-11.csv` pour le contrôle, le tri et Excel ;
- `cotes_lots_actifs_2026-09-11.json` pour l’export structuré ;
- `site/data/cotes.json` pour l’affichage des cotes directement dans le SaaS.

## Lecture des deux cotes

La **vente rapide du lot** est le prix brut plausible pour céder le lot dans l’état annoncé, sans garantie et avec peu de préparation. La **revente normale brute** est la recette plausible après contrôle, nettoyage et ventes séparées. Pour les lots professionnels volumineux, la différence entre les deux représente surtout du temps, du risque et de la logistique, pas une marge nette.

La confiance médiane est de **67 %**. Elle mesure la solidité de l’ordre de grandeur, pas la probabilité qu’une vente se réalise. Vingt-six lots sont sous 50 % de confiance, principalement parce que les modèles, capacités, blocages ou états de fonctionnement ne sont pas connus.

## Lots à fort potentiel apparent

| ID | Lot | Prix observé* | Achat avec 11 % | Vente rapide | Revente normale | Confiance |
|---:|---|---:|---:|---:|---:|---:|
| 294796 | 100 Lenovo E595 | 3 100 € | 3 441 € | 10 000 € | 18 000 € | 72 % |
| 302420 | 59 PC fixes | 300 € | 333 € | 3 500 € | 6 000 € | 58 % |
| 299305 | 24 E595 + divers | 50 € | 55,50 € | 3 200 € | 6 200 € | 58 % |
| 302437 | 21 Dynabook C40-H-115 | 600 € | 666 € | 2 300 € | 3 150 € | 68 % |
| 302462 | 11 Dell Latitude + docks | 300 € | 333 € | 1 600 € | 2 350 € | 74 % |
| 303750 | Pioneer DDJ-REV7 + flight-case | 500 € | 555 € | 1 200 € | 1 650 € | 83 % |

\* Prix courant quand une enchère existe, sinon mise à prix, relevé dans le fichier du SaaS le 11 septembre 2026. Le SaaS recalcule le coût d’achat avec 11 % à partir du prix courant à chaque actualisation. La TVA reste à 0 € sauf mention explicite dans la description.

## Contrôles prioritaires avant achat

Les lots de téléphones 304783, 306168, 308035, 336701, 340354 et 340341 doivent être considérés comme des lots de pièces tant que l’IMEI, le verrouillage d’activation, l’authenticité, l’écran, la batterie, Face ID et les caméras ne sont pas vérifiés.

Pour le lot **338443**, le contrôle communiqué pour l’iPhone 12 A2403 indique **Find My iPhone ON**. Cet appareil est donc valorisé uniquement pour pièces tant que le propriétaire d’origine ne retire pas le verrouillage d’activation. Par sécurité, l’iPhone 11 Pro non testé est lui aussi valorisé uniquement pour pièces : la cote actuelle du lot est de **60 € en vente rapide** et **100 € en vente séparée des pièces**. Une éventuelle valeur d’usage ne sera ajoutée qu’après un test concluant et un statut FMI OFF.

Les lots Apple 328386, 318430, 318523, 318544 et 318313 peuvent perdre une grande partie de leur valeur en cas de verrouillage iCloud ou MDM. Les références seules ne prouvent ni le stockage ni le fonctionnement.

Le DJI Matrice 210 est en excellent état annoncé, mais son marché est étroit et les batteries TB55 vieillissantes. Le Xiaomi Mi 4K vaut nettement plus lorsqu’il fonctionne, mais une panne du bloc laser ou du DMD peut ramener sa valeur près de celle des pièces.

## Méthode et limites

Chaque cote combine la description du lot, les photos disponibles, une somme des valeurs unitaires lorsque l’inventaire est détaillé, une décote de quantité et une décote de risque pour les mentions « non testé », « potentiellement bloqué », les accessoires absents et les défauts visibles.

Les pages leboncoin donnent un bon signal de concurrence et de prix demandé : par exemple 5 132 annonces pour la recherche Switch OLED, 3 798 pour la Xbox Series S, 1 476 pour l’iPhone 16 128 Go et 45 pour le Logitech G435. Elles ne donnent toutefois pas un historique complet et fiable du temps de mise en vente ni le prix final négocié. Une disparition d’annonce ne prouve pas une vente.

Le marché donne notamment les repères suivants :

- iPhone 16 128 Go : la majorité des exemples pertinents relevés se situe entre 460 et 600 € ([leboncoin](https://www.leboncoin.fr/c/telephones_objets_connectes/phone_brand%3Aapple%2Bphone_memory%3A128go%2Bphone_model%3Aiphone16)) ;
- PS5 seule : exemples courants autour de 330 à 400 € ([leboncoin](https://www.leboncoin.fr/c/consoles/console_brand%3Asony%2Bconsole_model%3Aps5)) ;
- Switch OLED : nombreux exemples autour de 150 à 210 € ([leboncoin](https://www.leboncoin.fr/ck/consoles/nintendo-switch-oled)) ;
- Xbox Series X avec deux manettes : environ 400 à 540 € parmi les exemples simples ([leboncoin](https://www.leboncoin.fr/ck/consoles/xbox-serie-x-avec-2-manette)) ;
- GoPro Hero 10 Black : fréquemment 180 à 250 € ([leboncoin](https://www.leboncoin.fr/ck/photo_audio_video/gopro-10-black)) ;
- Fujifilm X-T20 : marché dispersé, avec des kits 18-55 pertinents autour de 450 à 800 € ([leboncoin](https://www.leboncoin.fr/ck/photo_audio_video/fujifilm-x-t20)) ;
- Sony A6000 avec 16-50 : généralement autour de 390 à 450 € ([leboncoin](https://www.leboncoin.fr/ck/photo_audio_video/sony-alpha-6000)) ;
- Pioneer DDJ-REV7 : contrôleur autour de 1 300 à 1 750 €, flight-case seul autour de 220 à 250 € ([leboncoin](https://www.leboncoin.fr/ck/photo_audio_video/ddj-rev7)) ;
- Xiaomi Mi 4K Laser Projector 150 : environ 700 à 1 200 € fonctionnel, avec un exemplaire pour pièces affiché à 180 € ([leboncoin](https://www.leboncoin.fr/ck/photo_audio_video/xiaomi-mi-laser)) ;
- Logitech G435 : le plus souvent 20 à 35 €, avec une annonce marquée vendue à 25 € ([leboncoin](https://www.leboncoin.fr/ck/photo_audio_video/casque-g435)) ;
- MacBook Air M1 A2337 : fonctionnel souvent 350 à 560 €, mais seulement 70 à 270 € pour pièces selon la panne ([leboncoin](https://www.leboncoin.fr/ck/ordinateurs/macbook-air-a2337)) ;
- Lenovo E595 Ryzen 5 16/256 : 407 € reconditionné avec garantie, valeur nécessairement inférieure en gros et sans garantie ([Back Market](https://www.backmarket.fr/fr-fr/p/lenovo-e595-15-ryzen-5-3500u-ghz-ssd-256-go-16-go/7c3dcefc-9ebf-48df-8d27-50ff8082cddb)).

Le détail par lot contient la méthode, les risques, la demande estimée, le délai et les références de marché utilisées. Les cotes sont un instantané de marché et non une garantie ou une expertise officielle.
