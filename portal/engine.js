'use strict';
/* engine.js — le "cerveau" de l'app, 100% côté navigateur (aucun serveur).
 *
 * Ce module ne scrape RIEN. Il prend les lots (data/lots.json), les regroupe par
 * dépôt exact, calcule le trajet depuis chez toi, estime la revente et rend un
 * verdict GO / NO-GO par dépôt.
 *
 * Géocodage : BAN (api-adresse.data.gouv.fr) — API publique ouverte, CORS activé,
 * sans anti-bot. leboncoin : on ne fait QUE construire une URL de recherche que
 * l'utilisateur ouvre lui-même (deep-link) ; aucune requête auto vers leboncoin.
 */

const Engine = (() => {

  // ---- Réglages par défaut (surchargés par les Réglages de l'app) ----------
  const DEFAULTS = {
    home: 'Yvelines',      // ton point de départ (commune/CP), géocodé via la BAN
    marginPct: 40,         // marge de revente visée (sur la cote)
    minNetPerTrip: 150,    // marge nette minimale pour qu'un déplacement vaille le coup (€)
    maxDriveH: 3.5,        // au-delà : train plutôt que voiture
    avgKmh: 95,            // vitesse moyenne porte-à-porte (mix nationale/autoroute)
    fuelPerKm: 0.12,       // carburant (€/km)
    tollPerKm: 0.07,       // péage moyen (€/km) — 0 si tu évites l'autoroute
    roundTrip: true,       // aller-retour
    hourValue: 15,         // valeur de ton temps (€/h) — passé dans le verdict
    trainBase: 25,         // forfait train de base (€)
    trainPerKm: 0.11,      // train (€/km, aller simple estimé)
    loadHours: 0.75,       // temps sur place (vérif + chargement)
    vanPerDay: 80,         // location utilitaire pour un lot volumineux (€/jour)
  };

  const num = (v) => (v == null || v === '' || isNaN(+v)) ? null : +v;
  const clampPct = (p) => Math.max(0, Math.min(95, +p || 0));

  // ---- Géocodage BAN, avec cache localStorage ------------------------------
  async function geocode(query) {
    const q = (query || '').trim();
    if (!q) return null;
    const key = 'geo:' + q.toLowerCase();
    try { const c = localStorage.getItem(key); if (c) return JSON.parse(c); } catch {}
    try {
      const url = 'https://api-adresse.data.gouv.fr/search/?limit=1&q=' + encodeURIComponent(q);
      const r = await fetch(url);
      const j = await r.json();
      const f = j && j.features && j.features[0];
      if (!f) return null;
      const out = { lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0], label: f.properties.label };
      try { localStorage.setItem(key, JSON.stringify(out)); } catch {}
      return out;
    } catch { return null; }
  }

  // ---- Distance & trajet ---------------------------------------------------
  function haversineKm(a, b) {
    if (!a || !b) return null;
    const R = 6371, toR = (d) => d * Math.PI / 180;
    const dLat = toR(b.lat - a.lat), dLon = toR(b.lon - a.lon);
    const s = Math.sin(dLat / 2) ** 2 +
      Math.cos(toR(a.lat)) * Math.cos(toR(b.lat)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }

  // Estime le trajet chez-toi -> dépôt. Heuristique (haversine × facteur route).
  // Suffisant pour un GO/NO-GO ; remplaçable par un vrai routage (OSRM) plus tard.
  // `bulky` : un lot volumineux (100 PC, 8 TV…) impose un UTILITAIRE, quelle que
  // soit la distance — le train n'est alors pas une option, même au-delà de 3h30.
  function estimateTrip(homeCoord, depotCoord, cfg, bulky) {
    const s = Object.assign({}, DEFAULTS, cfg);
    const straight = haversineKm(homeCoord, depotCoord);
    if (straight == null) return { known: false };
    const km = Math.round(straight * 1.30);            // sinuosité routière
    const driveH = km / s.avgKmh;                       // temps de conduite (aller simple)
    const trips = s.roundTrip ? 2 : 1;
    const carCost = Math.round(km * (s.fuelPerKm + s.tollPerKm) * trips);
    const vanCost = Math.round(km * (s.fuelPerKm * 1.5 + s.tollPerKm) * trips + s.vanPerDay);
    const trainCost = Math.round((s.trainBase + km * s.trainPerKm) * trips);
    const mode = bulky ? 'van' : (driveH <= s.maxDriveH ? 'car' : 'train');
    const cost = mode === 'van' ? vanCost : mode === 'car' ? carCost : trainCost;
    const timeH = driveH * trips;
    const timeCost = Math.round(timeH * s.hourValue);
    return {
      known: true, km, driveH, mode, cost, carCost, vanCost, trainCost, timeH, timeCost,
      // Utilitaire imposé alors que la distance aurait suggéré le train.
      vanForced: mode === 'van' && driveH > s.maxDriveH,
    };
  }

  // ---- Horaires de retrait & faisabilité du déplacement ---------------------
  // Les pages de lot donnent le bloc "Lieu de dépôt" avec des horaires du type
  // "Lundi à vendredi 09h00-12h00 / 13h30-16h00". Le retrait n'est donc possible
  // qu'en semaine, en journée : c'est une contrainte aussi forte que l'argent.
  function parseHours(str) {
    const s = String(str || '');
    const out = [];
    const re = /(\d{1,2})\s*h\s*(\d{2})?\s*(?:-|–|—|à)\s*(\d{1,2})\s*h\s*(\d{2})?/gi;
    let m;
    while ((m = re.exec(s))) {
      const a = +m[1] + (+(m[2] || 0)) / 60;
      const b = +m[3] + (+(m[4] || 0)) / 60;
      if (b > a) out.push([a, b]);
    }
    const weekdayOnly = /lundi.*vendredi|du lundi au vendredi/i.test(s);
    return { intervals: out, weekdayOnly, raw: s };
  }

  const hhmm = (h) => {
    if (h == null || !isFinite(h)) return '—';
    const t = ((h % 24) + 24) % 24, H = Math.floor(t), M = Math.round((t - H) * 60);
    return H + 'h' + String(M === 60 ? 0 : M).padStart(2, '0');
  };

  // Plan de retrait : à quelle heure partir, retour, faisable dans la journée ?
  function planPickup(trip, hoursStr, cfg) {
    const s = Object.assign({}, DEFAULTS, cfg);
    const h = parseHours(hoursStr);
    if (!trip || !trip.known || !h.intervals.length) return { known: false, raw: h.raw, weekdayOnly: h.weekdayOnly };
    const open = Math.min(...h.intervals.map((i) => i[0]));
    const close = Math.max(...h.intervals.map((i) => i[1]));
    const departBy = open - trip.driveH;            // partir pour être à l'ouverture
    const backAt = open + s.loadHours + trip.driveH; // retour estimé
    const lastDepart = close - s.loadHours - trip.driveH; // au plus tard pour arriver à temps
    return {
      known: true, raw: h.raw, weekdayOnly: h.weekdayOnly, open, close, departBy, backAt,
      // Faisable en une journée si on ne part pas en pleine nuit et qu'on rentre le soir.
      sameDay: departBy >= 3 && backAt <= 22 && lastDepart >= departBy,
      earlyStart: departBy < 6,
      impossible: lastDepart < 0,   // même en partant à minuit on n'arrive pas avant la fermeture
      label: `Départ ${hhmm(departBy)} → ouverture ${hhmm(open)} → retour ~${hhmm(backAt)}`,
    };
  }

  // ---- Revente : quantité + cote + marge -----------------------------------
  // Extrait une quantité en tête de libellé ("100 PC portables ..." -> 100).
  function parseQty(name) {
    const m = (name || '').match(/^\s*(\d{1,4})\s*(?:x|×|\bunit|\bpc|\bpcs|\bpi[èe]ces|\blot)?/i);
    const q = m ? parseInt(m[1], 10) : 1;
    return (q >= 1 && q <= 5000) ? q : 1;
  }

  // Prix de revente unitaire estimé = médiane de la cote × (1 - marge visée).
  // (La cote vient de l'open data DNID ; l'analyse IA des photos peut la corriger
  //  via le champ lot.resale_override / lot.condition_factor.)
  function resaleUnit(lot, coteEntry, cfg) {
    const s = Object.assign({}, DEFAULTS, cfg);
    const override = num(lot.resale_override);
    if (override != null) return override;
    if (!coteEntry) return null;
    const cond = num(lot.condition_factor);            // 0..1 (état, complétude)
    const base = coteEntry.median * (1 - clampPct(s.marginPct) / 100);
    return Math.round(base * (cond != null ? cond : 1));
  }

  // ---- Deep-link leboncoin (occasion) — l'utilisateur l'ouvre lui-même -----
  // On ne requête jamais leboncoin : on fabrique juste l'URL de recherche.
  function leboncoinUrl(name) {
    const kw = (name || '')
      .replace(/^\s*\d{1,4}\s*(x|×)?\s*/i, '')          // retire la quantité de tête
      .replace(/lot de|lot|environ|pi[èe]ces?/gi, '')
      .replace(/\s+/g, ' ').trim().split(' ').slice(0, 6).join(' ');
    // sort_by=time (récents) ; l'utilisateur affine "état" sur place.
    return 'https://www.leboncoin.fr/recherche?text=' + encodeURIComponent(kw);
  }

  // ---- Regroupement par DÉPÔT + verdict ------------------------------------
  // lots : [{ name, description, depot, city, price, bid, qty?, resale_override?,
  //           condition_factor?, resellable?, bulky?, ... }]
  // coteFn(name) -> entrée de cote ({median, n, ...}) ou null.
  async function buildDepots(lots, coteFn, cfg) {
    const s = Object.assign({}, DEFAULTS, cfg);
    const home = await geocode(s.home);

    // 1) grouper par clé de dépôt (dépôt explicite sinon ville)
    const groups = new Map();
    for (const l of lots) {
      const key = (l.depot || l.city || 'Dépôt inconnu').trim();
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(l);
    }

    // 2) enrichir chaque dépôt
    const uniqWords = (s) => {
      const seen = new Set();
      return String(s).split(/\s+/).filter((w) => {
        const k = w.toLowerCase(); if (!w || seen.has(k)) return false; seen.add(k); return true;
      }).join(' ');
    };
    const depots = [];
    for (const [key, items] of groups) {
      const sample = items[0];
      // Requête de géocodage la PLUS précise possible : le code postal lève
      // l'ambiguïté des noms de commune homonymes (ex. plusieurs Saint-Grégoire).
      // La rue + le CP viennent du bloc "Lieu de dépôt" de la page du lot : c'est
      // la donnée la plus fiable (le nom du dépôt, lui, est souvent celui de la
      // grande ville — "MAGASIN DOMANIAL RENNES" alors qu'il est à Saint-Grégoire).
      const pc = sample.postcode || sample.zip || '';
      const street = sample.depot_street || sample.street || '';
      const geoQuery = street
        ? uniqWords([street, pc, sample.city].filter(Boolean).join(' '))
        : uniqWords([sample.depot, pc, sample.city].filter(Boolean).join(' ')) || key;
      const coord = await geocode(geoQuery);
      // Le caractère volumineux conditionne le MODE de transport : on le sait
      // avant de chiffrer le trajet.
      const bulkyHere = items.some((l) => l.bulky);
      const trip = estimateTrip(home, coord, s, bulkyHere);
      const pickup = planPickup(trip, sample.depot_hours, s);

      let buyTotal = 0, resaleTotal = 0, anyBulky = false;
      const enriched = items.map((l) => {
        const cote = coteFn ? coteFn(l.name) : null;
        const qty = num(l.qty) ?? parseQty(l.name);
        const unit = resaleUnit(l, cote, s);
        const buy = Math.max(num(l.bid) || 0, num(l.price) || 0);
        const resale = unit != null ? unit * qty : null;
        if (l.resellable !== false && resale != null) { buyTotal += buy; resaleTotal += resale; }
        if (l.bulky) anyBulky = true;
        return {
          ...l, qty, coteMedian: cote ? cote.median : null, coteN: cote ? cote.n : null,
          resaleUnit: unit, resaleTotal: resale, buy,
          lbcUrl: leboncoinUrl(l.name),
          resellable: l.resellable !== false && !!resale,
        };
      });

      // marge nette du dépôt = revente - achat - 1 trajet - coût du temps
      const tripCost = trip.known ? trip.cost : 0;
      const timeCost = trip.known ? trip.timeCost : 0;
      const grossMargin = resaleTotal - buyTotal;
      const net = grossMargin - tripCost - timeCost;
      const worth = net >= s.minNetPerTrip;

      // --- Tous les lots d'une vente se terminent EN MÊME TEMPS -------------
      // On mise donc sur plusieurs lots sans savoir lesquels on remportera,
      // alors que le trajet coûte pareil qu'on en gagne 1 ou 8. D'où :
      //  - breakEven : marge brute minimale à remporter ICI pour rentabiliser
      //  - soloOk    : ce lot, à lui seul, paie déjà le déplacement
      //  - basketMin : nb de lots (les meilleurs) nécessaires pour atteindre le seuil
      const breakEven = tripCost + timeCost + s.minNetPerTrip;
      for (const l of enriched) {
        l.lotNet = l.resellable ? (l.resaleTotal || 0) - l.buy : null;
        l.soloOk = l.lotNet != null && l.lotNet >= breakEven;
      }
      const ranked = enriched.filter((l) => l.lotNet != null && l.lotNet > 0)
        .sort((a, b) => b.lotNet - a.lotNet);
      let acc = 0, need = 0;
      for (const l of ranked) { if (acc >= breakEven) break; acc += l.lotNet; need++; }
      const basketMin = acc >= breakEven ? need : null;   // null = infaisable même en gagnant tout

      // Fin de vente (commune à tous les lots de la vente) + trésorerie max.
      const ends = items.map((l) => l.end).filter(Boolean).sort();
      const endAt = ends[0] || null;

      depots.push({
        key, coord, trip, pickup, lots: enriched, anyBulky,
        address: [street, pc, sample.city].filter(Boolean).join(', '),
        phone: sample.depot_phone || '', email: sample.depot_email || '',
        buyTotal, resaleTotal, grossMargin, tripCost, timeCost, net, worth,
        breakEven, basketMin, endAt, cashIfAll: buyTotal,
        verdict: !trip.known ? 'unknown' : worth ? 'go' : 'no',
      });
    }

    // 3) trier : GO d'abord, puis meilleure marge nette
    depots.sort((a, b) => (b.worth - a.worth) || (b.net - a.net));
    return { home, depots };
  }

  return { DEFAULTS, geocode, haversineKm, estimateTrip, resaleUnit, leboncoinUrl, parseQty,
           parseHours, planPickup, hhmm, buildDepots };
})();
