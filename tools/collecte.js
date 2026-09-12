/* COLLECTE — à coller dans la console du navigateur, sur une page de
 * https://encheres-domaine.gouv.fr (par ex. /categorie-de-produit/high-tech.html).
 *
 * Pourquoi dans le navigateur : le site refuse les requêtes venant d'un autre
 * contexte (images comprises). Ici on rejoue simplement les appels que la page
 * fait déjà elle-même, dans une session normale. Aucun contournement.
 *
 * Produit deux téléchargements :
 *   1. lots-hightech.json    — les lots (dépôt, dates, prix, description, contact)
 *   2. photos-hightech.bin   — toutes les photos, redimensionnées, en une archive
 *
 * Ensuite, côté projet :   python3 tools/importer.py
 */
(async () => {
  const BASE = 'https://encheres-domaine.gouv.fr';
  const MEDIA = BASE + '/admin/media/catalog/product';
  const CAT = 'NDY=';                 // base64("46") = catégorie « High tech »
  const STATUTS = ['13', '14'];       // 13 = vente à venir, 14 = vente en cours
  const MAXPX = 1100, QUALITE = 0.82;
  const log = (...a) => console.log('[collecte]', ...a);

  const gq = async (q, op, v) => (await (await fetch(
    BASE + '/gateway/magento/graphql/?query=' + encodeURIComponent(q) +
    '&operationName=' + op + '&variables=' + encodeURIComponent(JSON.stringify(v)),
    { cache: 'no-store' }
  )).json());

  // NB : le serveur exige la signature complète (currentPage + sort), sinon 500.
  const Q_LISTE = `query getCategoryLots($currentPage:Int$filter:ProductAttributeFilterInput!$pageSize:Int$sort:ProductAttributeSortInput){products(currentPage:$currentPage filter:$filter pageSize:$pageSize sort:$sort){items{id sku lot_number name url_key lot_status lot_status_label start_auction_lot_at end_auction_lot_at start_date end_date price_auction last_bid reserve_price professional_only auction description{html}short_description{html}small_image{url}sales_inspector_data{cav_name}}total_count}}`;
  // dropoff_location est NULL dans la liste : il n'est rempli que sur le détail.
  const Q_DETAIL = `query getProductPageMain($urlKey:String!){products(filter:{url_key:{eq:$urlKey}}){items{id lot_status lot_status_label last_bid bid_winner_amount price_auction reserve_price dropoff_location_id dropoff_location{city postcode}dropoff_location_fo{name address city postcode}contact_dropoff_location{name email telephone physical_schedule tel_schedule}media_gallery_entries{file position disabled}}}}`;

  const strip = (h) => (h || '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&').replace(/&#039;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, ' ').trim();

  log('1/4 — liste des lots…');
  const liste = await gq(Q_LISTE, 'getCategoryLots', {
    currentPage: 1, pageSize: 300, sort: { start_auction_lot_at: 'ASC' },
    filter: { category_uid: { eq: CAT }, lot_status: { in: STATUTS } },
  });
  const bruts = liste.data.products.items;
  log(`   ${bruts.length} lots`);

  log('2/4 — détail de chaque lot (dépôt + photos)…');
  const lots = [];
  let i = 0;
  const worker = async () => {
    while (i < bruts.length) {
      const b = bruts[i++];
      let d = {};
      try {
        const j = await gq(Q_DETAIL, 'getProductPageMain', { urlKey: b.url_key });
        const it = j.data.products.items[0];
        const fo = it.dropoff_location_fo || {}, dl = it.dropoff_location || {}, c = it.contact_dropoff_location || {};
        d = {
          status: it.lot_status, statusLabel: it.lot_status_label,
          price: it.price_auction, bid: it.last_bid, reserve: it.reserve_price,
          bidVerified: true, bidCheckedAt: new Date().toISOString(),
          depot: (fo.name || '').trim() || null, street: (fo.address || '').trim() || null,
          city: (dl.city || fo.city || '').trim() || null, cp: (dl.postcode || fo.postcode || '').trim() || null,
          contact: (c.name || '').trim() || null, phone: (c.telephone || '').trim() || null,
          email: (c.email || '').trim() || null, hours: (c.tel_schedule || '').trim() || null,
          access: (c.physical_schedule || '').trim() || null,
          photos: (it.media_gallery_entries || []).filter((m) => !m.disabled)
            .sort((a, z) => a.position - z.position).map((m) => MEDIA + m.file),
        };
      } catch (e) { d = { photos: [] }; }
      lots.push(Object.assign({
        id: b.id, sku: b.sku, lot: b.lot_number, name: (b.name || '').trim(),
        status: b.lot_status, statusLabel: b.lot_status_label,
        start: b.start_auction_lot_at || b.start_date, end: b.end_auction_lot_at || b.end_date,
        price: b.price_auction, bid: b.last_bid, reserve: b.reserve_price,
        pro: !!b.professional_only, auction: b.auction,
        org: b.sales_inspector_data ? b.sales_inspector_data.cav_name : null,
        url: BASE + '/lot/' + b.url_key + '.html',
        desc: strip(b.description && b.description.html) || strip(b.short_description && b.short_description.html),
      }, d));
      await new Promise((r) => setTimeout(r, 80));
    }
  };
  await Promise.all([worker(), worker(), worker()]);

  const files = lots.flatMap((l) => (l.photos || []).map((u, n) => ({ id: l.id, n, u })));
  log(`3/4 — ${files.length} photos à récupérer et redimensionner…`);
  const bin = {};
  let k = 0;
  const grab = async () => {
    while (k < files.length) {
      const t = files[k++];
      try {
        const r = await fetch(t.u);
        if (!r.ok) throw new Error(r.status);
        const bm = await createImageBitmap(await r.blob());
        const s = Math.min(1, MAXPX / Math.max(bm.width, bm.height));
        const cv = new OffscreenCanvas(Math.round(bm.width * s), Math.round(bm.height * s));
        cv.getContext('2d').drawImage(bm, 0, 0, cv.width, cv.height);
        bm.close();
        bin[t.id + '_' + t.n] = new Uint8Array(await (await cv.convertToBlob({ type: 'image/jpeg', quality: QUALITE })).arrayBuffer());
      } catch (e) { /* photo ignorée */ }
      if (k % 50 === 0) log(`   ${k}/${files.length}`);
      await new Promise((r) => setTimeout(r, 40));
    }
  };
  await Promise.all([grab(), grab(), grab(), grab()]);

  log('4/4 — téléchargements…');
  const save = (blob, nom) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = nom;
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
  };

  save(new Blob([JSON.stringify({
    updated: new Date().toISOString(), source: 'encheres-domaine.gouv.fr — High tech (46)',
    count: lots.length, lots,
  })], { type: 'application/json' }), 'lots-hightech.json');

  const cles = Object.keys(bin).sort((a, z) => {
    const [ai, an] = a.split('_').map(Number), [zi, zn] = z.split('_').map(Number);
    return ai - zi || an - zn;
  });
  const manifest = cles.map((c) => { const [id, n] = c.split('_'); return { id: +id, n: +n, len: bin[c].length }; });
  const mj = new TextEncoder().encode(JSON.stringify(manifest));
  const entete = new TextEncoder().encode(String(mj.length).padStart(10, '0'));
  setTimeout(() => save(new Blob([entete, mj, ...cles.map((c) => bin[c])],
    { type: 'application/octet-stream' }), 'photos-hightech.bin'), 1500);

  log(`terminé : ${lots.length} lots, ${cles.length} photos.`);
})();
