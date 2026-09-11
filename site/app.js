'use strict';
/* Interface de consultation des lots high-tech d'encheres-domaine.gouv.fr.
 * Lit site/data/lots.json (produit par la collecte) — aucun appel au site ici.
 * Deux onglets : Vente en cours (statut 14) / Vente à venir (statut 13).
 * Dans chaque onglet, les lots sont regroupés par VILLE DE DÉPÔT, avec les
 * dates de début et de fin d'enchères. Un clic sur un dépôt ouvre ses lots. */

const $ = (s) => document.querySelector(s);
const esc = (s) => (s == null ? '' : String(s)).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const euro = (v) => (v == null || v === '') ? '—' : Number(v).toLocaleString('fr-FR') + ' €';

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
let HOME = '';
let state = { status: 14, q: '', depot: null, showTrash: false, dateFilter: 'all' };

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
  const dates = [...new Set(LOTS.filter((l) => l.status === state.status).map((l) => l.end))]
    .filter(Boolean).sort((a, b) => new Date(a) - new Date(b));
  const nb = (d) => LOTS.filter((l) => l.status === state.status && l.end === d).length;

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
 * Stockée dans le navigateur, elle survit aux rafraîchissements de données
 * (on garde l'identifiant du lot, pas sa position). */
const TRASH = {
  key: 'lotsEcartes',
  set: new Set(),
  load() {
    try { this.set = new Set(JSON.parse(localStorage.getItem(this.key) || '[]')); }
    catch { this.set = new Set(); }
  },
  save() { try { localStorage.setItem(this.key, JSON.stringify([...this.set])); } catch {} },
  has(id) { return this.set.has(String(id)); },
  toggle(id) {
    const k = String(id);
    if (this.set.has(k)) this.set.delete(k); else this.set.add(k);
    this.save();
  },
};
TRASH.load();

// --- Filtrage + regroupement par ville de dépôt ---------------------------
function visible() {
  const q = state.q.trim().toLowerCase();
  return LOTS.filter((l) => l.status === state.status)
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
    const gardes = g.lots.filter((l) => !TRASH.has(l.id));
    const ecartes = g.lots.length - gardes.length;
    const src = gardes.length ? gardes : g.lots;
    const shots = src.filter((l) => l.img).slice(0, 5);
    const strip = shots.map((l) => `<div style="background-image:url('${esc(l.img)}')"></div>`).join('')
      + (src.length > 5 ? `<div class="more">+${src.length - 5}</div>` : '');
    return `<article class="dep" data-key="${esc(g.key)}">
      <div class="dtop">
        <div class="city">${esc(g.city)}<span class="cp">${esc(g.cp)}</span></div>
        <div class="dname">${esc(g.depot || '')}${g.street ? ' · ' + esc(g.street) : ''}</div>
        <div class="drow">
          ${g.km != null ? `<span class="pill km">${g.km} km · ${fmtTrajet(g.heures)}</span>` : ''}
          <span class="pill n">${gardes.length} lot${gardes.length > 1 ? 's' : ''}</span>
          ${ecartes ? `<span class="pill trash">${ecartes} écarté${ecartes > 1 ? 's' : ''}</span>` : ''}
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
  state.showTrash = false;
  // URL propre : un dépôt = une adresse, qu'on peut mettre en favori.
  if (!silent) location.hash = state.status + '/' + encodeURIComponent(key);
  $('#view-depots').hidden = true;
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

// Liste des lots d'un dépôt : les retenus, ou la poubelle si on l'a ouverte.
function renderDepotLots(g) {
  const tries = g.lots.slice().sort((a, b) => (a.lot || 0) - (b.lot || 0));
  const gardes = tries.filter((l) => !TRASH.has(l.id));
  const ecartes = tries.filter((l) => TRASH.has(l.id));
  // Poubelle vidée pendant qu'on la regarde : on revient tout seul à la liste,
  // sinon on reste bloqué sur un écran vide.
  if (state.showTrash && !ecartes.length) state.showTrash = false;
  const liste = state.showTrash ? ecartes : gardes;

  // Dans la poubelle, le retour doit ramener aux lots retenus DE CE DÉPÔT,
  // pas à la liste de tous les dépôts.
  const barre = state.showTrash
    ? `<div class="bar">
        <button class="tgl retour" id="tgl-trash">← Retour aux ${gardes.length} lot${gardes.length > 1 ? 's' : ''} retenu${gardes.length > 1 ? 's' : ''}</button>
        <span class="cnt">🗑 Poubelle — ${ecartes.length} lot${ecartes.length > 1 ? 's' : ''} écarté${ecartes.length > 1 ? 's' : ''}</span>
        <span class="note">« ↩ Remettre » les fait revenir dans la liste.</span>
      </div>`
    : `<div class="bar">
        <span class="cnt">${gardes.length} lot${gardes.length > 1 ? 's' : ''} retenu${gardes.length > 1 ? 's' : ''}</span>
        ${ecartes.length ? `<button class="tgl" id="tgl-trash">🗑 Poubelle (${ecartes.length})</button>` : ''}
      </div>`;

  const cartes = liste.map((l) => {
    const n = (l.photos || []).length;
    const bid = l.bid != null && l.bid !== '';
    const dans = TRASH.has(l.id);
    return `<article class="lot${dans ? ' ecarte' : ''}">
      <div class="ph" data-id="${l.id}" style="background-image:url('${esc(l.img || (l.photos || [])[0] || '')}')">
        <div class="tags">${l.pro ? '<span class="tag pro">PRO</span>' : ''}<span class="tag">n°${esc(l.lot)}</span></div>
        ${n > 1 ? `<span class="nph">${n} photos</span>` : ''}
      </div>
      <div class="body">
        <h3>${esc(l.name)}</h3>
        <div class="price"><span class="v">${euro(bid ? l.bid : l.price)}</span>
          <span class="k">${bid ? 'enchère en cours' : 'mise à prix'}</span></div>
        ${l.desc ? `<div class="desc">${esc(l.desc)}</div>
          <button class="more-btn">Lire la suite</button>` : ''}
      </div>
      <div class="actions">
        <button class="bin" data-bin="${l.id}">${dans ? '↩ Remettre' : '🗑 Écarter'}</button>
        <a class="go" href="${esc(l.url)}" target="_blank" rel="noopener">Annonce officielle ↗</a>
      </div>
    </article>`;
  }).join('');

  const vide = !liste.length
    ? `<p class="empty">${state.showTrash ? 'La poubelle est vide.' : 'Tous les lots de ce dépôt sont écartés. Ouvre la poubelle pour en récupérer.'}</p>`
    : '';

  $('#lots').innerHTML = barre + `<div class="grid-lots">${cartes}</div>` + vide;

  const tgl = $('#tgl-trash');
  if (tgl) tgl.addEventListener('click', () => { state.showTrash = !state.showTrash; renderDepotLots(g); });

  document.querySelectorAll('[data-bin]').forEach((b) => b.addEventListener('click', (e) => {
    e.stopPropagation();
    TRASH.toggle(b.dataset.bin);
    renderDepotLots(g);
  }));
  document.querySelectorAll('.more-btn').forEach((b) => b.addEventListener('click', () => {
    const d = b.previousElementSibling;
    d.classList.toggle('open');
    b.textContent = d.classList.contains('open') ? 'Réduire' : 'Lire la suite';
  }));
  document.querySelectorAll('.lot .ph').forEach((p) => p.addEventListener('click', () => {
    const lot = LOTS.find((x) => String(x.id) === p.dataset.id);
    if (lot && (lot.photos || []).length) openViewer(lot.photos);
  }));
}

function closeDepot(silent) {
  state.depot = null;
  $('#view-lots').hidden = true;
  $('#view-depots').hidden = false;
  if (!silent && location.hash) history.replaceState(null, '', location.pathname);
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
  if ($('#viewer').hidden) { if (e.key === 'Escape' && state.depot) closeDepot(); return; }
  if (e.key === 'Escape') $('#viewer').hidden = true;
  if (e.key === 'ArrowLeft') step(-1);
  if (e.key === 'ArrowRight') step(1);
});

// --- Navigation ------------------------------------------------------------
$('#back').addEventListener('click', closeDepot);
document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
  t.classList.add('active');
  state.status = +t.dataset.st;
  closeDepot();
  majFiltreDates();
  renderDepots();
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
  renderDepots();
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
  $('#n14').textContent = LOTS.filter((l) => l.status === 14).length;
  $('#n13').textContent = LOTS.filter((l) => l.status === 13).length;

  // Reprise depuis l'URL : #<statut>/<ville|cp>
  const h = decodeURIComponent(location.hash.slice(1));
  const slash = h.indexOf('/');
  if (slash > 0) {
    const st = +h.slice(0, slash);
    if (st === 13 || st === 14) {
      state.status = st;
      document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', +t.dataset.st === st));
    }
    majFiltreDates();
    renderDepots();
    openDepot(h.slice(slash + 1), true);
    return;
  }
  majFiltreDates();
  renderDepots();
})();
