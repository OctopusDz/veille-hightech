'use strict';
// Portail high-tech : lit data/lots.json (produit par la collecte) + data/cote.json.
// Aucun appel à l'API du site ici : le portail est 100% statique.

const $ = (s) => document.querySelector(s);
const numOr = (v, d) => (v == null || v === '' || isNaN(+v)) ? d : +v;
const store = {
  get margin() { return +(localStorage.getItem('margin') ?? 40); },
  set margin(v) { localStorage.setItem('margin', v); },
  get topic() { return localStorage.getItem('ntfyTopic') || ''; },
  set topic(v) { localStorage.setItem('ntfyTopic', v); },
  get home() { return localStorage.getItem('home') || 'Yvelines'; },
  set home(v) { localStorage.setItem('home', v); },
  get minNet() { return numOr(localStorage.getItem('minNet'), 150); },
  set minNet(v) { localStorage.setItem('minNet', v); },
  get maxDriveH() { return numOr(localStorage.getItem('maxDriveH'), 3.5); },
  set maxDriveH(v) { localStorage.setItem('maxDriveH', v); },
  get toll() { return numOr(localStorage.getItem('toll'), 0.07); },
  set toll(v) { localStorage.setItem('toll', v); },
  get fuel() { return numOr(localStorage.getItem('fuel'), 0.12); },
  set fuel(v) { localStorage.setItem('fuel', v); },
};
// Config passée au moteur (Engine) à partir des réglages utilisateur.
const cfg = () => ({
  home: store.home, marginPct: store.margin, minNetPerTrip: store.minNet,
  maxDriveH: store.maxDriveH, tollPerKm: store.toll, fuelPerKm: store.fuel,
});
let cote = { cote: {} };
let lots = [];

// Cote : matching mot-clé -> bucket
const BUCKETS = [
  ['iPhone', /iphone/i], ['iPad', /ipad/i], ['MacBook', /macbook|mac ?book/i],
  ['iMac / Mac', /imac|mac ?mini|mac ?pro/i], ['Apple Watch', /apple ?watch/i], ['AirPods', /airpods/i],
  ['Smartphone Samsung', /samsung.*(galaxy|phone)|galaxy (s|a|note|z)\d/i],
  ['Smartphone (autre)', /smartphone|t[ée]l[ée]phone portable|xiaomi|huawei|oppo|\bpixel\b|oneplus/i],
  ['PC portable', /ordinateur portable|pc portable|laptop|thinkpad|latitude|elitebook|probook/i],
  ['PC fixe / boîtier', /unit[ée] centrale|pc fixe|boi?[ît]ier|ordinateur de bureau|\btour\b/i],
  ['Tablette', /tablette|tablet/i], ['TV / Téléviseur', /t[ée]l[ée]viseur|\btv\b|oled|qled/i],
  ['Console', /playstation|\bps[45]\b|xbox|nintendo|switch|console/i],
  ['Casque / Audio', /casque|enceinte|bose|\bjbl\b|sonos|home ?cinema|barre de son/i],
  ['Photo / Caméra', /appareil photo|reflex|gopro|cam[ée]ra|objectif|\bnikon\b|\bcanon\b/i],
  ['Drone', /drone|\bdji\b|parrot/i],
];
function matchCote(name) {
  for (const [b, re] of BUCKETS) if (re.test(name || '')) return cote.cote[b] ? { bucket: b, ...cote.cote[b] } : null;
  return null;
}
const suggestedMax = (c) => (c ? Math.round(c.median * (1 - store.margin / 100)) : null);
const euro = (v) => (v == null || v === '') ? '—' : (+v).toLocaleString('fr-FR') + ' €';
const escapeHtml = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtDate = (s) => { if (!s) return ''; const d = new Date(s); return isNaN(d) ? '' : d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }); };

// Normalise un lot (accepte la forme brute de l'API GraphQL ou une forme aplatie)
function norm(l) {
  return {
    sku: l.sku || l.uid || l.id,
    name: (l.name || '').trim(),
    category: l.category || l.categorie || '',
    lot_number: l.lot_number ?? l.lot ?? '',
    price: l.price_auction ?? l.price ?? null,
    bid: l.last_bid ?? l.bid ?? null,
    reserve: l.reserve_price ?? l.reserve ?? null,
    pro: !!(l.professional_only ?? l.pro),
    city: (l.dropoff_location && l.dropoff_location.city) || l.city || '',
    end: l.end_auction_lot_at || l.end || l.end_date || '',
    url: l.url || (l.url_key ? `https://encheres-domaine.gouv.fr/lot/${l.url_key}.html` : ''),
    image: (l.small_image && l.small_image.url) || l.image || '',
    status: l.lot_status_label || l.status || '',
    // Champs conservés pour le moteur (regroupement dépôt + verdict)
    description: l.description || (l.short_description && l.short_description.html) || '',
    // Bloc "Lieu de dépôt" de la page du lot (nom, rue, CP, ville, contact, horaires)
    depot: l.depot || l.dropoff || (l.dropoff_location && (l.dropoff_location.name || l.dropoff_location.label)) || '',
    depot_street: l.depot_street || l.street || (l.dropoff_location && (l.dropoff_location.street || l.dropoff_location.address)) || '',
    postcode: l.postcode || l.zip || (l.dropoff_location && (l.dropoff_location.postcode || l.dropoff_location.zip)) || '',
    depot_phone: l.depot_phone || (l.dropoff_location && l.dropoff_location.phone) || '',
    depot_email: l.depot_email || (l.dropoff_location && l.dropoff_location.email) || '',
    depot_hours: l.depot_hours || (l.dropoff_location && l.dropoff_location.hours) || '',
    qty: l.qty ?? l.quantity ?? null,
    condition_factor: l.condition_factor ?? null,
    resale_override: l.resale_override ?? null,
    bulky: l.bulky ?? false,
    resellable: l.resellable,
  };
}
function isDeal(l) {
  const c = matchCote(l.name); const max = suggestedMax(c);
  if (max == null) return false;
  const best = Math.max(+l.price || 0, +l.bid || 0);
  return best > 0 && best <= max;
}

document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
  document.querySelectorAll('.tabpane').forEach((x) => x.classList.remove('active'));
  t.classList.add('active'); $('#tab-' + t.dataset.tab).classList.add('active');
}));

function renderLots() {
  const q = ($('#lots-search').value || '').toLowerCase();
  const onlyDeals = $('#only-deals').checked;
  const hidePro = $('#hide-pro').checked;
  const arr = lots
    .filter((l) => !hidePro || !l.pro)
    .filter((l) => !onlyDeals || isDeal(l))
    .filter((l) => !q || l.name.toLowerCase().includes(q))
    .sort((a, b) => (isDeal(b) - isDeal(a)) || ((a.price || 1e9) - (b.price || 1e9)));
  $('#lots-count').textContent = arr.length;
  $('#lots-empty').hidden = lots.length > 0;
  $('#lots-grid').innerHTML = arr.map((l) => {
    const c = matchCote(l.name); const max = suggestedMax(c);
    const best = Math.max(+l.price || 0, +l.bid || 0);
    const deal = max != null && best > 0 && best <= max;
    const cls = max == null ? '' : deal ? 'ok' : 'warn';
    const maxLine = max == null ? `<div class="maxbid muted">cote inconnue</div>`
      : `<div class="maxbid ${cls}">Max conseillé ${euro(max)}${deal ? ' ✅' : ' ⚠︎'}</div>`;
    const coteLine = c ? `<div class="meta"><span>cote méd. ${euro(c.median)}</span><span>n=${c.n}</span></div>` : '';
    const img = l.image ? `style="background-image:url('${l.image.replace(/'/g, '')}')"` : '';
    return `<div class="lot">
      <div class="ph" ${img}>
        ${l.category ? `<span class="tag">${escapeHtml(l.category)}</span>` : ''}
        ${l.pro ? `<span class="pro">PRO</span>` : ''}
        ${deal ? `<span class="pro" style="left:6px;right:auto;top:auto;bottom:6px;background:var(--good);color:#04220f">BONNE AFFAIRE</span>` : ''}
      </div>
      <div class="body">
        <div class="name" title="${escapeHtml(l.name)}">${escapeHtml(l.name || '(sans nom)')}</div>
        <div class="prices"><span>Mise ${euro(l.price)}</span><span>Ench. ${euro(l.bid)}</span></div>
        ${maxLine}${coteLine}
        <div class="meta"><span>${escapeHtml(l.city)}</span><span>${fmtDate(l.end)}</span></div>
      </div>
      ${l.url ? `<a class="open" href="${l.url}" target="_blank" rel="noopener">Voir le lot →</a>` : ''}
    </div>`;
  }).join('');
}

function renderCote() {
  const q = ($('#cote-search').value || '').toLowerCase();
  const entries = Object.entries(cote.cote || {}).filter(([k]) => !q || k.toLowerCase().includes(q))
    .sort((a, b) => b[1].n - a[1].n);
  $('#cote-meta').textContent = cote.generated_at
    ? `Prix réels · open data DNID (${cote.license || 'Etalab'}) · maj ${new Date(cote.generated_at).toLocaleDateString('fr-FR')}`
    : '';
  $('#cote-grid').innerHTML = entries.map(([name, s]) => {
    const max = suggestedMax(s);
    return `<div class="cote"><h4>${name} <span class="n">n=${s.n}</span></h4><div class="bar"></div>
      <div class="stats">
        <span>min</span><b>${euro(s.min)}</b><span>p25</span><b>${euro(s.p25)}</b>
        <span>médiane</span><b>${euro(s.median)}</b><span>p75</span><b>${euro(s.p75)}</b>
        <span>max</span><b>${euro(s.max)}</b><span>max à miser</span><b style="color:var(--good)">${euro(max)}</b>
      </div></div>`;
  }).join('');
}

// coteFn pour le moteur : nom de lot -> entrée de cote (médiane, n…)
const coteFn = (name) => matchCote(name);

const fmtDT = (s) => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleString('fr-FR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); };
const fmtH = (h) => { if (h == null) return '—'; const m = Math.round(h * 60); return m < 60 ? m + ' min' : (Math.floor(m / 60) + 'h' + String(m % 60).padStart(2, '0')); };

async function renderDepots() {
  const grid = $('#depots-list');
  if (!lots.length) { $('#depots-empty').hidden = false; $('#depots-status').textContent = ''; grid.innerHTML = ''; $('#depots-count').textContent = 0; return; }
  $('#depots-empty').hidden = true;
  $('#depots-status').textContent = 'Calcul des trajets…';
  const { home, depots } = await Engine.buildDepots(lots, coteFn, cfg());
  const go = depots.filter((d) => d.verdict === 'go').length;
  $('#depots-count').textContent = go;
  $('#depots-status').textContent = home
    ? `Depuis ${home.label} · ${depots.length} dépôt(s) · ${go} à faire`
    : `⚠︎ point de départ « ${store.home} » introuvable — précise-le dans ⚙️`;

  grid.innerHTML = depots.map((d) => {
    const badge = d.verdict === 'go' ? `<span class="vb go">✅ GO</span>`
      : d.verdict === 'no' ? `<span class="vb no">✖ NON</span>`
      : `<span class="vb unk">? trajet</span>`;
    const t = d.trip;
    const icon = { car: '🚗', van: '🚚', train: '🚆' }[t.mode] || '🚗';
    const tripLine = t.known
      ? `<div class="trip">${icon} ${t.km} km · ${fmtH(t.driveH)} de route ·
          <b>${euro(t.cost)}</b> A/R <span class="muted">(+ ${euro(t.timeCost)} temps)</span>
          ${t.mode === 'van' ? '<span class="muted">· utilitaire (lot volumineux)</span>' : ''}</div>`
      : `<div class="trip muted">trajet inconnu (dépôt non géolocalisé)</div>`;
    const bulkyWarn = t.vanForced
      ? `<div class="warnbox">🚚 ${fmtH(t.driveH)} de route : au-delà de ton seuil train, mais le lot est
          volumineux → <b>utilitaire obligatoire</b> (location incluse dans le coût).</div>` : '';
    // Adresse exacte + contact du magasin domanial (bloc "Lieu de dépôt")
    const addr = d.address ? `<div class="addr">📍 ${escapeHtml(d.address)}
        <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(d.address)}" target="_blank" rel="noopener">itinéraire</a></div>` : '';
    const contact = (d.phone || d.email) ? `<div class="addr">
        ${d.phone ? `<a href="tel:${d.phone.replace(/\s/g, '')}">☎ ${escapeHtml(d.phone)}</a>` : ''}
        ${d.email ? `<a href="mailto:${escapeHtml(d.email)}">✉ écrire</a>` : ''}</div>` : '';
    // Retrait : horaires d'ouverture -> heure de départ, retour, faisabilité
    const p = d.pickup || {};
    const pickupBox = p.known
      ? `<div class="pickup ${p.impossible ? 'ko' : p.earlyStart ? 'warn' : 'ok'}">
          🕘 ${escapeHtml(p.raw)}<br>
          ⏱ ${p.label}
          ${p.impossible ? ' — <b>impossible dans la journée</b>'
            : p.sameDay ? (p.earlyStart ? ' — <b>départ très tôt</b>' : ' — faisable dans la journée')
            : ' — <b>prévoir une nuit sur place</b>'}
          ${p.weekdayOnly ? '<br>📅 Retrait <b>en semaine uniquement</b> (jour de congé à poser)' : ''}
        </div>`
      : (p.raw ? `<div class="pickup">🕘 ${escapeHtml(p.raw)}</div>` : '');
    const net = `<div class="net ${d.net >= store.minNet ? 'good' : 'bad'}">Marge nette ${euro(d.net)}</div>`;
    const money = `<div class="money">
        <span>Revente ~${euro(d.resaleTotal)}</span>
        <span>Achat ${euro(d.buyTotal)}</span>
        <span>Trajet −${euro(d.tripCost + d.timeCost)}</span>
      </div>`;
    // Tous les lots d'une vente closent ensemble : on mise sans savoir ce qu'on gagne.
    const risk = `<div class="risk">
        🎯 Seuil : <b>${euro(d.breakEven)}</b> de marge à remporter ici pour rentabiliser le trajet —
        ${d.basketMin === 1 ? `<b>le meilleur lot suffit</b>`
          : d.basketMin ? `il faut <b>les ${d.basketMin} meilleurs lots</b>`
          : `<span class="ko">infaisable même en gagnant tout</span>`}
      </div>
      <div class="money">
        <span>💶 Trésorerie si tu gagnes tout : ${euro(d.cashIfAll)}</span>
        ${d.endAt ? `<span>⏰ Clôture ${fmtDT(d.endAt)}</span>` : ''}
      </div>`;
    const rows = d.lots.map((l) => {
      const keep = l.resellable;
      const resale = l.resaleTotal != null ? euro(l.resaleTotal) : '—';
      const unit = l.resaleUnit != null ? `${euro(l.resaleUnit)}/u` : 'cote inconnue';
      return `<div class="drow ${keep ? '' : 'skip'}">
        <div class="dname">${escapeHtml(l.name)} ${l.qty > 1 ? `<span class="qty">×${l.qty}</span>` : ''}
          ${l.soloOk ? `<span class="solo">seul ✅ paie le trajet</span>` : ''}</div>
        <div class="dmeta">
          <span>Achat ${euro(l.buy)}</span>
          ${keep ? `<span>Revente ~${resale} <span class="muted">(${unit})</span></span>` : `<span class="muted">ignoré (non revendable)</span>`}
        </div>
        <div class="dlinks">
          <a href="${l.lbcUrl}" target="_blank" rel="noopener">🔎 leboncoin</a>
          ${l.url ? `<a href="${l.url}" target="_blank" rel="noopener">Voir le lot →</a>` : ''}
        </div>
      </div>`;
    }).join('');
    return `<div class="depot ${d.verdict}">
      <div class="dhead"><div class="dtitle">${escapeHtml(d.key)} ${badge}</div>${net}</div>
      ${addr}${tripLine}${bulkyWarn}${pickupBox}${money}${risk}${contact}
      <details><summary>${d.lots.length} lot(s)</summary>${rows}</details>
    </div>`;
  }).join('');
}

// Réglages
const dlg = $('#settings');
$('#btn-settings').addEventListener('click', () => {
  $('#set-home').value = store.home;
  $('#set-margin').value = store.margin; $('#margin-val').textContent = store.margin;
  $('#set-minnet').value = store.minNet; $('#minnet-val').textContent = store.minNet;
  $('#set-drive').value = store.maxDriveH; $('#drive-val').textContent = store.maxDriveH;
  $('#set-toll').value = store.toll; $('#set-fuel').value = store.fuel;
  $('#set-topic').value = store.topic; dlg.showModal();
});
$('#set-margin').addEventListener('input', (e) => $('#margin-val').textContent = e.target.value);
$('#set-minnet').addEventListener('input', (e) => $('#minnet-val').textContent = e.target.value);
$('#set-drive').addEventListener('input', (e) => $('#drive-val').textContent = e.target.value);
dlg.addEventListener('close', () => {
  if (dlg.returnValue === 'save') {
    store.home = $('#set-home').value.trim() || 'Yvelines';
    store.margin = +$('#set-margin').value; store.topic = $('#set-topic').value.trim();
    store.minNet = +$('#set-minnet').value; store.maxDriveH = +$('#set-drive').value;
    store.toll = numOr($('#set-toll').value, 0.07); store.fuel = numOr($('#set-fuel').value, 0.12);
    renderCote(); renderLots(); renderDepots();
  }
});
$('#lots-search').addEventListener('input', renderLots);
$('#only-deals').addEventListener('change', renderLots);
$('#hide-pro').addEventListener('change', renderLots);
$('#cote-search').addEventListener('input', renderCote);

(async function init() {
  try { cote = await (await fetch('data/cote.json?_=' + Date.now())).json(); } catch { cote = { cote: {} }; }
  try {
    const raw = await (await fetch('data/lots.json?_=' + Date.now())).json();
    const list = Array.isArray(raw) ? raw : (raw.lots || raw.items || []);
    lots = list.map(norm).filter((l) => l.sku && l.name);
    $('#lots-status').textContent = raw.updated
      ? `${lots.length} lots · maj ${new Date(raw.updated).toLocaleString('fr-FR')}`
      : `${lots.length} lots`;
  } catch { lots = []; $('#lots-status').textContent = ''; }
  renderCote(); renderLots(); renderDepots();
})();
