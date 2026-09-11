'use strict';
/* Interface de consultation des lots high-tech d'encheres-domaine.gouv.fr.
 * Lit site/data/lots.json (produit par la collecte) — aucun appel au site ici.
 * Les ventes en cours et à venir sont regroupées par dépôt. Les lots écartés
 * restent récupérables dans une vue dédiée, eux aussi regroupés par dépôt.
 * Dans chaque onglet, les lots sont regroupés par VILLE DE DÉPÔT, avec les
 * dates de début et de fin d'enchères. Un clic sur un dépôt ouvre ses lots. */

const $ = (s) => document.querySelector(s);
const esc = (s) => (s == null ? '' : String(s)).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const euro = (v) => (v == null || v === '') ? '—' : Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' €';

const DT = new Intl.DateTimeFormat('fr-FR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
const fmt = (s) => { const d = new Date(s); return isNaN(d) ? '—' : DT.format(d); };

// Temps restant avant la clôture, en clair.
function remain(end) {
  const ms = new Date(end) - Date.now();
  if (isNaN(ms)) return '';
  if (ms <= 0) return 'terminé';
  const h = Math.floor(ms / 36e5), d = Math.floor(h / 24);
  if (d >= 1) return `${d} j ${h % 24} h`;
  const m = Math.floor(ms / 6e4);
  return h >= 1 ? `${h} h ${m % 60} min` : `${m} min`;
}

let LOTS = [];
let ARCH = [];
let COTES = new Map();
let HOME = '';
const DEPOT_SORTS = ['lot', 'confidence', 'quick-margin', 'confidence-margin'];
function savedDepotSort() {
  try {
    const value = localStorage.getItem('depotSort');
    return DEPOT_SORTS.includes(value) ? value : 'lot';
  } catch { return 'lot'; }
}
let state = {
  status: 14,
  q: '',
  depot: null,
  depotSort: savedDepotSort(),
  dateFilter: 'all',
  trashDepot: 'all',
  trashStatus: 'all',
};

// Chiffres dynamiques d'une cote : l'enchère courante peut bouger après la
// création de l'estimation, donc le tri utilise le même calcul que la carte.
function acquisitionAtBid(cote, bid) {
  const current = Number(bid) || 0;
  const feeRate = Number(cote.auction_fee_rate_percent) || 11;
  const fees = Math.round(current * feeRate) / 100;
  const vatRate = cote.vat_status === 'mentionnee_a_ajouter' && cote.vat_rate_percent != null
    ? Number(cote.vat_rate_percent)
    : null;
  const vat = vatRate == null ? 0 : Math.round((current + fees) * vatRate) / 100;
  const purchaseTotal = Math.round((current + fees + vat) * 100) / 100;
  return { current, feeRate, fees, vatRate, vat, purchaseTotal };
}

function valuationNumbers(lot) {
  const cote = COTES.get(String(lot.id));
  if (!cote) return { confidence: -1, quickMargin: -Infinity, adjustedMargin: -Infinity };

  const bid = lot.bid != null && lot.bid !== '' ? lot.bid : lot.price;
  const acquisition = acquisitionAtBid(cote, bid);
  const confidence = Number(cote.confidence_percent) || 0;
  const quickMargin = Number(cote.quick_sale_lot_eur) - acquisition.purchaseTotal;

  return {
    ...acquisition, confidence, quickMargin,
    normalMargin: Number(cote.normal_resale_gross_eur) - acquisition.purchaseTotal,
    // Marge rapide pondérée par la fiabilité de l'estimation.
    adjustedMargin: quickMargin * confidence / 100,
  };
}

function renderCote(lot) {
  const cote = COTES.get(String(lot.id));
  if (!cote) return '<div class="cote missing">Cote indisponible pour ce lot.</div>';

  // Les cotes restent fixes pour cet instantané de marché, mais le coût d'achat
  // suit l'enchère courante de lots.json à chaque actualisation du SaaS.
  const { current, feeRate, fees, vatRate, vat, purchaseTotal, quickMargin, normalMargin } = valuationNumbers(lot);
  const maxBid = Number(cote.recommended_max_bid_eur);
  const maxAcquisition = Number.isFinite(maxBid) ? acquisitionAtBid(cote, maxBid) : null;
  const quickMarginAtMax = maxAcquisition
    ? Number(cote.quick_sale_lot_eur) - maxAcquisition.purchaseTotal
    : null;
  const maxBidExceeded = Number.isFinite(maxBid) && current > maxBid;
  const confidence = Number(cote.confidence_percent) || 0;
  const confidenceTone = confidence >= 70 ? 'high' : confidence >= 50 ? 'medium' : 'low';
  const confidenceLabel = confidence >= 70 ? 'bonne' : confidence >= 50 ? 'moyenne' : 'faible';
  const signedEuro = (value) => `${value >= 0 ? '+' : ''}${euro(value)}`;
  const currentVatLabel = vat
    ? ` + ${euro(vat)} de TVA (${vatRate} %)`
    : ' · aucune TVA ajoutée';
  const maxVatLabel = maxAcquisition && maxAcquisition.vat
    ? ` + ${euro(maxAcquisition.vat)} de TVA (${maxAcquisition.vatRate} %)`
    : ' · aucune TVA ajoutée';
  const sources = (cote.source_urls || []).map((url, index) =>
    `<a href="${esc(url)}" target="_blank" rel="noopener">source ${index + 1}</a>`
  ).join(' · ');
  const deviceChecks = (cote.device_checks || []).map((check) => {
    const verified = check.verification_basis === 'verified';
    const statusLabel = verified ? 'état contrôlé' : 'hypothèse prudente';
    const imeiLabel = check.imei_suffix ? `IMEI ••••${esc(check.imei_suffix)} · ` : '';
    return `<div class="cote-alert ${verified ? 'verified' : 'assumed'}">
      <b>${verified ? 'Contrôle appareil' : 'Risque appareil'} · ${esc(check.device)}</b>
      <strong>Localiser / verrouillage d’activation : ${esc(check.find_my_iphone)}</strong>
      <span>${esc(statusLabel)} · ${imeiLabel}${esc(check.valuation_effect)}</span></div>`;
  }).join('');

  return `<section class="cote" aria-label="Cote de revente estimée">
    <div class="cote-head">
      <div class="cote-title"><span>Estimation du lot</span><strong>Prix de revente</strong></div>
      <span class="confidence ${confidenceTone}">Confiance ${confidenceLabel} · ${confidence} %</span>
    </div>
    ${deviceChecks}
    <div class="cote-values">
      <div class="cote-value quick">
        <span>Si tu veux vendre vite</span>
        <b>${euro(cote.quick_sale_lot_eur)}</b>
        <small>prix prudent</small>
      </div>
      <div class="cote-value normal">
        <span>Si tu peux attendre</span>
        <b>${euro(cote.normal_resale_gross_eur)}</b>
        <small>revente normale</small>
      </div>
    </div>
    ${Number.isFinite(maxBid) ? `<div class="cote-limit${maxBidExceeded ? ' exceeded' : ''}">
      <div class="limit-heading">
        <span>Ta limite d’enchère</span>
        <strong>${maxBidExceeded ? 'Plafond dépassé' : 'Ne dépasse pas'}</strong>
      </div>
      <b class="limit-bid">${euro(maxBid)}</b>
      <div class="limit-total">
        <span>Total maximum à payer</span>
        <b>${euro(maxAcquisition.purchaseTotal)}</b>
        <small>${euro(maxBid)} d’enchère + ${euro(maxAcquisition.fees)} de frais (${feeRate} %)${maxVatLabel}</small>
      </div>
      <div class="limit-margin ${quickMarginAtMax >= 0 ? 'positive' : 'negative'}">
        <span>Marge estimée si tu revends vite</span>
        <b>${signedEuro(quickMarginAtMax)}</b>
        <small>si tu enchéris jusqu’à la limite</small>
      </div>
      ${maxBidExceeded ? `<em>N’enchéris plus : l’offre actuelle dépasse la limite de ${euro(current - maxBid)}.</em>` : ''}
    </div>` : ''}
    <div class="cote-current">
      <div class="current-heading">
        <span>Si tu remportes le lot maintenant</span>
        <strong>${euro(purchaseTotal)} à payer</strong>
      </div>
      <small>${euro(current)} d’enchère + ${euro(fees)} de frais (${feeRate} %)${currentVatLabel}</small>
      <div class="current-margin ${quickMargin >= 0 ? 'positive' : 'negative'}">
        <span>Marge estimée en vente rapide</span>
        <b>${signedEuro(quickMargin)}</b>
      </div>
    </div>
    <p class="cote-margin-note">Les marges sont avant transport, réparations, commissions de revente et temps de travail.</p>
    <div class="cote-meta">
      <span>Demande : <b>${esc(cote.demand)}</b></span>
      <span>Délai estimé : <b>${cote.estimated_sale_days_min} à ${cote.estimated_sale_days_max} jours</b></span>
    </div>
    <details class="cote-details">
      <summary>Pourquoi cette estimation ?</summary>
      <p><b>Marge estimée en revente normale aujourd’hui :</b> ${signedEuro(normalMargin)}</p>
      <p><b>Méthode :</b> ${esc(cote.valuation_method)}</p>
      <p><b>Risques :</b> ${esc(cote.main_risks)}</p>
      ${sources ? `<p><b>Comparables :</b> ${sources}</p>` : '<p>Estimation par inventaire et décote de risque, sans comparable direct retenu.</p>'}
    </details>
  </section>`;
}

// Filtre sur la date de clôture. Valeurs : 'all', 'today', 'd3', 'd7',
// ou une date de clôture exacte (chaîne ISO telle qu'elle vient des données).
function passeDate(end) {
  const f = state.dateFilter;
  if (f === 'all') return true;
  const d = new Date(end);
  if (isNaN(d)) return false;
  if (f === 'today') {
    const n = new Date();
    return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
  }
  if (f === 'd3' || f === 'd7') {
    const jours = f === 'd3' ? 3 : 7;
    return d - Date.now() <= jours * 864e5;
  }
  return end === f;
}

// Les dates proposées dépendent de l'onglet : on reconstruit la liste à chaque fois.
function majFiltreDates() {
  const sel = $('#fdate');
  const actifs = LOTS.filter((l) => l.status === state.status && !TRASH.has(l.id));
  const dates = [...new Set(actifs.map((l) => l.end))]
    .filter(Boolean).sort((a, b) => new Date(a) - new Date(b));
  const nb = (d) => actifs.filter((l) => l.end === d).length;

  sel.innerHTML = `<option value="all">Toutes les clôtures</option>
    <option value="today">Clôture aujourd'hui</option>
    <option value="d3">Sous 3 jours</option>
    <option value="d7">Sous 7 jours</option>
    <optgroup label="Dates de clôture">
      ${dates.map((d) => `<option value="${esc(d)}">${fmt(d)} — ${nb(d)} lot${nb(d) > 1 ? 's' : ''}</option>`).join('')}
    </optgroup>`;

  // On garde le choix courant s'il existe encore dans ce nouvel onglet.
  if (![...sel.options].some((o) => o.value === state.dateFilter)) state.dateFilter = 'all';
  sel.value = state.dateFilter;
  sel.classList.toggle('on', state.dateFilter !== 'all');
}

/* Poubelle : les lots écartés ne sont jamais supprimés, seulement masqués.
 *
 * Deux modes :
 *  - sans jeton : mémorisée dans ce navigateur seulement (perdue si on vide
 *    le cache, différente sur chaque appareil) ;
 *  - avec un jeton GitHub (fine-grained, limité à ce dépôt) : enregistrée dans
 *    site/data/poubelle.json du dépôt — partagée entre appareils, jamais perdue.
 *    Le dépôt est alors la source de vérité ; le navigateur n'est qu'un cache.
 * On garde l'identifiant du lot, pas sa position : le tri survit aux collectes. */
const GH = { repo: 'OctopusDz/veille-hightech', path: 'site/data/poubelle.json', branch: 'main' };
const TRASH = {
  key: 'lotsEcartes', tokenKey: 'ghToken',
  set: new Set(), sha: null, timer: null, etat: 'local', detail: '',
  get token() { try { return localStorage.getItem(this.tokenKey) || ''; } catch { return ''; } },
  set token(v) { try { v ? localStorage.setItem(this.tokenKey, v) : localStorage.removeItem(this.tokenKey); } catch {} },
  load() {
    try { this.set = new Set(JSON.parse(localStorage.getItem(this.key) || '[]')); }
    catch { this.set = new Set(); }
  },
  persist() { try { localStorage.setItem(this.key, JSON.stringify([...this.set])); } catch {} },
  has(id) { return this.set.has(String(id)); },
  toggle(id) {
    const k = String(id);
    if (this.set.has(k)) this.set.delete(k); else this.set.add(k);
    this.persist();
    if (this.token) { clearTimeout(this.timer); this.timer = setTimeout(() => this.push(), 1200); }
  },
  headers() {
    const h = { Accept: 'application/vnd.github+json' };
    if (this.token) h.Authorization = 'Bearer ' + this.token;
    return h;
  },
  url() { return `https://api.github.com/repos/${GH.repo}/contents/${GH.path}`; },
  // Lit la poubelle du dépôt et remplace la version locale.
  async pull() {
    if (!this.token) { this.etat = 'local'; return; }
    try {
      const r = await fetch(this.url() + `?ref=${GH.branch}&t=${Date.now()}`, { headers: this.headers() });
      if (r.status === 404) { this.sha = null; this.etat = 'ok'; this.detail = 'fichier absent (créé au 1er écart)'; return; }
      if (r.status === 401 || r.status === 403) { this.etat = 'ko'; this.detail = 'jeton refusé (' + r.status + ')'; return; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      this.sha = j.sha;
      const bin = atob((j.content || '').replace(/\n/g, ''));
      const txt = new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
      const data = JSON.parse(txt || '{}');
      this.set = new Set((data.ecartes || []).map(String));
      this.persist();
      this.etat = 'ok'; this.detail = `${this.set.size} lot(s) écarté(s), synchronisé`;
    } catch (e) { this.etat = 'ko'; this.detail = 'lecture impossible : ' + e.message; }
    majSync();
  },
  // Écrit la poubelle dans le dépôt (un commit par changement, regroupés).
  async push(retry = true) {
    if (!this.token) return;
    const body = JSON.stringify({ updated: new Date().toISOString(), ecartes: [...this.set] }, null, 1);
    const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(body)));
    try {
      const r = await fetch(this.url(), {
        method: 'PUT', headers: { ...this.headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `Poubelle : ${this.set.size} lot(s) écarté(s)`, content: b64,
                               branch: GH.branch, ...(this.sha ? { sha: this.sha } : {}) }),
      });
      if (r.status === 409 || r.status === 422) {
        // Le fichier a bougé (autre appareil) : on relit puis on réessaie une fois.
        if (retry) { await this.pull(); return this.push(false); }
        throw new Error('conflit');
      }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      this.sha = j.content && j.content.sha;
      this.etat = 'ok'; this.detail = `${this.set.size} lot(s) écarté(s), enregistré sur GitHub`;
    } catch (e) { this.etat = 'ko'; this.detail = 'enregistrement impossible : ' + e.message; }
    majSync();
  },
};
TRASH.load();

// Indicateur d'état de la poubelle, en haut à droite.
function majSync() {
  const el = $('#sync');
  if (!el) return;
  el.className = 'sync ' + (TRASH.etat === 'ok' ? 'ok' : TRASH.etat === 'ko' ? 'ko' : '');
  el.textContent = TRASH.etat === 'ok' ? '· poubelle synchronisée ✓'
    : TRASH.etat === 'ko' ? '· poubelle : erreur de synchro' : '· poubelle locale';
  el.title = TRASH.detail || '';
}

// --- Filtrage + regroupement par ville de dépôt ---------------------------
function visible() {
  const q = state.q.trim().toLowerCase();
  return LOTS.filter((l) => l.status === state.status)
    .filter((l) => !TRASH.has(l.id))
    .filter((l) => passeDate(l.end))
    .filter((l) => {
      if (!q) return true;
      return [l.name, l.desc, l.city, l.depot, l.org, l.lot].join(' ').toLowerCase().includes(q);
    });
}

function groupByDepot(lots) {
  const m = new Map();
  for (const l of lots) {
    const key = `${l.city}|${l.cp}`;
    if (!m.has(key)) {
      m.set(key, {
        key, city: l.city, cp: l.cp, depot: l.depot, street: l.street, org: l.org,
        start: l.start, end: l.end, contact: l.contact, phone: l.phone,
        email: l.email, hours: l.hours, access: l.access,
        km: l.km ?? null, heures: l.heures ?? null, lots: [],
      });
    }
    const g = m.get(key);
    g.lots.push(l);
    if (new Date(l.start) < new Date(g.start)) g.start = l.start;
    if (new Date(l.end) > new Date(g.end)) g.end = l.end;
  }
  // Classement : le plus proche de chez moi d'abord (distance inconnue en dernier).
  return [...m.values()].sort((a, b) =>
    (a.km ?? Infinity) - (b.km ?? Infinity) || new Date(a.end) - new Date(b.end));
}

// Durée de trajet estimée, en clair.
const fmtTrajet = (h) => {
  if (h == null) return '';
  const H = Math.floor(h), M = Math.round((h - H) * 60);
  return H ? `${H} h ${String(M).padStart(2, '0')}` : `${M} min`;
};

// --- Vue 1 : les dépôts ----------------------------------------------------
function renderDepots() {
  const lots = visible();
  const groups = groupByDepot(lots);
  $('#empty').hidden = groups.length > 0;
  if (!groups.length) {
    const sel = $('#fdate');
    const libelle = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent.trim() : '';
    $('#empty').textContent = state.dateFilter !== 'all'
      ? `Aucun lot avec ce filtre (${libelle})${state.q ? ' et cette recherche' : ''}. Repasse sur « Toutes les clôtures ».`
      : 'Aucun lot ne correspond à cette recherche.';
  }
  $('#hint').textContent = groups.length
    ? `${lots.length} lot${lots.length > 1 ? 's' : ''} sur ${groups.length} dépôt${groups.length > 1 ? 's' : ''}, du plus proche au plus loin de chez moi. Clique sur un dépôt pour voir ses lots.`
    : '';

  $('#depots').innerHTML = groups.map((g) => {
    const live = state.status === 14;
    const shots = g.lots.filter((l) => l.img).slice(0, 5);
    const strip = shots.map((l) => `<div style="background-image:url('${esc(l.img)}')"></div>`).join('')
      + (g.lots.length > 5 ? `<div class="more">+${g.lots.length - 5}</div>` : '');
    return `<article class="dep" data-key="${esc(g.key)}">
      <div class="dtop">
        <div class="city">${esc(g.city)}<span class="cp">${esc(g.cp)}</span></div>
        <div class="dname">${esc(g.depot || '')}${g.street ? ' · ' + esc(g.street) : ''}</div>
        <div class="drow">
          ${g.km != null ? `<span class="pill km">${g.km} km · ${fmtTrajet(g.heures)}</span>` : ''}
          <span class="pill n">${g.lots.length} lot${g.lots.length > 1 ? 's' : ''}</span>
          <span class="pill ${live ? 'live' : 'soon'}">${live ? 'Vente en cours' : 'Vente à venir'}</span>
          ${g.org ? `<span class="pill org">${esc(g.org)}</span>` : ''}
        </div>
      </div>
      <div class="dates">
        <div><span class="lbl">Début</span><b>${fmt(g.start)}</b></div>
        <div><span class="lbl">Fin</span><b>${fmt(g.end)}</b></div>
        <div><span class="lbl">${live ? 'Clôture dans' : 'Ouvre dans'}</span><span class="left">${live ? remain(g.end) : remain(g.start)}</span></div>
      </div>
      <div class="strip">${strip}</div>
    </article>`;
  }).join('');

  document.querySelectorAll('.dep').forEach((el) => {
    el.addEventListener('click', () => openDepot(el.dataset.key));
  });
}

// --- Vue 3 : les lots terminés (archive) ----------------------------------
function renderFin() {
  const q = state.q.trim().toLowerCase();
  const liste = ARCH
    .filter((l) => !q || [l.name, l.desc, l.city, l.depot, l.org, l.lot].join(' ').toLowerCase().includes(q))
    .sort((a, b) => new Date(b.end) - new Date(a.end));
  $('#fin-empty').hidden = liste.length > 0;
  if (!ARCH.length) $('#fin-empty').textContent = "Aucun lot terminé pour l'instant — l'archive se remplit à chaque clôture.";
  else if (!liste.length) $('#fin-empty').textContent = 'Aucun lot terminé ne correspond à cette recherche.';
  const vendus = liste.filter((l) => l.vendu).length;
  $('#hint-fin').textContent = liste.length
    ? `${liste.length} lot${liste.length > 1 ? 's' : ''} terminé${liste.length > 1 ? 's' : ''} · ${vendus} vendu${vendus > 1 ? 's' : ''} · ${liste.length - vendus} invendu${liste.length - vendus > 1 ? 's' : ''}. Du plus récent au plus ancien.`
    : '';
  $('#fin').innerHTML = liste.map((l) => {
    const dep = l.prixDepart, der = l.dernierBid, adj = l.prixAdjuge;
    const final = adj != null && adj !== 0 ? adj : der;
    const ecart = (final != null && dep != null) ? final - dep : null;
    return `<article class="lot fin">
      <div class="ph" style="background-image:url('${esc(l.img || '')}')">
        <div class="tags">${l.pro ? '<span class="tag pro">PRO</span>' : ''}<span class="tag">n°${esc(l.lot)}</span></div>
      </div>
      <div class="body">
        <h3>${esc(l.name)}</h3>
        <div class="where">${esc(l.city || '')}${l.cp ? ' (' + esc(l.cp) + ')' : ''}${l.depot ? ' · ' + esc(l.depot) : ''}</div>
        <div class="where">Clôturé le <b>${fmt(l.end)}</b> · <span class="badge ${l.vendu ? 'ok' : 'ko'}">${l.vendu ? 'Vendu' : 'Invendu'}</span>
          ${l.statutFinal ? `<span class="muted"> · ${esc(l.statutFinal)}</span>` : ''}</div>
        <div class="res">
          <div><span class="k">Mise à prix</span><span class="v">${euro(dep)}</span></div>
          <div class="arrow">→</div>
          <div><span class="k">${adj != null && adj !== 0 ? 'Adjugé' : 'Dernière enchère'}</span>
            <span class="v ${l.vendu ? 'win' : 'lost'}">${euro(final)}</span>
            ${ecart != null && ecart > 0 ? `<span class="k">+${ecart.toLocaleString('fr-FR')} € sur la mise</span>` : ''}</div>
        </div>
        ${l.desc ? `<div class="desc">${esc(l.desc)}</div><button class="more-btn">Lire la suite</button>` : ''}
      </div>
      <a class="go" href="${esc(l.url)}" target="_blank" rel="noopener">Annonce officielle ↗</a>
    </article>`;
  }).join('');
  document.querySelectorAll('#fin .more-btn').forEach((b) => b.addEventListener('click', () => {
    const d = b.previousElementSibling; d.classList.toggle('open');
    b.textContent = d.classList.contains('open') ? 'Réduire' : 'Lire la suite';
  }));
}

function depotKey(l) { return `${l.city}|${l.cp}`; }

function updateCounters() {
  $('#n14').textContent = LOTS.filter((l) => l.status === 14 && !TRASH.has(l.id)).length;
  $('#n13').textContent = LOTS.filter((l) => l.status === 13 && !TRASH.has(l.id)).length;
  $('#ntrash').textContent = LOTS.filter((l) => TRASH.has(l.id)).length;
}

// Vue dédiée : tous les lots écartés, regroupés par dépôt.
function renderTrash() {
  const tous = LOTS.filter((l) => TRASH.has(l.id));
  const depotSelect = $('#trash-depot');
  const depotGroups = groupByDepot(tous);
  const options = depotGroups.map((g) =>
    `<option value="${esc(g.key)}">${esc(g.city)} (${esc(g.cp)}) — ${g.lots.length}</option>`
  ).join('');
  depotSelect.innerHTML = `<option value="all">Tous les dépôts (${depotGroups.length})</option>${options}`;
  if (![...depotSelect.options].some((o) => o.value === state.trashDepot)) state.trashDepot = 'all';
  depotSelect.value = state.trashDepot;

  const q = state.q.trim().toLowerCase();
  const liste = tous
    .filter((l) => state.trashStatus === 'all' || l.status === Number(state.trashStatus))
    .filter((l) => state.trashDepot === 'all' || depotKey(l) === state.trashDepot)
    .filter((l) => !q || [l.name, l.desc, l.city, l.depot, l.org, l.lot].join(' ').toLowerCase().includes(q));
  const groups = groupByDepot(liste);

  $('#trash-empty').hidden = liste.length > 0;
  $('#hint-trash').textContent = liste.length
    ? `${liste.length} lot${liste.length > 1 ? 's' : ''} écarté${liste.length > 1 ? 's' : ''} dans ${groups.length} dépôt${groups.length > 1 ? 's' : ''}. La recherche en haut s'applique aussi ici.`
    : '';
  $('#trash-groups').innerHTML = groups.map((g) => `<section class="trash-depot-group">
    <header>
      <div><h2>${esc(g.city)} <span>${esc(g.cp)}</span></h2><p>${esc(g.depot || '')}${g.street ? ' · ' + esc(g.street) : ''}</p></div>
      <span class="pill trash">${g.lots.length} écarté${g.lots.length > 1 ? 's' : ''}</span>
    </header>
    <div class="grid-lots">${g.lots
      .slice()
      .sort((a, b) => (a.lot || 0) - (b.lot || 0))
      .map((l) => renderLotCard(l, true)).join('')}</div>
  </section>`).join('');

  bindLotCards($('#trash-groups'), renderTrash);
}

// Affiche la bonne vue selon l'onglet.
function afficherOnglet() {
  const fin = state.status === 'fin';
  const trash = state.status === 'trash';
  $('#view-fin').hidden = !fin;
  $('#view-trash').hidden = !trash;
  $('#view-depots').hidden = fin || trash || !!state.depot;
  $('#view-lots').hidden = fin || trash || !state.depot;
  $('#fdate').hidden = fin || trash;
  if (fin) renderFin();
  else if (trash) renderTrash();
  else renderDepots();
}

// --- Vue 2 : les lots d'un dépôt ------------------------------------------
function openDepot(key, silent) {
  let g = groupByDepot(visible()).find((x) => x.key === key);
  // Un filtre actif peut masquer le dépôt visé (ouverture par URL) : on lève
  // les filtres plutôt que d'échouer sans rien dire.
  if (!g && (state.dateFilter !== 'all' || state.q)) {
    state.dateFilter = 'all';
    state.q = '';
    $('#q').value = '';
    majFiltreDates();
    renderDepots();
    g = groupByDepot(visible()).find((x) => x.key === key);
  }
  if (!g) return false;
  state.depot = key;
  // URL propre : un dépôt = une adresse, qu'on peut mettre en favori.
  if (!silent) location.hash = state.status + '/' + encodeURIComponent(key);
  $('#view-depots').hidden = true;
  $('#view-trash').hidden = true;
  $('#view-fin').hidden = true;
  $('#view-lots').hidden = false;
  window.scrollTo(0, 0);

  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([g.street, g.cp, g.city].filter(Boolean).join(' '))}`;
  $('#dephead').innerHTML = `<div class="dephead">
    <h2>${esc(g.city)} <span style="color:var(--muted);font-weight:400;font-size:16px">${esc(g.cp)}</span></h2>
    <div class="sub">${esc(g.depot || '')}${g.org ? ' · organisateur ' + esc(g.org) : ''}</div>
    <div class="meta">
      ${g.street ? `<div><span class="k">Adresse</span><span class="v">${esc(g.street)}<br>${esc(g.cp)} ${esc(g.city)}</span><br><a href="${maps}" target="_blank" rel="noopener">Itinéraire ↗</a></div>` : ''}
      ${g.km != null ? `<div><span class="k">Depuis chez moi</span><span class="v"><b>${g.km} km</b><br>~${fmtTrajet(g.heures)} de route</span></div>` : ''}
      <div><span class="k">Enchères</span><span class="v">du <b>${fmt(g.start)}</b><br>au <b>${fmt(g.end)}</b></span></div>
      ${g.hours ? `<div><span class="k">Horaires</span><span class="v">${esc(g.hours)}</span></div>` : ''}
      ${g.access ? `<div><span class="k">Accès / retrait</span><span class="v">${esc(g.access)}</span></div>` : ''}
      ${(g.phone || g.email) ? `<div><span class="k">Contact</span><span class="v">${esc(g.contact || '')}</span>
        ${g.phone ? `<br><a href="tel:${esc(g.phone).replace(/\s/g, '')}">${esc(g.phone)}</a>` : ''}
        ${g.email ? `<br><a href="mailto:${esc(g.email)}">${esc(g.email)}</a>` : ''}</div>` : ''}
    </div>
  </div>`;

  renderDepotLots(g);
  return true;
}

function renderLotCard(l, discarded = false) {
  const n = (l.photos || []).length;
  const bid = l.bid != null && l.bid !== '';
  const action = discarded ? 'Remettre ce lot dans sa vente' : 'Écarter ce lot';
  return `<article class="lot${discarded ? ' ecarte' : ''}">
    <div class="ph" data-id="${l.id}" style="background-image:url('${esc(l.img || (l.photos || [])[0] || '')}')">
      <div class="tags">${l.pro ? '<span class="tag pro">PRO</span>' : ''}<span class="tag">n°${esc(l.lot)}</span></div>
      <button class="photo-bin${discarded ? ' restore' : ''}" data-bin="${l.id}" aria-label="${action}" title="${action}">${discarded ? '↩' : '🗑'}</button>
      ${n > 1 ? `<span class="nph">${n} photos</span>` : ''}
    </div>
    <div class="body">
      <h3>${esc(l.name)}</h3>
      <div class="price"><span class="v">${euro(bid ? l.bid : l.price)}</span>
        <span class="k">${bid ? 'enchère en cours' : 'mise à prix'}</span></div>
      ${renderCote(l)}
      ${l.desc ? `<div class="desc">${esc(l.desc)}</div>
        <button class="more-btn">Lire la suite</button>` : ''}
    </div>
    <a class="go" href="${esc(l.url)}" target="_blank" rel="noopener">Voir l'annonce officielle ↗</a>
  </article>`;
}

function bindLotCards(root, onToggle) {
  root.querySelectorAll('[data-bin]').forEach((b) => b.addEventListener('click', (e) => {
    e.stopPropagation();
    TRASH.toggle(b.dataset.bin);
    updateCounters();
    onToggle();
  }));
  root.querySelectorAll('.more-btn').forEach((b) => b.addEventListener('click', () => {
    const d = b.previousElementSibling;
    d.classList.toggle('open');
    b.textContent = d.classList.contains('open') ? 'Réduire' : 'Lire la suite';
  }));
  root.querySelectorAll('.lot .ph').forEach((p) => p.addEventListener('click', () => {
    const lot = LOTS.find((x) => String(x.id) === p.dataset.id);
    if (lot && (lot.photos || []).length) openViewer(lot.photos);
  }));
}

// Liste claire des lots conservés du dépôt. Les écartés ont leur propre écran.
function renderDepotLots(g) {
  const tieBreak = (a, b) => (Number(a.lot) || 0) - (Number(b.lot) || 0);
  const compare = (a, b) => {
    const av = valuationNumbers(a), bv = valuationNumbers(b);
    if (state.depotSort === 'confidence') return bv.confidence - av.confidence || tieBreak(a, b);
    if (state.depotSort === 'quick-margin') return bv.quickMargin - av.quickMargin || tieBreak(a, b);
    if (state.depotSort === 'confidence-margin') return bv.adjustedMargin - av.adjustedMargin || tieBreak(a, b);
    return tieBreak(a, b);
  };
  const gardes = g.lots
    .filter((l) => !TRASH.has(l.id))
    .sort(compare);

  if (!gardes.length) {
    closeDepot();
    renderDepots();
    return;
  }

  $('#lots').innerHTML = `<div class="bar">
      <span class="cnt">${gardes.length} lot${gardes.length > 1 ? 's' : ''} à examiner</span>
      <label class="sort-label">Trier par
        <select id="depot-sort" aria-label="Trier les lots du dépôt">
          <option value="lot"${state.depotSort === 'lot' ? ' selected' : ''}>Numéro de lot</option>
          <option value="confidence"${state.depotSort === 'confidence' ? ' selected' : ''}>Confiance : élevée → faible</option>
          <option value="quick-margin"${state.depotSort === 'quick-margin' ? ' selected' : ''}>Écart brut rapide : élevé → faible</option>
          <option value="confidence-margin"${state.depotSort === 'confidence-margin' ? ' selected' : ''}>Confiance + écart : meilleur d'abord</option>
        </select>
      </label>
      <span class="note">Pour écarter un lot, touche la poubelle en haut à droite de sa photo.</span>
    </div>
    <div class="grid-lots">${gardes.map((l) => renderLotCard(l)).join('')}</div>`;

  $('#depot-sort').addEventListener('change', (e) => {
    state.depotSort = e.target.value;
    try { localStorage.setItem('depotSort', state.depotSort); } catch {}
    renderDepotLots(g);
  });

  bindLotCards($('#lots'), () => {
    majFiltreDates();
    renderDepotLots(g);
  });
}

function closeDepot(silent) {
  state.depot = null;
  $('#view-lots').hidden = true;
  $('#view-depots').hidden = state.status === 'fin' || state.status === 'trash';
  if (!silent && location.hash) history.replaceState(null, '', location.pathname + location.search);
}

// --- Visionneuse photo -----------------------------------------------------
let vPhotos = [], vIdx = 0;
function openViewer(photos) { vPhotos = photos; vIdx = 0; $('#viewer').hidden = false; showPhoto(); }
function showPhoto() {
  $('#vimg').src = vPhotos[vIdx];
  $('#vcount').textContent = `${vIdx + 1} / ${vPhotos.length}`;
}
const step = (d) => { vIdx = (vIdx + d + vPhotos.length) % vPhotos.length; showPhoto(); };
$('#vclose').addEventListener('click', () => $('#viewer').hidden = true);
$('#vprev').addEventListener('click', () => step(-1));
$('#vnext').addEventListener('click', () => step(1));
$('#viewer').addEventListener('click', (e) => { if (e.target.id === 'viewer') $('#viewer').hidden = true; });
document.addEventListener('keydown', (e) => {
  if ($('#viewer').hidden) {
    if (e.key === 'Escape' && state.depot) { closeDepot(); renderDepots(); }
    return;
  }
  if (e.key === 'Escape') $('#viewer').hidden = true;
  if (e.key === 'ArrowLeft') step(-1);
  if (e.key === 'ArrowRight') step(1);
});

// --- Navigation ------------------------------------------------------------
function activateTab(status) {
  document.querySelectorAll('.tab').forEach((tab) => {
    const tabStatus = tab.dataset.st === 'fin' || tab.dataset.st === 'trash'
      ? tab.dataset.st
      : Number(tab.dataset.st);
    tab.classList.toggle('active', tabStatus === status);
  });
}

// Chrome modifie l'URL lors d'un clic sur Retour/Suivant sans recharger cette
// application. On doit donc relire le hash et remettre l'interface dans l'état
// correspondant, au lieu de laisser l'ancien dépôt affiché.
function applyRouteFromLocation() {
  const h = decodeURIComponent(location.hash.slice(1));

  if (h === 'fin' || h === 'trash') {
    state.status = h;
    state.depot = null;
    activateTab(h);
    afficherOnglet();
    return;
  }

  const slash = h.indexOf('/');
  if (slash > 0) {
    const status = Number(h.slice(0, slash));
    const key = h.slice(slash + 1);
    if (status === 13 || status === 14) {
      // L'ouverture normale a déjà rendu le dépôt avant que l'événement
      // hashchange arrive. Ce garde-fou évite de refaire tout le rendu.
      if (state.status === status && state.depot === key) return;
      state.status = status;
      state.depot = null;
      activateTab(status);
      majFiltreDates();
      renderDepots();
      if (!openDepot(key, true)) afficherOnglet();
      return;
    }
  }

  // URL sans hash : retour à la liste des dépôts. On conserve l'onglet
  // En cours/À venir qui était actif avant l'ouverture du dépôt.
  if (state.status !== 13 && state.status !== 14) state.status = 14;
  closeDepot(true);
  activateTab(state.status);
  majFiltreDates();
  afficherOnglet();
}

window.addEventListener('hashchange', applyRouteFromLocation);

$('#back').addEventListener('click', () => { closeDepot(); renderDepots(); });
document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
  t.classList.add('active');
  state.status = t.dataset.st === 'fin' || t.dataset.st === 'trash' ? t.dataset.st : +t.dataset.st;
  closeDepot(true);
  if (state.status === 13 || state.status === 14) majFiltreDates();
  if (state.status === 'fin' || state.status === 'trash') location.hash = state.status;
  else if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  afficherOnglet();
}));
$('#fdate').addEventListener('change', (e) => {
  state.dateFilter = e.target.value;
  e.target.classList.toggle('on', state.dateFilter !== 'all');
  if (state.depot) closeDepot();
  renderDepots();
});
$('#q').addEventListener('input', (e) => {
  state.q = e.target.value;
  if (state.depot) closeDepot();
  afficherOnglet();
});
$('#trash-status').addEventListener('change', (e) => {
  state.trashStatus = e.target.value;
  renderTrash();
});
$('#trash-depot').addEventListener('change', (e) => {
  state.trashDepot = e.target.value;
  renderTrash();
});

// --- Réglages : jeton GitHub pour la poubelle synchronisée ------------------
const dlgSet = $('#dlg-set');
$('#btn-set').addEventListener('click', () => {
  $('#set-token').value = TRASH.token;
  $('#set-status').textContent = TRASH.token ? (TRASH.detail || 'jeton enregistré') : 'aucun jeton : poubelle locale';
  dlgSet.showModal();
});
dlgSet.addEventListener('close', async () => {
  if (dlgSet.returnValue === 'clear') { TRASH.token = ''; TRASH.etat = 'local'; TRASH.detail = ''; majSync(); return; }
  if (dlgSet.returnValue !== 'save') return;
  const v = $('#set-token').value.trim();
  if (!v) return;
  TRASH.token = v;
  const locale = new Set(TRASH.set);          // ce qu'on avait avant d'activer la synchro
  await TRASH.pull();
  // Dépôt vide (ou fichier absent) mais poubelle locale remplie : on ne perd rien,
  // on envoie la locale sur GitHub.
  if (TRASH.etat === 'ok' && locale.size && TRASH.set.size === 0) {
    TRASH.set = locale; TRASH.persist(); await TRASH.push();
  }
  updateCounters();
  if (state.status === 13 || state.status === 14) majFiltreDates();
  afficherOnglet();
});

// --- Démarrage -------------------------------------------------------------
(async function init() {
  try {
    const raw = await (await fetch('data/lots.json?_=' + Date.now())).json();
    LOTS = raw.lots || [];
    HOME = (raw.home && raw.home.query) || '';
    $('#upd').textContent = raw.updated
      ? 'Données du ' + new Date(raw.updated).toLocaleString('fr-FR')
      : '';
  } catch { LOTS = []; $('#upd').textContent = 'données introuvables'; }
  try {
    const rawCotes = await (await fetch('data/cotes.json?_=' + Date.now())).json();
    COTES = new Map((rawCotes.lots || []).map((cote) => [String(cote.id), cote]));
  } catch { COTES = new Map(); }
  try { ARCH = (await (await fetch('data/archive.json?_=' + Date.now())).json()).lots || []; } catch { ARCH = []; }
  $('#nfin').textContent = ARCH.length;
  $('#upd').insertAdjacentHTML('beforeend', ' <span id="sync" class="sync"></span>');
  await TRASH.pull();
  majSync();
  updateCounters();

  // Reprise depuis l'URL : #fin, #trash ou #<statut>/<ville|cp>.
  // La même fonction gère ensuite les flèches Retour et Suivant de Chrome.
  applyRouteFromLocation();
})();
