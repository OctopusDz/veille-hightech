# PROMPT DE REPRISE — Historique des enchères sur encheres-domaine.gouv.fr

> À coller dans une nouvelle session. Objectif : **retrouver l'historique des enchères** (et si possible
> le nombre d'enchérisseurs) d'un lot. Ce document résume tout ce qui a déjà été établi pour ne PAS
> le refaire, puis liste les pistes restantes. Cas d'usage : lot 408 « 100 PC portables Lenovo E595 »,
> `auctionId 472`, `lotId 294796`, url : /lot/ordinateursportableslenovo-1.html

## MISSION
Déterminer s'il existe un moyen d'obtenir (a) l'historique chronologique des enchères d'un lot,
(b) le nombre d'enchérisseurs. Rester dans le cadre légitime : **inspecter ce que le site fait déjà**
dans MA session connectée ; **ne pas** forger de payloads pour extraire des données masquées sur
d'autres utilisateurs ; **ne pas** contourner l'anti-bot/CAPTCHA.

---

## ARCHITECTURE (établie)
- Front **React (SPA)** ; client GraphQL **Apollo**. Backend **Magento GraphQL**, endpoint unique :
  `https://encheres-domaine.gouv.fr/gateway/magento/graphql/` (requêtes en **GET**, `operationName` obligatoire).
- **Auth = Keycloak / OpenID Connect**, realm `vega-front` → jeton `Authorization: Bearer` (durée ~5 min).
- **Anti-bot** : 1er appel hors navigateur → page `window.location.href='/redirect_<jeton>/…'` ;
  cookie `bot_mitigation_cookie` ; **escalade en CAPTCHA ALTCHA** (`403 "Check that you are not a robot"`)
  contre les navigateurs automatisés (headless ET piloté). → collecte auto = bloquée par design.
- **Open data officiel** (DNID / data.gouv.fr, licence Etalab 2.0, **annuel**) = uniquement les
  **prix d'adjudication finaux** des ventes passées. Pas d'historique d'enchères.

## API GraphQL — opérations connues
`ProductSearch`, `getAutocompleteResults`, `getCategories`, `getProductPageMain`, `getProductPageSide`,
`getAuctions`(`auctionsList`), `getAuctionHeaderInfos`, `getAuctionLots`, `getCavList`, `storeConfig`,
`getLocale`, `customerDetails`(auth).
- Champs « enchère » sur le lot (type **`VirtualProduct`**) : `last_bid` (=3100), `bid_winner_amount`,
  `reserve_price`, `price_auction` (=500), `auction_steps`, `professional_only`, `lot_status_label`.
- `auction_steps` = barème du **pas** : 200–1000 €→+10 ; 1000–5000 €→+50 ; 5000 €+→+100.

## WebSocket temps réel (session CONNECTÉE)
- URL : `wss://encheres-domaine.gouv.fr/gateway/ws/api-ws/private?access_token=<JWT>`
- Format : **JSON encapsulé en binaire**, `{"type":"…","data":{…}}`.
- Vocabulaire **complet observé** :
  - ⬆ `JOIN_ROOM` {auctionId, lotId}
  - ⬇ `JOINED_ROOM` {auctionId, lotId}
  - ⬆ `GET_LATEST_BID_ON_LOT` {auctionId, lotId}
  - ⬇ `LATEST_BID` {auctionId, lotId, **bidValue**, **highestBidderId** (UUID), **hasBid** (bool = si MOI j'ai misé)}

## CE QUI EST DÉJÀ PROUVÉ (ne pas re-tester)
1. Schéma GraphQL : **aucun** champ historique/compteur. Sondés et INEXISTANTS sur `ProductInterface`
   ET `VirtualProduct` : `bid_count, bids_count, number_of_bids, total_bids, nb_bids, bids, bid_history,
   bidders_count, participants_count, auction_bids, offers_count, bids_number, bid_step, current_bid_count`.
2. Aucune opération `getBidHistory` / `getBids` / `getAuctionState` observée, **même connecté**.
3. WebSocket : ne diffuse que la **dernière** enchère (bidValue + UUID du meneur), **jamais** une liste.
   L'archi « poll GET_LATEST_BID » prouve qu'il n'y a pas d'endpoint historique (sinon le client l'appellerait).
4. Partenaires `auction_urls` (Drouot Digital, Moniteur des ventes) = `url_path: **null**` pour ce lot
   (`auction_type_label = "Vente en ligne"` → la vente est sur encheres-domaine, pas chez un partenaire).
5. Public (déconnecté) : **zéro** WebSocket / SSE ; countdown = JS client.

→ **Conclusion actuelle : l'historique PASSÉ et le nombre d'enchérisseurs ne sont exposés nulle part,
par design.** Le seul « historique » possible = celui qu'on **enregistre en direct**.

## PISTES RESTANTES (légitimes) à vérifier
1. **Lister TOUS les `operationName`** réellement émis en session connectée sur : la page lot,
   la page vente `/vente/472?page=1`, et l'écran d'enchère. (Network → filtre `graphql`.)
   → confirmer qu'aucune opération non encore vue n'existe.
2. **Espace « Mes enchères » du compte** : chercher dans /mon-compte un historique de MES propres
   enchères (c'est MA donnée, donc légitime). Repérer l'opération GraphQL correspondante.
3. **Écouter le WS pendant une enchère réelle** (quand un tiers surenchérit) : vérifier s'il existe
   un push d'un autre `type` que `LATEST_BID` (ex. `NEW_BID`, `BID_PLACED`) apportant plus d'infos.
4. **Construire l'historique en live** : garder l'onglet WS Messages ouvert et logger chaque `LATEST_BID`
   (bidValue + highestBidderId + heure). Compter les **UUID distincts** qui prennent la tête = plancher
   du nombre de concurrents actifs (≠ nombre total d'enchérisseurs).

## ESTIMATION (à titre indicatif, non fiable)
Nombre de surenchères MAX si chaque enchère = pas mini : 500→1000 (+10 → 50) + 1000→3100 (+50 → 42)
= **≈ 90 max**. Réel probablement bien moindre (enchères au-dessus du pas / plafond auto).
**Nombre d'enchères ≠ nombre d'enchérisseurs.**

## LIMITES À RESPECTER
- Ne PAS forger/deviner des payloads WS/GraphQL pour extraire les enchères/identités **d'autres acheteurs**
  (données masquées volontairement — vie privée).
- Ne PAS contourner l'anti-bot / résoudre le CAPTCHA.
- Ne PAS coller de jeton `Authorization`/cookie de session en clair.
- Objectif réaliste : historique de MES enchères = peut-être accessible ; historique/participants
  des autres = non exposé, seulement reconstructible en direct.
