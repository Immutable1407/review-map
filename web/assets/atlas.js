(() => {
  'use strict';

  /* ------------------------------------------------------------
     data
     ------------------------------------------------------------ */
  const CATS = [
    { name: '美食', glyph: '吃', color: '#C8452C', en: 'Food' },
    { name: '甜品', glyph: '甜', color: '#B85C7A', en: 'Sweet' },
    { name: '咖啡', glyph: '咖', color: '#8A6440', en: 'Coffee' },
    { name: '酒吧', glyph: '酌', color: '#5F4E86', en: 'Bar' },
    { name: '公园', glyph: '园', color: '#4C7A5A', en: 'Park' },
    { name: '展馆', glyph: '展', color: '#3E7480', en: 'Gallery' },
    { name: '小店', glyph: '逛', color: '#B0813C', en: 'Shop' },
    { name: '游玩', glyph: '游', color: '#3F6E8C', en: 'Outing' }
  ];
  const CAT = Object.fromEntries(CATS.map((c) => [c.name, c]));
  const CAT_COLOR = Object.fromEntries(CATS.map((c) => [c.name, c.color]));
  const CITY_EN = {
    北京: 'Beijing', 上海: 'Shanghai', 天津: 'Tianjin', 大连: 'Dalian',
    深圳: 'Shenzhen', 广州: 'Guangzhou', 澳门: 'Macau', 杭州: 'Hangzhou', 武汉: 'Wuhan'
  };

  // Generated place IDs / GCJ-02 coordinates remain authoritative. Convert only
  // the display copy for the WGS84 basemap; navigation retains original values.
  const PLACES = (window.PLACES_DATA || []).map((p, i) => {
    const [lng, lat] = gcoord.transform([...p.location], gcoord.GCJ02, gcoord.WGS84);
    return {...p, city: p.city.replace(/市$/, ''), food: p.recommendedFood || [], lng, lat, no: i + 1};
  });
  const byId = new Map(PLACES.map((p) => [p.id, p]));
  const CITY_ORDER = ['北京', '上海', '天津', '大连', '深圳', '广州', '澳门', '杭州', '武汉'];
  const cityRank = (c) => (CITY_ORDER.indexOf(c) === -1 ? 99 : CITY_ORDER.indexOf(c));

  const state = { city: '北京', cat: '全部', q: '', id: null };
  const detail = { editing: false, rating: 0, revision: 0, epoch: 0, section: null };
  const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const motion = duration => reducedMotion() ? 0 : duration;

  /* ---------------- real session + durable review API ---------------- */
  let owner = false, connected = false, reviews = {}, syncVersion = 0, refreshSequence = 0;
  const pending = new Set();
  const api = new URL('./api/', location.href);
  const draftKey = id => `map-review-draft:${id}`;
  function loadDraft(id) { try { return JSON.parse(localStorage.getItem(draftKey(id)) || 'null'); } catch { return null; } }
  function keepDraft() {
    const ta = document.querySelector('#revText');
    if (!state.id || !ta || !owner || detail.section !== 'review') return;
    try { localStorage.setItem(draftKey(state.id), JSON.stringify({rating: detail.rating, comment: ta.value, revision: detail.revision})); } catch {}
  }
  function discardDraft(id) { try { localStorage.removeItem(draftKey(id)); } catch {} }
  function safeRenderReview() {
    const p = byId.get(state.id);
    if (!p) return;
    const section = document.querySelector('.reviews');
    if (section) section.outerHTML = reviewSection(p);
    const summary = document.querySelector('[data-review-summary]');
    if (summary) summary.textContent = reviews[p.id]?.rating ? '★ ' + reviews[p.id].rating : '';
  }
  async function request(path, method = 'GET', body) {
    const response = await fetch(new URL(path, api), {method, credentials: 'same-origin', signal: AbortSignal.timeout(15000),
      headers: {'Content-Type':'application/json','X-Personal-Review':'1'}, body: body === undefined ? undefined : JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) { keepDraft(); owner = false; detail.editing = false; accountUI(); safeRenderReview(); }
      const error = new Error(data.error || '请求失败，请重试。'); error.status = response.status; throw error;
    }
    return data;
  }
  async function refreshReviews() {
    const version = syncVersion, sequence = ++refreshSequence;
    try {
      const [session, data] = await Promise.all([request('session'),request('reviews')]);
      if (version !== syncVersion || sequence !== refreshSequence) return;
      const changed = JSON.stringify(reviews) !== JSON.stringify(data.reviews || {}), connectionChanged = !connected;
      reviews = data.reviews || {}; connected = true;
      if (owner && !session.owner) { keepDraft(); detail.editing = false; }
      const ownerChanged = owner !== session.owner; owner = session.owner; accountUI();
      if ((changed || ownerChanged || connectionChanged) && (!owner || detail.section !== 'review' || !document.querySelector('#revText'))) safeRenderReview();
      lockEditor(pending.has(state.id));
      if (changed && (!isMobile() || document.body.classList.contains('sheet-open'))) renderList();
    } catch { if (version === syncVersion && sequence === refreshSequence) { connected = false; accountUI(); } }
  }
  const reviewFor = (id) => reviews[id] || null;

  function starRow(n, size) {
    let out = '';
    for (let i = 1; i <= 5; i++) out += `<span class="${i <= n ? '' : 'off'}">★</span>`;
    return `<span class="stars" aria-label="${n} out of 5">${out}</span>`;
  }
  function fmtDay(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  }

  function accountUI() {
    const btn = $('#account');
    if (!btn) return;
    btn.classList.toggle('is-in', owner);
    $('#accLabel').textContent = owner ? '已登录' : '登录';
    btn.setAttribute('aria-label', owner ? '登录设置' : '登录');
    $('#mAccount').textContent = owner ? '已登录' : '登录';
    $('#serviceState').textContent = connected ? (owner ? '已登录' : '公开浏览') : '评价未连接';
    $('#authGuest').hidden = owner;
    $('#authOwner').hidden = !owner;
  }

  function openAuth() {
    accountUI();
    $('#authErr').textContent = '';
    const dlg = $('#authDialog');
    if (!dlg.open) dlg.showModal();
    if (!owner) setTimeout(() => $('#authPass').focus(), 60);
  }
  function closeAuth() {
    const dlg = $('#authDialog');
    if (dlg.open) dlg.close();
    $('#authPass').value = '';
    $('#authErr').textContent = '';
  }

  async function signIn(pass) {
    const button = $('#authForm button[type=submit]'); button.disabled = true; syncVersion++;
    try {
      await request('session','POST',{password:pass});
      owner = true; connected = true; syncVersion++; closeAuth(); accountUI(); safeRenderReview();
      showToast('已登录');
    } catch (error) { $('#authErr').textContent = error.message; }
    finally { button.disabled = false; }
  }

  async function signOut() {
    $('#authOut').disabled = true; syncVersion++;
    try {
      await request('logout','POST',{}); keepDraft(); owner = false; detail.editing = false; syncVersion++;
      closeAuth(); accountUI(); safeRenderReview(); showToast('已退出登录');
    } catch (error) { showToast(error.message); }
    finally { $('#authOut').disabled = false; }
  }

  function reviewSection(p) {
    const rev = reviewFor(p.id);
    const showForm = owner && (detail.editing || !rev);
    const saved = loadDraft(p.id);
    if (showForm) { detail.rating = saved?.rating ?? detail.rating; detail.revision = rev?.revision || 0; }
    const rating = showForm ? detail.rating : (rev ? rev.rating : 0);
    let html = `<section class="reviews" aria-label="评价">
      <div class="rev-head">
        <span class="lbl">个人评价</span>
        ${rev && rev.rating ? `<span class="avg">${Number(rev.rating).toFixed(1)}<small>/ 5</small></span>` : ''}
      </div>`;

    if (rev) {
      html += `<div class="rev-card">
        <div class="rev-meta">
          ${rev.rating ? starRow(rev.rating) : '<span></span>'}
          <span>${fmtDay(rev.updatedAt)}</span>
        </div>
        ${rev.comment ? `<p class="rev-text">${esc(rev.comment)}</p>` : ''}
        ${owner ? `<div class="rev-actions"><button data-act="edit-review">${detail.editing ? '取消' : '编辑'}</button><button data-act="del-review" ${pending.has(p.id) ? 'disabled' : ''}>删除</button></div>` : ''}
      </div>`;
    }

    if (showForm) {
      html += `<form class="rev-form" id="revForm">
        <div class="rate" role="radiogroup" aria-label="评分">
          ${[1,2,3,4,5].map((n) => `<button type="button" class="${n <= rating ? 'on' : ''}" data-star="${n}" role="radio" tabindex="${n === (rating || 1) ? '0' : '-1'}" aria-checked="${n === rating}" aria-label="${n} 星">★</button>`).join('')}
        </div>
        <button type="button" class="rev-open" data-act="clear-rating">清除评分</button>
        <label for="revText" class="sr-only">评价</label>
        <textarea id="revText" maxlength="5000" placeholder="写下菜品、环境，或下次想试的…">${esc(saved?.comment ?? rev?.comment ?? '')}</textarea>
        <div class="foot">
          <span class="hint">${rating ? rating + ' / 5' : '评分可选'}</span>
          <button class="save" type="submit" ${pending.has(p.id) || !connected ? 'disabled' : ''}>${pending.has(p.id) ? '保存中…' : '保存评价'}</button>
        </div>
        <p class="rev-error" role="alert">${saved && saved.revision !== detail.revision ? '此地点已有更新，草稿已保留，请核对后再保存。' : ''}</p>
      </form>`;
    } else if (!owner && !rev) {
      html += `<p class="rev-note">${connected ? '暂无评价' : '评价服务暂未连接'}</p><p class="rev-guest"><button data-act="signin">登录后评价</button></p>`;
    } else if (owner && rev && !detail.editing) {
      /* review card already shows edit */
    }
    html += '</section>';
    return html;
  }

  async function commitReview(p) {
    if (!owner || pending.has(p.id)) return;
    const ta = plate.querySelector('#revText');
    const text = ta ? ta.value.trim() : '';
    const rating = detail.rating || 0;
    if (!rating && !text) { showToast('选一个评分，或写下一句评价。'); return; }
    const id = p.id, epoch = detail.epoch;
    keepDraft(); pending.add(id); syncVersion++; lockEditor(true);
    try {
      const result = await request(`reviews/${encodeURIComponent(id)}`,'PUT',{...reviews[id],rating,comment:text,revision:detail.revision});
      reviews[id] = result.review; syncVersion++;
      if (state.id === id && detail.epoch === epoch) { discardDraft(id); detail.editing = false; safeRenderReview(); }
      else { const draft = loadDraft(id); if (draft?.rating === rating && draft.comment.trim() === text) discardDraft(id); }
      if (!isMobile() || document.body.classList.contains('sheet-open')) renderList();
      showToast('评价已保存');
    } catch (error) {
      const message = error.status === 409 ? '评价已在其他页面更新，草稿已保留。请取消后刷新，再核对保存。' : error.message;
      if (state.id === id && detail.epoch === epoch) { const el = plate.querySelector('.rev-error'); if (el) el.textContent = message; }
      showToast(message);
    } finally { pending.delete(id); lockEditor(pending.has(state.id)); }
  }

  async function removeReview(p) {
    if (!owner || pending.has(p.id) || !confirm('删除这条评价？')) return;
    const id = p.id, epoch = detail.epoch, revision = reviews[id]?.revision || 0;
    pending.add(id); syncVersion++; lockEditor(true);
    try {
      await request(`reviews/${encodeURIComponent(id)}`,'DELETE',{revision});
      delete reviews[id]; syncVersion++; discardDraft(id);
      if (state.id === id && detail.epoch === epoch) { detail.editing = false; detail.rating = 0; safeRenderReview(); }
      if (!isMobile() || document.body.classList.contains('sheet-open')) renderList();
      showToast('评价已删除');
    } catch (error) { showToast(error.message); }
    finally { pending.delete(id); lockEditor(pending.has(state.id)); }
  }

  function lockEditor(busy) {
    plate.querySelectorAll('#revForm button, #revForm textarea, [data-act="del-review"]').forEach(el => { el.disabled = busy; });
    const save = plate.querySelector('#revForm .save');
    if (save) { save.disabled = busy || !connected; save.textContent = busy ? '保存中…' : '保存评价'; }
    const form = plate.querySelector('#revForm'); if (form) form.setAttribute('aria-busy',String(busy));
  }

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  const pad = (n) => String(n).padStart(3, '0');
  const isMobile = () => matchMedia('(max-width: 860px)').matches;
  const panelWidth = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--panel-w')) || 360;
  const plateWidth = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--plate-w')) || 336;
  const overviewPadding = () => isMobile() ? {top:90,bottom:50,left:30,right:30} : {top:60,bottom:60,left:panelWidth()+50,right:50};
  const selectedPadding = () => isMobile() ? {top:56,bottom:Math.round(innerHeight*.62),left:20,right:20} : {top:60,bottom:60,left:panelWidth()+40,right:plateWidth()+40};

  function haystack(p) {
    return [p.name, p.savedName, p.city, p.district, p.address, p.category, (p.food || []).join(' '), p.note]
      .join(' ').toLowerCase();
  }
  function searchActive() { return state.q.trim().length > 0; }

  function matchQ(p) {
    const q = state.q.trim().toLowerCase();
    return !q || haystack(p).includes(q);
  }
  function matches(p) {
    if (state.cat !== '全部' && !(p.tags || [p.category]).includes(state.cat)) return false;
    if (state.city !== '全部' && p.city !== state.city) return false;
    return matchQ(p);
  }

  let current = [];
  let mobileShown = 60;
  function compute() {
    current = PLACES.filter(matches).sort((a, b) => {
      const c = cityRank(a.city) - cityRank(b.city);
      if (c) return c;
      const ca = CATS.findIndex((x) => x.name === a.category);
      const cb = CATS.findIndex((x) => x.name === b.category);
      if (ca !== cb) return ca - cb;
      return a.name.localeCompare(b.name, 'zh');
    });
    return current;
  }

  function cityCount(city) {
    return PLACES.filter((p) => (city === '全部' || p.city === city) && matchQ(p) && (state.cat === '全部' || (p.tags || [p.category]).includes(state.cat))).length;
  }
  function catCount(cat) {
    return PLACES.filter((p) => (state.city === '全部' || p.city === state.city) && matchQ(p) && (cat === '全部' || (p.tags || [p.category]).includes(cat))).length;
  }

  /* ------------------------------------------------------------
     panel rendering
     ------------------------------------------------------------ */
  const $ = (s) => document.querySelector(s);
  const listEl = $('#list');
  const citiesEl = $('#cities');
  const catsEl = $('#cats');
  const countEl = $('#count');
  const scopeEl = $('#scope');
  const mCount = $('#mCount');
  const qEl = $('#q');
  const searchWrap = $('#searchWrap');

  function renderCities() {
    const order = ['全部', ...new Set([...CITY_ORDER.filter(c => PLACES.some(p => p.city === c)), ...PLACES.map(p => p.city)])];
    citiesEl.innerHTML = order.map((c) => {
      const n = cityCount(c);
      const dead = n === 0 && state.city !== c;
      return `<button class="city${state.city === c ? ' is-on' : ''}" data-city="${esc(c)}" aria-pressed="${state.city === c}"${dead ? ' disabled' : ''}>${esc(c)}</button>`;
    }).join('');
  }

  function renderCats() {
    const total = catCount('全部');
    catsEl.innerHTML = [
      `<button class="cat${state.cat === '全部' ? ' is-on' : ''}" data-cat="全部" style="--c:#17150F"><span class="g">全</span><span class="n">全部</span><span class="c">${total}</span></button>`,
      ...CATS.map((c) => { const n = catCount(c.name); const dead = n === 0 && state.cat !== c.name;
        return `<button class="cat${state.cat === c.name ? ' is-on' : ''}" data-cat="${c.name}" style="--c:${c.color}"${dead ? ' disabled' : ''}><span class="g">${c.glyph}</span><span class="n">${c.name}</span><span class="c">${n}</span></button>`; })
    ].join('');
  }

  function hl(text, q) {
    const t = esc(text);
    if (!q) return t;
    const needle = esc(q);
    const i = t.toLowerCase().indexOf(needle.toLowerCase());
    if (i < 0) return t;
    return t.slice(0, i) + '<mark>' + t.slice(i, i + needle.length) + '</mark>' + t.slice(i + needle.length);
  }

  function renderList() {
    const list = current;
    countEl.textContent = searchActive() || state.cat !== '全部' ? `${list.length} 项结果` : '';
    mCount.textContent = list.length;
    if (isMobile() && !document.body.classList.contains('sheet-open')) { listEl.innerHTML = ''; return; }

    if (!list.length) {
      listEl.innerHTML = `<div class="empty-list">
        <div class="big">No entries.</div>
        <p>没有找到符合条件的地方。</p>
        <button data-act="clear">清除筛选</button>
      </div>`;
      scopeEl.textContent = 'The index';
      return;
    }

    const cityEn = state.city === '全部' ? 'all cities' : (CITY_EN[state.city] || state.city);
    scopeEl.textContent = searchActive() ? `Search · ${cityEn}` : (state.city === '全部' ? 'The index · all cities' : `The index · ${cityEn}`);

    const groupBy = state.city === '全部' ? 'city' : 'district';
    const groups = new Map();
    for (const p of isMobile() ? list.slice(0,mobileShown) : list) {
      const k = groupBy === 'city' ? p.city : (p.district || '其他');
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(p);
    }
    let keys = [...groups.keys()];
    if (groupBy === 'city') keys.sort((a, b) => cityRank(a) - cityRank(b));
    else keys.sort((a, b) => groups.get(b).length - groups.get(a).length || a.localeCompare(b, 'zh'));

    let html = '';
    for (const k of keys) {
      const rows = groups.get(k);
      const en = groupBy === 'city' ? (CITY_EN[k] || '') : '';
      html += `<div class="group"><span><span class="cn">${esc(k)}</span>${en ? `<span class="en">${en}</span>` : ''}</span><span class="n">${rows.length}</span></div>`;
      for (const p of rows) {
        const c = CAT[p.category] || { glyph: '·', color: '#17150F' };
        html += `<button class="row${state.id === p.id ? ' is-on' : ''}" data-id="${esc(p.id)}" style="--c:${c.color}">
          <span class="no">${pad(p.no)}</span>
          <span>
            <span class="name">${hl(p.name, state.q)}</span>
            <span class="meta"><span class="dotcat"></span><span class="district">${esc(p.district || p.city)}</span><span>·</span><span>${esc(p.category)}</span>${reviewFor(p.id) && reviewFor(p.id).rating ? `<span class="rate-mini">★ ${reviewFor(p.id).rating}</span>` : ''}</span>
          </span>
          <span class="g">${c.glyph}</span>
        </button>`;
      }
    }
    listEl.innerHTML = html;
  }

  function syncUI() {
    mobileShown = 60;
    compute();
    renderCities();
    renderCats();
    renderList();
    renderMarkers();
    if (!reducedMotion()) listEl.querySelectorAll('.row').forEach((row,index) => {
      if (index < 7) row.animate([{opacity:.35,transform:'translateY(4px)'},{opacity:1,transform:'none'}],{duration:280,delay:index*16,easing:'cubic-bezier(.16,1,.3,1)'});
    });
    $('#stageEmpty').classList.toggle('show', current.length === 0);
    $('#resetCity').hidden = state.city === '全部' || searchActive();
    $('#resetCat').hidden = state.cat === '全部';
    if (state.id && !current.some((p) => p.id === state.id)) closePlate();
  }

  /* ------------------------------------------------------------
     map
     ------------------------------------------------------------ */
  const C = {
    land: '#E3D9C5', water: '#C0D2CE', park: '#D5DDBF', res: '#DFD5C0',
    build: '#DBD0B9', road: '#FDFAF1', case: '#CBBEA6', rail: '#CEC2AA',
    text: '#6C6455', halo: '#ECE5D6', line: '#C9BFAB'
  };

  function tintedStyle() {
    const style = JSON.parse(JSON.stringify(window.POSITRON_STYLE));
    const set = (layer, key, val) => {
      const l = style.layers.find((x) => x.id === layer);
      if (!l) return;
      l.paint = l.paint || {};
      l.paint[key] = val;
    };
    const layout = (layer, key, val) => {
      const l = style.layers.find((x) => x.id === layer);
      if (!l) return;
      l.layout = l.layout || {};
      l.layout[key] = val;
    };

    set('background', 'background-color', C.land);
    set('park', 'fill-color', C.park);
    set('water', 'fill-color', C.water);
    set('waterway', 'line-color', C.water);
    set('landuse_residential', 'fill-color', C.res);
    set('landcover_wood', 'fill-color', C.park);
    set('landcover_grass', 'fill-color', C.park);
    set('building', 'fill-color', C.build);
    set('building', 'fill-outline-color', 'rgba(23,21,15,0.06)');
    set('highway_path', 'line-color', '#EDE6D6');
    set('highway_minor', 'line-color', C.road);
    set('highway_major_casing', 'line-color', C.case);
    set('highway_major_inner', 'line-color', C.road);
    set('highway_major_subtle', 'line-color', C.case);
    set('highway_motorway_casing', 'line-color', C.case);
    set('highway_motorway_inner', 'line-color', C.road);
    set('highway_motorway_subtle', 'line-color', C.case);
    set('tunnel_motorway_casing', 'line-color', C.case);
    set('tunnel_motorway_inner', 'line-color', C.road);
    set('railway', 'line-color', C.rail);
    set('railway_dashline', 'line-color', C.land);
    set('railway_transit', 'line-color', C.rail);
    set('railway_transit_dashline', 'line-color', C.land);
    set('railway_service', 'line-color', C.rail);
    set('railway_service_dashline', 'line-color', C.land);
    set('boundary_3', 'line-color', C.line);
    set('boundary_2', 'line-color', C.line);
    set('aeroway-taxiway', 'line-color', C.case);
    set('road_area_pier', 'fill-color', C.land);
    set('road_pier', 'line-color', C.land);

    const labelLayers = ['water_name_point_label', 'water_name_line_label', 'waterway_line_label', 'highway-name-path', 'highway-name-minor', 'highway-name-major', 'airport', 'label_other', 'label_village', 'label_town', 'label_state', 'label_city', 'label_city_capital', 'label_country_1', 'label_country_2', 'label_country_3'];
    labelLayers.forEach((id) => {
      set(id, 'text-color', id.startsWith('water') || id === 'waterway_line_label' ? '#6E8280' : C.text);
      set(id, 'text-halo-color', C.halo);
      set(id, 'text-halo-width', 1.1);
      set(id, 'text-halo-blur', 0.2);
    });

    // Chinese place names only, quieter sizes
    ['label_other', 'label_village', 'label_town', 'label_state', 'label_city', 'label_city_capital', 'highway-name-path', 'highway-name-minor', 'highway-name-major', 'water_name_point_label', 'water_name_line_label', 'waterway_line_label'].forEach((id) => {
      layout(id, 'text-field', ['coalesce', ['get', 'name:nonlatin'], ['get', 'name']]);
    });
    layout('label_city', 'text-size', ['interpolate', ['linear'], ['zoom'], 4, 11, 7, 12, 11, 16, 14, 18]);
    layout('label_city_capital', 'text-size', ['interpolate', ['linear'], ['zoom'], 4, 11, 7, 12, 11, 16, 14, 18]);
    layout('label_town', 'text-size', ['interpolate', ['linear'], ['zoom'], 6, 10, 10, 12, 14, 14]);
    layout('label_village', 'text-size', ['interpolate', ['linear'], ['zoom'], 9, 9.5, 14, 12]);
    layout('label_other', 'text-size', ['interpolate', ['linear'], ['zoom'], 8, 9.5, 14, 11.5]);
    layout('highway-name-minor', 'text-size', ['interpolate', ['linear'], ['zoom'], 13, 9, 18, 11]);
    layout('highway-name-major', 'text-size', ['interpolate', ['linear'], ['zoom'], 12, 9, 18, 11.5]);

    const quiet = { label_village: 12.2, label_other: 12.6, label_town: 11.2, 'highway-name-minor': 14, 'highway-name-major': 13, 'highway-name-path': 15 };
    Object.entries(quiet).forEach(([id, z]) => {
      const l = style.layers.find((x) => x.id === id);
      if (l) l.minzoom = Math.max(l.minzoom || 0, z);
    });

    // drop POI dots & shields that make the map busy
    style.layers = style.layers.filter((l) => !/^highway-shield|^road_shield|^poi/.test(l.id));
    return style;
  }

  let map, mapReady = false, placePulse = null, hoverPopup = null, tileErrors = 0;

  function initMap() {
    if (!window.maplibregl) {
      $('#loading').classList.add('done');
      showToast('地图脚本未能载入 · 索引仍可使用');
      return;
    }
    try {
      map = new maplibregl.Map({
      container: 'map',
      style: tintedStyle(),
      center: [116.4074, 39.9042],
      zoom: 11,
      minZoom: 3,
      maxZoom: 18,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      fadeDuration: 180
    });
    } catch (err) {
      $('#loading').classList.add('done');
      showToast('这台设备无法渲染地图 · 索引仍可使用');
      return;
    }
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: '<a href="https://github.com/Immutable1407/review-map/blob/main/ATTRIBUTION.md" target="_blank" rel="noopener">Style credits</a>' }), 'bottom-right');

    // never let the curtain stay up: tiles stream in behind it
    const curtain = () => $('#loading').classList.add('done');
    setTimeout(curtain, 4200);
    map.once('idle', curtain);

    map.on('load', () => {
      mapReady = true;
      addLayers();
      const selected = byId.get(state.id);
      if (selected) map.jumpTo({center:[selected.lng,selected.lat],zoom:14.1,padding:selectedPadding()});
      else map.jumpTo({ center: [116.407, 39.917], zoom: 11.35, padding:overviewPadding() });
      if (selected) highlightPlace(selected);
      setTimeout(() => $('#loading').classList.add('done'), 260);
      renderMarkers();
    });

    map.on('error', (e) => {
      if (!mapReady) return;
      const msg = (e && e.error && e.error.message) || '';
      if (/tile|fetch|network|Failed to fetch|403|404/i.test(msg)) {
        tileErrors += 1;
        if (tileErrors === 4) {
          $('#nethint').classList.add('show');
          setTimeout(() => $('#nethint').classList.remove('show'), 4200);
        }
      }
    });

    map.on('mousemove', (e) => {
      const { lng, lat } = e.lngLat;
      const el = $('#coords');
      if (el) el.textContent = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N' : 'S'} · ${Math.abs(lng).toFixed(4)}° ${lng >= 0 ? 'E' : 'W'}`;
    });

    map.on('click', (e) => {
      const hit = map.queryRenderedFeatures(e.point, { layers: ['places-pin', 'places-dot'] });
      if (hit.length) { select(hit[0].properties.id, { fly: true }); return; }
      closePlate();
    });

    map.on('click', 'clusters', (e) => {
      const f = e.features[0];
      map.getSource('places').getClusterExpansionZoom(f.properties.cluster_id).then((z) => {
        map.easeTo({ center: f.geometry.coordinates, zoom: z + 0.2, duration: motion(700) });
      });
    });

    map.on('mouseenter', 'places-pin', (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const p = byId.get(e.features[0].properties.id);
      if (!p) return;
      hoverPopup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'atlas-popup', maxWidth: '280px' })
        .setLngLat([p.lng, p.lat])
        .setHTML(`<b>${esc(p.name)}</b><span>${esc(p.category)}</span>`)
        .addTo(map);
    });
    map.on('mouseleave', 'places-pin', () => {
      map.getCanvas().style.cursor = '';
      if (hoverPopup) { hoverPopup.remove(); hoverPopup = null; }
    });
    map.on('mouseenter', 'clusters', () => { map.getCanvas().style.cursor = 'zoom-in'; });
    map.on('mouseleave', 'clusters', () => { map.getCanvas().style.cursor = ''; });
  }

  function addLayers() {
    map.addSource('places', {
      type: 'geojson',
      data: featureCollection(),
      cluster: true,
      clusterRadius: 62,
      clusterMaxZoom: 15
    });

    map.addLayer({
      id: 'clusters',
      type: 'circle',
      source: 'places',
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': '#FBF7EC',
        'circle-radius': ['step', ['get', 'point_count'], 15, 10, 18, 40, 21, 100, 25],
        'circle-stroke-width': 1.4,
        'circle-stroke-color': '#17150F',
        'circle-opacity': 1
      }
    });
    map.addLayer({
      id: 'cluster-count',
      type: 'symbol',
      source: 'places',
      filter: ['has', 'point_count'],
      layout: {
        'text-field': ['get', 'point_count_abbreviated'],
        'text-font': ['Noto Sans Bold'],
        'text-size': 10,
        'text-allow-overlap': true
      },
      paint: { 'text-color': '#17150F' }
    });

    /* small dots while the city is far away */
    map.addLayer({
      id: 'places-dot',
      type: 'circle',
      source: 'places',
      maxzoom: 12.4,
      filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-color': ['match', ['get', 'category'], ...CATS.flatMap((c) => [c.name, c.color]), '#17150F'],
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 3.4, 12.4, 5.6],
        'circle-stroke-width': 1.2,
        'circle-stroke-color': '#FBF7EC',
        'circle-opacity': 0.95
      }
    });

    /* proper rounded pins once streets are legible */
    map.addLayer({
      id: 'places-pin',
      type: 'circle',
      source: 'places',
      minzoom: 12.4,
      filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-color': ['match', ['get', 'category'], ...CATS.flatMap((c) => [c.name, c.color]), '#17150F'],
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 12.4, 8.5, 15, 10.5, 18, 12.5],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#FBF7EC',
        'circle-opacity': 1
      }
    });
    map.addLayer({
      id: 'places-glyph',
      type: 'symbol',
      source: 'places',
      minzoom: 12.4,
      filter: ['!', ['has', 'point_count']],
      layout: {
        'text-field': ['get', 'glyph'],
        'text-font': ['Noto Sans Bold'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 12.4, 8.5, 16, 10],
        'text-allow-overlap': false,
        'text-ignore-placement': false
      },
      paint: { 'text-color': '#FBF7EC' }
    });
  }

  function featureCollection() {
    return {
      type: 'FeatureCollection',
      features: current.map((p) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
        properties: { id: p.id, name: p.name, category: p.category, glyph: (CAT[p.category] || {}).glyph || '·' }
      }))
    };
  }

  function renderMarkers() {
    if (!mapReady || !map.getSource('places')) return;
    map.getSource('places').setData(featureCollection());
  }

  function fitTo(places, opts = {}) {
    if (!mapReady || !places.length) return;
    if (places.length === 1) {
      map.easeTo({ center: [places[0].lng, places[0].lat], zoom: 14.2, duration: motion(800) });
      return;
    }
    const b = new maplibregl.LngLatBounds();
    places.forEach((p) => b.extend([p.lng, p.lat]));
    const pad = overviewPadding();
    map.fitBounds(b, { padding: pad, maxZoom: opts.maxZoom || 12.6, duration: motion(900), essential: false });
  }

  function fitCity(city, instant) {
    const set = city === '全部' ? PLACES : PLACES.filter((p) => p.city === city);
    if (!mapReady || !set.length) return;
    if (city === '全部') {
      const b = new maplibregl.LngLatBounds();
      set.forEach((p) => b.extend([p.lng, p.lat]));
      map.fitBounds(b, { padding: overviewPadding(), maxZoom: 5.2, duration: instant ? 0 : motion(900) });
      return;
    }
    if (instant) {
      const b = new maplibregl.LngLatBounds();
      set.forEach((p) => b.extend([p.lng, p.lat]));
      map.fitBounds(b, { padding: overviewPadding(), maxZoom: 12, duration: 0 });
    } else {
      fitTo(set);
    }
  }

  /* ------------------------------------------------------------
     plate
     ------------------------------------------------------------ */
  const plate = $('#plate');

  function distanceKm(a, b) {
    const R = 6371, rad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * rad;
    const dLng = (b.lng - a.lng) * rad;
    const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }

  function nearby(p) {
    return PLACES
      .map((o) => ({ p: o, d: distanceKm(p, o) }))
      .filter((o) => o.p.id !== p.id && o.d < 1.8)
      .sort((a, b) => a.d - b.d)
      .slice(0, 4);
  }

  function renderPlate(p) {
    const c = CAT[p.category] || { color: '#17150F', en: 'Place' };
    const aliases = [...new Set(p.savedNames || [p.savedName].filter(Boolean))].filter(name => name && name !== p.name);
    const around = nearby(p), rev = reviewFor(p.id);
    const hasNotes = aliases.length || p.food?.length || p.note;
    plate.innerHTML = `
      <div class="plate-scroll thin-scroll">
        <div class="plate-top">
          <span class="compact-category" style="--c:${c.color}"><i></i>${esc(p.city)} · ${esc((p.tags || [p.category]).join(' · '))}</span>
          <button class="plate-close" data-act="close" aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 5l14 14M19 5 5 19" /></svg>
          </button>
        </div>
        <h2 tabindex="-1">${esc(p.name)}</h2>
        <p class="compact-address">${esc(p.district || '')}${p.district && p.address ? ' · ' : ''}${esc(p.address || '地址暂缺')}</p>

        <div class="detail-options" aria-label="更多地点信息">
          <button type="button" id="toggle-review" data-pane="review" aria-controls="pane-review" aria-expanded="${detail.section === 'review'}" class="${detail.section === 'review' ? 'is-on' : ''}">评价 <span data-review-summary>${rev?.rating ? '★ ' + rev.rating : ''}</span></button>
          ${hasNotes ? `<button type="button" id="toggle-notes" data-pane="notes" aria-controls="pane-notes" aria-expanded="${detail.section === 'notes'}" class="${detail.section === 'notes' ? 'is-on' : ''}">收藏笔记</button>` : ''}
          ${around.length ? `<button type="button" id="toggle-nearby" data-pane="nearby" aria-controls="pane-nearby" aria-expanded="${detail.section === 'nearby'}" class="${detail.section === 'nearby' ? 'is-on' : ''}">附近收藏</button>` : ''}
        </div>

        <section class="plate-extra" id="pane-review" data-content="review" aria-labelledby="toggle-review" ${detail.section !== 'review' ? 'hidden' : ''}>${reviewSection(p)}</section>
        ${hasNotes ? `<section class="plate-extra" id="pane-notes" data-content="notes" aria-labelledby="toggle-notes" ${detail.section !== 'notes' ? 'hidden' : ''}>
          <dl class="facts">
            ${p.food?.length ? `<div class="fact"><dt>推荐</dt><dd><div class="foods">${p.food.map(food => `<span>${esc(food)}</span>`).join('')}</div></dd></div>` : ''}
            ${p.note ? `<div class="fact"><dt>备注</dt><dd class="note">${esc(p.note)}</dd></div>` : ''}
            ${aliases.length ? `<div class="fact"><dt>别名</dt><dd>${esc(aliases.join('、'))}</dd></div>` : ''}
          </dl>
        </section>` : ''}
        ${around.length ? `<section class="plate-extra" id="pane-nearby" data-content="nearby" aria-labelledby="toggle-nearby" ${detail.section !== 'nearby' ? 'hidden' : ''}>
          <div class="nearby">
            <div class="nearby-head"><span>附近也收藏过</span><span>直线距离</span></div>
            <ul>${around.map(o => `<li><button data-goto="${esc(o.p.id)}" style="--c:${(CAT[o.p.category] || {}).color || '#17150F'}"><span class="d"></span><span class="nm">${esc(o.p.name)}</span><span class="ds">${o.d < 1 ? Math.round(o.d*1000)+' m' : o.d.toFixed(1)+' km'}</span></button></li>`).join('')}</ul>
          </div>
        </section>` : ''}

        <div class="plate-actions">
          <a class="btn primary" href="https://uri.amap.com/marker?position=${p.location[0]},${p.location[1]}&name=${encodeURIComponent(p.name)}&coordinate=gaode&callnative=0&src=review-map" target="_blank" rel="noopener">
            在高德地图打开
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 18 18 6M9 6h9v9" stroke-linecap="round" stroke-linejoin="round" /></svg>
          </a>
          <div class="sub-actions"><button data-act="copylink">复制链接</button><button data-act="copyname">复制店名</button><button data-act="clear-filter">只看${esc(p.category)}</button></div>
        </div>
      </div>
      <div class="plate-nav">
        <button data-act="prev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" /></svg> 上一处</button>
        <span class="at">${pad(p.no)}</span>
        <button data-act="next">下一处 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M10 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
      </div>`;
  }

  let detailResizeAnimation;
  function toggleDetailSection(key) {
    const previousHeight = plate.getBoundingClientRect().height;
    detailResizeAnimation?.cancel();
    keepDraft();
    detail.section = detail.section === key ? null : key;
    plate.querySelectorAll('[data-pane]').forEach(button => {
      const open = button.dataset.pane === detail.section;
      button.classList.toggle('is-on',open); button.setAttribute('aria-expanded',String(open));
    });
    plate.querySelectorAll('[data-content]').forEach(section => {
      const open = section.dataset.content === detail.section;
      section.hidden = !open;
      if (open && !reducedMotion()) section.animate([{opacity:0,transform:'translateY(-4px)'},{opacity:1,transform:'none'}],{duration:240,easing:'cubic-bezier(.16,1,.3,1)'});
    });
    const nextHeight = plate.getBoundingClientRect().height;
    if (!reducedMotion()) detailResizeAnimation = plate.animate([{height:previousHeight+'px'},{height:nextHeight+'px'}],{duration:320,easing:'cubic-bezier(.16,1,.3,1)'});
  }

  function select(id, opts = {}) {
    const p = byId.get(id);
    if (!p) return;
    detailResizeAnimation?.cancel();
    keepDraft();
    state.id = id;
    detail.epoch++;
    detail.editing = false;
    detail.section = null;
    detail.rating = loadDraft(id)?.rating ?? reviewFor(id)?.rating ?? 0;
    renderPlate(p);
    lockEditor(pending.has(id));
    plate.inert = false; plate.setAttribute('aria-hidden','false');
    plate.classList.add('is-open');
    document.body.classList.add('plate-open');
    document.body.classList.remove('sheet-open');
    markRow();
    const scroll = plate.querySelector('.plate-scroll');
    if (!reducedMotion()) scroll.animate([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'none'}],{duration:320,easing:'cubic-bezier(.16,1,.3,1)'});

    if (opts.fly !== false) {
      const pad = selectedPadding();
      if (mapReady) {
      const z = Math.max(map.getZoom(), 14.1);
      map.easeTo({ center: [p.lng, p.lat], zoom: z, padding: pad, duration: motion(900), essential: false });
      }
    }
    if (mapReady) highlightPlace(p);
    try { history.replaceState(null, '', `#p=${encodeURIComponent(id)}`); } catch (e) { /* file:// */ }
  }

  function highlightPlace(p) {
    if (!placePulse) {
      const el = document.createElement('div'); el.className = 'pin-pulse';
      el.style.setProperty('--pc', (CAT[p.category] || {}).color || '#C8452C');
      placePulse = new maplibregl.Marker({element:el,anchor:'center'}).setLngLat([p.lng,p.lat]).addTo(map);
    } else {
      placePulse.setLngLat([p.lng,p.lat]);
      placePulse.getElement().style.setProperty('--pc',(CAT[p.category] || {}).color || '#C8452C');
    }
  }

  function closePlate() {
    detailResizeAnimation?.cancel();
    keepDraft(); detail.epoch++;
    if (plate.contains(document.activeElement)) document.activeElement.blur();
    plate.inert = true; plate.setAttribute('aria-hidden','true');
    plate.classList.remove('is-open');
    document.body.classList.remove('plate-open');
    state.id = null;
    markRow();
    if (placePulse) { placePulse.remove(); placePulse = null; }
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) {}
  }

  function markRow() {
    listEl.querySelectorAll('.row').forEach((r) => r.classList.toggle('is-on', r.dataset.id === state.id));
    const on = listEl.querySelector('.row.is-on');
    if (on) {
      const top = on.offsetTop - listEl.offsetTop;
      const view = listEl.scrollTop;
      const h = listEl.clientHeight;
      if (top < view + 60 || top > view + h - 80) listEl.scrollTop = top - 60;
    }
  }

  function step(dir) {
    if (!current.length) return;
    let i = current.findIndex((p) => p.id === state.id);
    if (i === -1) i = 0;
    const next = current[(i + dir + current.length) % current.length];
    select(next.id, { fly: true });
  }

  plate.addEventListener('click', (e) => {
    const pane = e.target.closest('[data-pane]');
    if (pane) { toggleDetailSection(pane.dataset.pane); return; }
    const go = e.target.closest('[data-goto]');
    if (go) { select(go.dataset.goto, { fly: true }); return; }
    const star = e.target.closest('[data-star]');
    if (star) {
      if (!owner || pending.has(state.id)) return;
      detail.rating = Number(star.dataset.star);
      plate.querySelectorAll('[data-star]').forEach((b) => {
        const on = Number(b.dataset.star) <= detail.rating;
        b.classList.toggle('on', on);
        b.setAttribute('aria-checked', String(Number(b.dataset.star) === detail.rating));
        b.tabIndex = Number(b.dataset.star) === detail.rating ? 0 : -1;
      });
      const hint = plate.querySelector('.rev-form .hint');
      if (hint) hint.textContent = detail.rating + ' / 5';
      keepDraft();
      return;
    }
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === 'clear-rating') { detail.rating = 0; keepDraft(); safeRenderReview(); return; }
    if (act === 'signin') { openAuth(); return; }
    if (act === 'edit-review') {
      if (!owner || pending.has(state.id)) return;
      keepDraft(); detail.epoch++;
      const p = byId.get(state.id);
      if (!p) return;
      detail.editing = !detail.editing;
      detail.rating = loadDraft(p.id)?.rating ?? reviewFor(p.id)?.rating ?? 0;
      renderPlate(p);
      return;
    }
    if (act === 'del-review') {
      const p = byId.get(state.id);
      if (p) removeReview(p);
      return;
    }
    if (act === 'close') closePlate();
    if (act === 'goto') { /* handled below */ }
    if (act === 'prev') step(-1);
    if (act === 'next') step(1);
    if (act === 'copyname') copy(byId.get(state.id).name, '店名已复制');
    if (act === 'copylink') {
      const url = location.href.split('#')[0] + '#p=' + encodeURIComponent(state.id);
      copy(url, '链接已复制');
    }
    if (act === 'clear-filter') {
      const p = byId.get(state.id);
      state.cat = p.category; state.city = p.city; state.q = '';
      qEl.value = ''; searchWrap.classList.remove('has-q');
      syncUI(); closePlate(); fitCity(state.city);
    }
  });

  plate.addEventListener('submit', (e) => {
    if (!e.target.matches('#revForm')) return;
    e.preventDefault();
    const p = byId.get(state.id);
    if (p) commitReview(p);
  });
  plate.addEventListener('input', e => { if (e.target.matches('#revText')) keepDraft(); });
  plate.addEventListener('keydown', e => {
    const radio = e.target.closest('[data-star]');
    if (!radio || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(e.key)) return;
    e.preventDefault(); e.stopPropagation();
    const current = Number(radio.dataset.star);
    const value = e.key === 'Home' ? 1 : e.key === 'End' ? 5 : ((current - 1 + (['ArrowLeft','ArrowDown'].includes(e.key) ? -1 : 1) + 5) % 5) + 1;
    const next = plate.querySelector(`[data-star="${value}"]`); next.click(); next.focus();
  });
  listEl.addEventListener('scroll', () => {
    if (!isMobile() || mobileShown >= current.length || listEl.scrollTop + listEl.clientHeight < listEl.scrollHeight - 120) return;
    mobileShown += 60; renderList();
  },{passive:true});

  function copy(text, msg) {
    const done = () => showToast(msg);
    if (navigator.clipboard && location.protocol !== 'file:') {
      navigator.clipboard.writeText(text).then(done).catch(() => fallback());
    } else fallback();
    function fallback() {
      const t = document.createElement('textarea');
      t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
      document.body.appendChild(t); t.select();
      try { document.execCommand('copy'); done(); } catch (e) { showToast('复制失败'); }
      t.remove();
    }
  }

  let toastTimer;
  function showToast(msg) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
  }

  /* ------------------------------------------------------------
     events
     ------------------------------------------------------------ */
  citiesEl.addEventListener('click', (e) => {
    const b = e.target.closest('[data-city]');
    if (!b) return;
    state.city = b.dataset.city;
    state.q = ''; qEl.value = ''; searchWrap.classList.remove('has-q');
    closePlate();
    syncUI();
    fitCity(state.city);
    if (isMobile()) document.body.classList.remove('sheet-open');
  });

  catsEl.addEventListener('click', (e) => {
    const b = e.target.closest('[data-cat]');
    if (!b) return;
    state.cat = state.cat === b.dataset.cat ? '全部' : b.dataset.cat;
    syncUI();
    if (current.length) fitTo(current);
  });

  listEl.addEventListener('click', (e) => {
    const row = e.target.closest('[data-id]');
    if (row) { select(row.dataset.id, { fly: true }); return; }
    if (e.target.closest('[data-act="clear"]')) clearAll();
  });

  let searchTimer;
  $('#q').addEventListener('input', (e) => {
    state.q = e.target.value;
    searchWrap.classList.toggle('has-q', state.q.length > 0);
    clearTimeout(searchTimer); searchTimer = setTimeout(syncUI,120);
  });
  $('#clearQ').addEventListener('click', () => {
    state.q = ''; qEl.value = ''; searchWrap.classList.remove('has-q'); syncUI(); qEl.focus();
  });
  $('#resetCity').addEventListener('click', () => {
    state.city = '全部'; closePlate(); syncUI(); fitCity('全部');
  });
  $('#resetCat').addEventListener('click', () => { state.cat = '全部'; syncUI(); fitCity(state.city); });
  $('#clearAll').addEventListener('click', clearAll);
  function clearAll() {
    state.city = '全部'; state.cat = '全部'; state.q = '';
    qEl.value = ''; searchWrap.classList.remove('has-q');
    closePlate(); syncUI(); fitCity('全部');
  }

  $('#random').addEventListener('click', () => {
    const pool = current.length ? current : PLACES;
    let p = pool[Math.floor(Math.random() * pool.length)];
    if (pool.length > 1 && p.id === state.id) p = pool[(pool.indexOf(p) + 1) % pool.length];
    select(p.id, { fly: true });
    showToast(`今天去 · ${p.name.slice(0, 18)}`);
  });

  $('#zin').addEventListener('click', () => map && map.zoomIn());
  $('#zout').addEventListener('click', () => map && map.zoomOut());
  $('#zfit').addEventListener('click', () => { closePlate(); fitCity(state.city); });

  $('#mList').addEventListener('click', () => {
    closePlate(); document.body.classList.toggle('sheet-open'); renderList();
  });
  $('#mSearch').addEventListener('click', () => {
    document.body.classList.add('sheet-open');
    closePlate(); renderList();
    setTimeout(() => qEl.focus(), 380);
  });
  document.querySelector('.panel').addEventListener('click', (e) => {
    if (e.target.closest('.sheet-grab')) document.body.classList.remove('sheet-open');
  });

  document.addEventListener('keydown', (e) => {
    if ($('#authDialog').open) return;
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); qEl.focus(); if (isMobile()) document.body.classList.add('sheet-open'); }
    if (e.key === 'Escape') {
      if (document.activeElement === qEl) { qEl.blur(); return; }
      if (plate.classList.contains('is-open')) closePlate();
      else document.body.classList.remove('sheet-open');
    }
    if (typing) return;
    if (e.key === 'r' || e.key === 'R') $('#random').click();
    if (e.target.closest('.rate')) return;
    if (e.key === 'j' || e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    if (e.key === 'k' || e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  });

  window.addEventListener('hashchange', () => {
    if (location.hash.startsWith('#p=')) {
      let id; try { id = decodeURIComponent(location.hash.slice(3)); } catch { return; }
      if (byId.has(id) && id !== state.id) select(id, { fly: true });
    }
  });

  window.addEventListener('resize', () => {
    renderList();
    if (!isMobile()) document.body.classList.remove('sheet-open');
    if (!mapReady || !state.id) return;
    const p = byId.get(state.id);
    if (!p) return;
    map.easeTo({ padding: selectedPadding(), duration: 0 });
  });

  /* ------------------------------------------------------------
     owner
     ------------------------------------------------------------ */
  $('#account').addEventListener('click', openAuth);
  $('#mAccount').addEventListener('click', openAuth);
  $('#authClose').addEventListener('click', closeAuth);
  $('#authDone').addEventListener('click', closeAuth);
  $('#authOut').addEventListener('click', signOut);
  $('#authForm').addEventListener('submit', (e) => {
    e.preventDefault();
    signIn($('#authPass').value);
  });
  $('#authDialog').addEventListener('click', (e) => {
    if (e.target === $('#authDialog')) closeAuth();
  });
  $('#authDialog').addEventListener('close', () => { $('#authPass').value = ''; });
  let userLocation;
  $('#locate').addEventListener('click', () => {
    if (!mapReady || !navigator.geolocation) { showToast('暂时无法定位，仍可按城市浏览。'); return; }
    const button = $('#locate'); button.disabled = true;
    navigator.geolocation.getCurrentPosition(({coords}) => {
      button.disabled = false;
      if (!userLocation) {
        const el = document.createElement('div'); el.className = 'user-location'; el.title = '我的位置';
        userLocation = new maplibregl.Marker({element:el}).setLngLat([coords.longitude,coords.latitude]).addTo(map);
      } else userLocation.setLngLat([coords.longitude,coords.latitude]);
      closePlate(); map.easeTo({center:[coords.longitude,coords.latitude],zoom:14,duration:motion(700),padding:overviewPadding()});
    },() => { button.disabled = false; showToast('未取得定位，可继续按城市浏览。'); },{enableHighAccuracy:true,timeout:10000});
  });

  /* ------------------------------------------------------------
     go
     ------------------------------------------------------------ */
  accountUI();
  refreshReviews();
  window.addEventListener('pagehide', keepDraft);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !pending.size) refreshReviews(); });
  setInterval(() => { if (!document.hidden && !pending.size && !$('#authDialog').open) refreshReviews(); },30000);
  compute();
  renderCities();
  renderCats();
  renderList();
  initMap();
  if (location.hash.startsWith('#p=')) {
    try { const id = decodeURIComponent(location.hash.slice(3)); if (byId.has(id)) select(id,{fly:false}); } catch {}
  }
})();
