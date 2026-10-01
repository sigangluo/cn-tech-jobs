/* 社招职位看板：纯静态，数据来自 data/jobs.json（scripts/build.py 生成）。
   职位名、部门、职位描述都来自第三方招聘站点，一律当数据处理：只用 textContent / 文本节点渲染，不拼 innerHTML。 */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const SVG_TAGS = new Set(['svg', 'g', 'rect', 'path', 'line', 'text', 'circle', 'polyline', 'title']);
  const NS = 'http://www.w3.org/2000/svg';
  const PAGE = 50;
  const fmt = n => n.toLocaleString('en-US');

  function h(tag, attrs, ...kids) {
    const e = SVG_TAGS.has(tag) ? document.createElementNS(NS, tag) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid);
    return e;
  }

  let D;                                   // jobs.json
  let CO = {};                             // company key -> {name, list_url, note, idx}
  const S = { range: 'all', cos: new Set(), cats: new Set(), city: '', yb: '', q: '', sort: 'date', page: 0, view: 'chart', fac: {}, facCo: null };
  const jdCache = {};

  // ---------- 提示框 ----------
  const tip = $('#tip');
  function showTip(x, y, head, rows) {
    tip.replaceChildren(
      h('div', { class: 'th' }, head),
      ...rows.map(r => h('div', { class: 'tr' },
        h('span', { class: 'tk', style: `background:var(${r.color})` }),
        h('span', { class: 'tv' }, r.value),
        h('span', { class: 'tn' }, r.name))));
    tip.hidden = false;
    const b = tip.getBoundingClientRect();
    let nx = x + 14, ny = y + 14;
    if (nx + b.width > innerWidth - 8) nx = x - b.width - 14;
    if (ny + b.height > innerHeight - 8) ny = y - b.height - 14;
    tip.style.left = Math.max(8, nx) + 'px';
    tip.style.top = Math.max(8, ny) + 'px';
  }
  const hideTip = () => { tip.hidden = true; };

  // ---------- 筛选 ----------
  function cutoff(days) {
    const d = new Date(D.generated + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - days);
    return d.toISOString().slice(0, 10);
  }

  function passes(j) {
    if (S.cos.size && !S.cos.has(j.c)) return false;
    for (const [i, v] of Object.entries(S.fac)) {
      const fv = (j.f || [])[i];
      if (v && !(Array.isArray(fv) ? fv.includes(v) : fv === v)) return false;
    }   // 公司专属维度（只在选中一家公司时才会有值）
    if (S.cats.size && !S.cats.has(j.cat)) return false;
    if (S.city && !j.ci.includes(S.city)) return false;
    if (S.yb !== '' && j.yb !== +S.yb) return false;
    if (S.range !== 'all' && j.dt < cutoff(+S.range)) return false;
    if (S.q) {
      const q = S.q.toLowerCase();
      if (!j.t.toLowerCase().includes(q) && !j.dp.toLowerCase().includes(q)) return false;
    }
    return true;
  }
  const isDefault = () => S.range === 'all' && !S.cos.size && !S.cats.size && !S.city && S.yb === '' && !S.q && Object.values(S.fac).every(v => !v);

  // ---------- 概览 ----------
  function tile(label, value, sub, cls) {
    return h('div', { class: 'tile ' + (cls || '') },
      h('div', { class: 'l' }, label), h('div', { class: 'v' }, value), sub ? h('div', { class: 's' }, sub) : null);
  }
  function renderKpis(F) {
    const n = F.length, pct = x => (n ? Math.round(x / n * 100) : 0) + '%';
    const byCat = c => F.filter(j => j.cat === c).length;
    const senior = F.filter(j => j.ym != null && j.ym >= 5).length;
    const c7 = cutoff(7);
    const recent = F.filter(j => j.dt >= c7).length;
    $('#kpis').replaceChildren(
      tile('符合条件的职位', fmt(n), isDefault() ? '当前收录的全部职位' : `全部共 ${fmt(D.jobs.length)} 个`, 'hero'),
      ...D.categories.map(c => tile(c + '岗', fmt(byCat(c)), n ? '占 ' + pct(byCat(c)) : '')),
      tile('要求 5 年以上', fmt(senior), n ? '占 ' + pct(senior) : ''),
      tile('近 7 天发布 / 更新', fmt(recent), `${c7} 之后`));
  }

  // ---------- 图表工具 ----------
  function niceScale(m) {
    if (m <= 0) return { max: 1, step: 1 };
    const rough = m / 4, p = 10 ** Math.floor(Math.log10(rough));
    const step = [1, 2, 2.5, 5, 10].find(f => f * p >= rough) * p;
    return { max: step * Math.ceil(m / step), step };
  }
  function barPath(x, y, w, hh, r) {       // 只圆右端（数据端），基线端保持直角
    r = Math.min(r, w, hh / 2);
    if (r <= 0) return `M${x},${y}h${w}v${hh}h${-w}Z`;
    return `M${x},${y}H${x + w - r}A${r},${r} 0 0 1 ${x + w},${y + r}V${y + hh - r}A${r},${r} 0 0 1 ${x + w - r},${y + hh}H${x}Z`;
  }
  const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

  /* 横向堆叠条形图。rows: [{label, v:[每段数值], key}]；segs: [{name, color:'--cat-0', ink:'--cat-0-ink'}]
     pct=true 时每行拉满 100%（占比图），否则共用一个从 0 起的数值轴。 */
  function hbar({ rows, segs, pct, labelW, width, labelMax }) {
    if (!rows.length) return empty('没有数据');
    const rowH = 34, barH = 20, top = 4, axisH = 24, right = pct ? 66 : 56;
    labelW = Math.min(150, Math.max(...rows.map(r => short(r.label, labelMax || 8).length)) * 14 + 22);
    const x0 = labelW, x1 = width - right, plotW = Math.max(40, x1 - x0);
    const totals = rows.map(r => r.v.reduce((a, b) => a + b, 0));
    const sc = pct ? { max: 1, step: 0.25 } : niceScale(Math.max(...totals));
    const plotH = rows.length * rowH;
    const svg = h('svg', { class: 'chart', viewBox: `0 0 ${width} ${top + plotH + axisH}`, role: 'group', 'aria-label': '条形图' });

    for (let t = 0; t <= sc.max + 1e-9; t += sc.step) {           // 竖向细网格 + 刻度
      const x = x0 + t / sc.max * plotW;
      svg.append(h('line', { class: 'gridline', x1: x, x2: x, y1: top, y2: top + plotH }),
        h('text', { class: 't-axis', x, y: top + plotH + 17, 'text-anchor': 'middle' }, pct ? Math.round(t * 100) + '%' : fmt(Math.round(t))));
    }
    svg.append(h('line', { class: 'axisline', x1: x0, x2: x0, y1: top, y2: top + plotH }));

    rows.forEach((r, ri) => {
      const y = top + ri * rowH, by = y + (rowH - barH) / 2, total = totals[ri];
      const summary = `${r.label}：` + segs.map((s, i) => `${s.name} ${fmt(r.v[i])}`).join('，');
      const g = h('g', { class: 'row', tabindex: 0, role: 'img', 'aria-label': summary });
      g.append(h('rect', { class: 'rowbg', x: 0, y, width, height: rowH, rx: 6 }),
        h('text', { class: 't-lbl', x: x0 - 10, y: y + rowH / 2 + 4.5, 'text-anchor': 'end' }, short(r.label, labelMax || 8)));
      const lastNz = r.v.reduce((a, v, i) => (v > 0 ? i : a), -1);
      let acc = 0;
      r.v.forEach((v, i) => {
        if (!v) return;
        const w0 = pct ? v / total * plotW : v / sc.max * plotW;
        const xs = x0 + acc; acc += w0;
        const w = i === lastNz ? w0 : Math.max(0, w0 - 2);        // 相邻色块之间留 2px 表面色缝隙
        if (w < 0.5) return;
        g.append(h('path', { class: 'seg', d: barPath(xs, by, w, barH, i === lastNz ? 4 : 0), style: `fill:var(${segs[i].color})` }));
        const label = pct ? Math.round(v / total * 100) + '%' : fmt(v);
        if (w >= label.length * 6.6 + 14)                          // 放得下才写在色块里，放不下就交给提示框和数据表
          g.append(h('text', { class: 't-in', x: xs + w / 2, y: by + barH / 2 + 4, 'text-anchor': 'middle', style: `fill:var(${segs[i].ink})` }, label));
      });
      const tipX = pct ? x1 + 8 : x0 + acc + 8;
      g.append(h('text', { class: 't-val', x: tipX, y: y + rowH / 2 + 4.5 }, pct ? 'n=' + fmt(total) : fmt(total)));
      const rows2 = () => segs.map((s, i) => ({
        color: s.color, name: s.name + (r.notes && r.notes[i] ? ` · ${r.notes[i]}` : ''),
        value: fmt(r.v[i]) + (total ? `（${Math.round(r.v[i] / total * 100)}%）` : ''),
      }));
      const head = `${r.label} · 共 ${fmt(total)}`;
      g.addEventListener('pointermove', e => showTip(e.clientX, e.clientY, head, rows2()));
      g.addEventListener('pointerleave', hideTip);
      g.addEventListener('focus', () => { const b = g.getBoundingClientRect(); showTip(b.left + b.width / 2, b.top, head, rows2()); });
      g.addEventListener('blur', hideTip);
      svg.append(g);
    });
    return svg;
  }

  function dataTable(head, rows) {
    return h('table', { class: 'dtable' },
      h('thead', null, h('tr', null, head.map(t => h('th', { scope: 'col' }, t)))),
      h('tbody', null, rows.map(r => h('tr', null, r.map((c, i) => (i ? h('td', null, c) : h('th', { scope: 'row' }, c)))))));
  }
  const empty = msg => h('div', { class: 'empty' }, msg);

  // 年限分档的配色：第 0 档是「未提及」（没有信息），用灰色；其余档按顺序用蓝色有序渐变（约定见 scripts/lib/schema.py）
  const yearSegs = () => D.buckets.map((b, i) => (i === 0
    ? { name: b, color: '--na', ink: '--na-ink' }
    : { name: b, color: `--ord-${i - 1}`, ink: `--ord-${i - 1}-ink` }));

  // ---------- 图表渲染 ----------
  function renderCharts(F) {
    const catSegs = D.categories.map((c, i) => ({ name: c, color: `--cat-${i}`, ink: `--cat-${i}-ink` }));
    const ordSegs = yearSegs();
    const tableView = S.view === 'table';
    const put = (id, node) => $(`#${id} .body`).replaceChildren(node);
    const widthOf = id => Math.max(300, Math.floor($(`#${id} .body`).clientWidth) || 520);

    if (!F.length) {
      for (const id of ['cardCompany', 'cardYears', 'cardCity']) put(id, empty('没有符合条件的职位'));
    } else {
      // 公司 × 类别
      const src = sourcesOf(F);   // 看板类别 <- 公司自己的原始分类
      const coRows = D.companies.map(c => ({
        label: c.name, key: c.key,
        v: D.categories.map(cat => F.filter(j => j.c === c.key && j.cat === cat).length),
        notes: D.categories.map(cat => (src[c.key] && src[c.key][cat] ? '来自 ' + srcText(src[c.key][cat]) : '')),
      })).filter(r => r.v.some(Boolean));
      const srcOf = (r, cat) => (src[r.key] && src[r.key][cat] ? srcText(src[r.key][cat]) : '—');
      put('cardCompany', tableView
        ? dataTable(['公司', ...D.categories, '合计', ...D.categories.map(c => `${c}来自`)],
          coRows.map(r => [r.label, ...r.v.map(fmt), fmt(r.v.reduce((a, b) => a + b, 0)), ...D.categories.map(cat => srcOf(r, cat))]))
        : h('div', null, hbar({ rows: coRows, segs: catSegs, width: widthOf('cardCompany') }),
          h('div', { class: 'srcs' },
            h('div', { class: 'srcs-t' }, '类别来源：公司自己的分类 → 看板类别'),
            ...coRows.map(r => h('div', { class: 'src-row' }, h('span', { class: 'src-co' }, r.label),
              ...D.categories.map((cat, i) => (src[r.key] && src[r.key][cat]
                ? h('span', { class: 'src-c' }, h('span', { class: 'dot', style: `background:var(--cat-${i})` }), `${cat} ← ${srcText(src[r.key][cat])}`)
                : null)))))));

      // 公司内的工作年限分布
      const yRows = D.companies.map(c => {
        const own = F.filter(j => j.c === c.key);
        return { label: c.name, v: D.buckets.map((b, i) => own.filter(j => j.yb === i).length) };
      }).filter(r => r.v.some(Boolean));
      put('cardYears', tableView
        ? dataTable(['公司', ...D.buckets.map(b => b + '（占比）'), '职位数'], yRows.map(r => {
          const t = r.v.reduce((a, b) => a + b, 0);
          return [r.label, ...r.v.map(v => `${fmt(v)}（${Math.round(v / t * 100)}%）`), fmt(t)];
        }))
        : hbar({ rows: yRows, segs: ordSegs, pct: true, width: widthOf('cardYears') }));

      // 城市 Top 10 × 类别
      const cnt = new Map();
      for (const j of F) for (const c of j.ci) {
        if (!cnt.has(c)) cnt.set(c, D.categories.map(() => 0));
        cnt.get(c)[D.categories.indexOf(j.cat)]++;
      }
      const cityRows = [...cnt].map(([label, v]) => ({ label, v })).sort((a, b) => sum(b.v) - sum(a.v)).slice(0, 10);
      put('cardCity', tableView
        ? dataTable(['城市', ...D.categories, '合计'], cityRows.map(r => [r.label, ...r.v.map(fmt), fmt(sum(r.v))]))
        : hbar({ rows: cityRows, segs: catSegs, width: widthOf('cardCity'), labelMax: 10 }));
    }
  }
  const sum = a => a.reduce((x, y) => x + y, 0);

  // 每家公司、每个看板类别是由公司自己的哪些原始分类合成的：{公司: {看板类别: Map(原始分类 -> 职位数)}}
  function sourcesOf(F) {
    const m = {};
    for (const j of F) {
      const byCat = (m[j.c] = m[j.c] || {});
      const raw = (byCat[j.cat] = byCat[j.cat] || new Map());
      raw.set(j.rc, (raw.get(j.rc) || 0) + 1);
    }
    return m;
  }
  // 只有一个来源时写名字；多个来源时带上各自的职位数，如「技术类 340、技术 66」
  const srcText = mp => [...mp].sort((a, b) => b[1] - a[1]).map(([n, c]) => (mp.size > 1 ? `${n} ${fmt(c)}` : n)).join('、');

  // ---------- 职位列表 ----------
  const cmp = {
    date: (a, b) => b.dt.localeCompare(a.dt),
    yasc: (a, b) => (a.ym ?? -1) - (b.ym ?? -1) || b.dt.localeCompare(a.dt),
    ydesc: (a, b) => (b.ym ?? -1) - (a.ym ?? -1) || b.dt.localeCompare(a.dt),
    co: (a, b) => CO[a.c].idx - CO[b.c].idx || b.dt.localeCompare(a.dt),
  };

  function loadJD(key) {
    if (!jdCache[key]) jdCache[key] = fetch(`data/jd/${key}.json`, { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
    return jdCache[key];
  }

  async function fillDetail(td, j) {
    td.replaceChildren(empty('加载职位描述…'));
    try {
      const [desc, req] = (await loadJD(j.c))[j.id] || ['', ''];
      const co = CO[j.c];
      const link = j.u && j.u.startsWith('https://')
        ? h('a', { href: j.u, target: '_blank', rel: 'noopener noreferrer' }, '打开职位页 ↗')
        : h('a', { href: co.list_url, target: '_blank', rel: 'noopener noreferrer' }, `暂无直达链接，去${co.name}官网职位列表搜索标题 ↗`);
      td.replaceChildren(
        h('div', { class: 'jd' },
          h('div', null, h('h4', null, '职位描述'), h('div', { class: 'txt' }, desc || '（无）')),
          h('div', null, h('h4', null, '任职要求'), h('div', { class: 'txt' }, req || '（无）'))),
        h('div', { class: 'detail-actions' }, link,
          ...(CO[j.c].facets || []).map((f, i) => {
            const v = [].concat((j.f || [])[i] || []).filter(x => x && x !== NO_VALUE);
            return v.length ? h('span', null, `${f.label}：${v.join('、')}`) : null;
          }),
          j.yp ? h('span', null, '优先年限：' + j.yp) : null));
    } catch (e) {
      td.replaceChildren(empty('职位描述加载失败，请刷新重试。'));
    }
  }

  function jobRow(j) {
    const btn = h('button', { class: 'title-btn', type: 'button', 'aria-expanded': 'false' }, j.t);
    const tr = h('tr', { class: 'job' },
      h('td', { class: 'col-co' }, CO[j.c].name),
      h('td', null,
        h('div', null, btn),
        j.dp ? h('div', { class: 'dept' }, j.dp) : null,
        h('div', { class: 'mobile-meta' }, `${CO[j.c].name} · ${j.cat} · ${j.ci.join('、') || '—'} · ${j.y}`)),
      h('td', { class: 'col-cat' }, j.cat),
      h('td', { class: 'col-city' }, j.ci.join('、') || '—'),
      h('td', { class: 'col-y' }, j.y, j.yp ? h('div', { class: 'pref' }, '优先 ' + j.yp) : null),
      h('td', { class: 'col-dt' }, j.dt));
    let detail = null;
    btn.addEventListener('click', () => {
      if (detail) { detail.remove(); detail = null; btn.setAttribute('aria-expanded', 'false'); return; }
      const td = h('td', { colspan: 6 });
      detail = h('tr', { class: 'detail' }, td);
      tr.after(detail);
      btn.setAttribute('aria-expanded', 'true');
      fillDetail(td, j);
    });
    return tr;
  }

  function renderTable(F) {
    const list = [...F].sort(cmp[S.sort]);
    const pages = Math.max(1, Math.ceil(list.length / PAGE));
    S.page = Math.min(S.page, pages - 1);
    $('#jobsBody').replaceChildren(...list.slice(S.page * PAGE, (S.page + 1) * PAGE).map(jobRow));
    $('#listCount').textContent = `${fmt(list.length)} 个`;
    const go = d => () => { S.page += d; renderTable(F); $('#listH').scrollIntoView({ block: 'start' }); };
    $('#pager').replaceChildren(
      h('button', { class: 'btn', type: 'button', disabled: S.page === 0, onclick: go(-1) }, '上一页'),
      h('span', null, list.length ? `第 ${S.page + 1} / ${pages} 页` : '没有符合条件的职位'),
      h('button', { class: 'btn', type: 'button', disabled: S.page >= pages - 1, onclick: go(1) }, '下一页'));
  }

  // ---------- 公司专属筛选 ----------
  // 各公司的数据维度不一样（有的有二级类别，有的有业务线……），由各公司在 META["facets"] 里声明。
  // 只选中一家公司时才显示：多家公司的取值混在一起没法选。
  const NO_VALUE = '（未标注）';
  function syncFacets() {
    const co = S.cos.size === 1 ? CO[[...S.cos][0]] : null;
    const key = co && co.facets.length ? co.key : null;
    if (key === S.facCo) return;                    // 公司没变就不重建，避免打字时下拉框被重置
    S.facCo = key; S.fac = {};
    const row = $('#facetRow');
    row.hidden = !key;
    row.replaceChildren(...(key ? [
      h('span', { class: 'fac-title' }, `${co.name} 专属筛选`),
      ...co.facets.map((f, i) => h('label', { class: 'fld' }, f.label,
        h('select', { onchange: e => { S.fac[i] = e.target.value; update(true); } },
          h('option', { value: '' }, '全部'),
          ...f.values.map(([v, n]) => h('option', { value: v }, `${v}（${fmt(n)}）`)))))] : []));
  }

  // ---------- 总控 ----------
  let lastF = [];
  function update(resetPage) {
    if (resetPage) S.page = 0;
    syncFacets();
    lastF = D.jobs.filter(passes);
    renderKpis(lastF);
    renderCharts(lastF);
    renderTable(lastF);
    $('#fReset').hidden = isDefault();
    DD.company.sync(); DD.cat.sync();
  }

  /* 可多选的下拉框。set 是选中值的集合（空 = 不限制）；选项里的勾选框是原生 input，键盘可达，Esc 关闭并回到按钮。 */
  const DD = {};
  const openMenus = new Set();
  function closeAll(except) { for (const m of openMenus) if (m !== except) m.close(); }
  document.addEventListener('pointerdown', e => { for (const m of openMenus) if (!m.root.contains(e.target)) m.close(); });

  function multiDropdown({ root, label, allText, summarize, options, set }) {
    const btn = h('button', { class: 'dd-btn', type: 'button', 'aria-haspopup': 'true', 'aria-expanded': 'false', 'aria-labelledby': `${label} ${root.id}-t` });
    const menu = h('div', { class: 'dd-menu', role: 'group', 'aria-labelledby': label, hidden: true });
    const boxes = options.map(o => {
      const input = h('input', { type: 'checkbox', value: o.value });
      input.addEventListener('change', () => { input.checked ? set.add(o.value) : set.delete(o.value); update(true); });
      menu.append(h('label', { class: 'dd-item' }, input,
        o.color ? h('span', { class: 'dot', style: `background:var(${o.color})` }) : null,
        h('span', null, o.label), h('span', { class: 'n' }, fmt(o.count))));
      return input;
    });
    const clear = h('button', { class: 'dd-clear', type: 'button' }, '清除');
    clear.addEventListener('click', () => { set.clear(); update(true); });
    menu.append(clear);
    const self = {
      root,
      close() { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); openMenus.delete(self); },
      sync() {
        boxes.forEach(b => { b.checked = set.has(b.value); });
        const t = h('span', { id: `${root.id}-t` }, set.size ? summarize(options.filter(o => set.has(o.value))) : allText);
        btn.replaceChildren(t);
        btn.classList.toggle('on', set.size > 0);
        clear.hidden = !set.size;
      },
    };
    btn.addEventListener('click', () => {
      if (!menu.hidden) return self.close();
      closeAll(self); menu.hidden = false; btn.setAttribute('aria-expanded', 'true'); openMenus.add(self);
    });
    root.addEventListener('keydown', e => { if (e.key === 'Escape' && !menu.hidden) { self.close(); btn.focus(); } });
    root.replaceChildren(btn, menu);
    self.sync();
    return self;
  }

  function buildControls() {
    const opt = (v, t) => h('option', { value: v }, t);
    $('#fRange').replaceChildren(opt('all', '全部时间'), opt('7', '近 7 天'), opt('30', '近 30 天'), opt('90', '近 90 天'));
    const countBy = f => { const m = {}; for (const j of D.jobs) m[f(j)] = (m[f(j)] || 0) + 1; return m; };
    const perCo = countBy(j => j.c), perCat = countBy(j => j.cat);
    DD.company = multiDropdown({
      root: $('#fCompany'), label: 'lCompany', allText: '全部公司', set: S.cos,
      summarize: sel => (sel.length === 1 ? sel[0].label : `已选 ${sel.length} 家公司`),
      options: D.companies.map(c => ({ value: c.key, label: c.name, count: perCo[c.key] || 0 })),
    });
    DD.cat = multiDropdown({
      root: $('#fCat'), label: 'lCat', allText: '全部类别', set: S.cats,
      summarize: sel => (sel.length === 1 ? sel[0].label : `已选 ${sel.length} 个类别`),
      options: D.categories.map((c, i) => ({ value: c, label: c, color: `--cat-${i}`, count: perCat[c] || 0 })),
    });
    const cities = new Map();
    for (const j of D.jobs) for (const c of j.ci) cities.set(c, (cities.get(c) || 0) + 1);
    $('#fCity').replaceChildren(opt('', '全部城市'),
      ...[...cities].filter(([, n]) => n >= 5).sort((a, b) => b[1] - a[1]).map(([c, n]) => opt(c, `${c}（${fmt(n)}）`)));
    $('#fYears').replaceChildren(opt('', '全部'), ...D.buckets.map((b, i) => opt(String(i), b)));

    $('#fRange').onchange = e => { S.range = e.target.value; update(true); };
    $('#fCity').onchange = e => { S.city = e.target.value; update(true); };
    $('#fYears').onchange = e => { S.yb = e.target.value; update(true); };
    $('#fSort').onchange = e => { S.sort = e.target.value; update(true); };
    let timer;
    $('#fQuery').oninput = e => { clearTimeout(timer); timer = setTimeout(() => { S.q = e.target.value.trim(); update(true); }, 150); };
    $('#fReset').onclick = () => {
      Object.assign(S, { range: 'all', city: '', yb: '', q: '' }); S.cos.clear(); S.cats.clear();
      $('#fRange').value = 'all'; $('#fCity').value = ''; $('#fYears').value = ''; $('#fQuery').value = '';
      update(true);
    };
    for (const b of document.querySelectorAll('.seg-ctl button'))
      b.onclick = () => {
        S.view = b.dataset.view;
        for (const o of document.querySelectorAll('.seg-ctl button')) o.setAttribute('aria-pressed', o === b);
        renderCharts(lastF);
      };

    $('#catLegend').replaceChildren(...D.categories.map((c, i) =>
      h('span', { class: 'k' }, h('span', { class: 'sw', style: `background:var(--cat-${i})` }), c)));
    $('#ordLegend').replaceChildren(...yearSegs().map(s =>
      h('span', { class: 'k' }, h('span', { class: 'sw', style: `background:var(${s.color})` }), s.name)));
  }

  function buildTexts() {
    $('#meta').textContent = `数据日期 ${D.generated} · ${D.companies.length} 家公司 · 共 ${fmt(D.jobs.length)} 个职位`;
    const noLink = D.companies.filter(c => !D.jobs.some(j => j.c === c.key && j.u)).map(c => c.name);
    const updated = D.companies.filter(c => c.date_label !== '发布时间').map(c => c.name);
    $('#foot').replaceChildren(
      h('p', null, '说明'),
      h('ul', null,
        h('li', null, `数据来自各公司官网公开的招聘接口，每周一更新；这里只收录社招的${D.categories.map(c => `「${c}」`).join('')}岗位。`),
        h('li', null, '工作年限是从任职要求文本里自动识别的「最低年限」（如「3-5 年」记为 3 年）。「未提及」指任职要求里没写年限；「明确不限」指写了不限，或写的是 0-N 年 / N 年以内这类没有最低门槛的要求。个别写法特殊的职位可能识别有误，以官网为准。'),
        h('li', null, '「打开职位页」指向各公司官网的职位详情页' + (noLink.length ? `（${noLink.join('、')}暂无直达链接）` : '') + '；打不开时请到官网职位列表按标题搜索。'),
        updated.length ? h('li', null, `${updated.join('、')}的日期是更新时间而非发布时间。`) : null,
        ...D.companies.filter(c => c.note).map(c => h('li', null, `${c.name}：${c.note}`)),
        h('li', null, '下载 CSV：', ...D.companies.flatMap(c => [
          `${c.name}（`, ...c.csv.flatMap((cat, i) => [i ? '、' : '', h('a', { href: `data/csv/${c.key}/${encodeURIComponent(cat)}.csv`, download: '' }, cat)]), '） '])),
        h('li', null, '职位信息来自各公司官网的公开页面，版权归原公司所有，本站仅整理汇总供参考；职位是否仍在招、具体要求均以官网为准。')));
  }

  function bindTheme() {
    $('#themeBtn').onclick = () => {
      const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('jobs-theme', next); } catch (e) { /* 隐私模式等场景下存不了也没关系 */ }
      hideTip();
    };
  }

  fetch('data/jobs.json', { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      D = data;
      D.companies.forEach((c, i) => { c.idx = i; CO[c.key] = c; });
      bindTheme();
      buildControls();
      buildTexts();
      update(true);
      let lastW = 0;
      new ResizeObserver(() => {                                 // 容器宽度变了才重画，避免无谓重绘
        const w = Math.round($('#charts').clientWidth);
        if (w && w !== lastW) { const first = !lastW; lastW = w; if (!first) renderCharts(lastF); }
      }).observe($('#charts'));
    })
    .catch(err => {
      $('#meta').textContent = '数据加载失败：' + err.message + '。本地预览请运行 python3 -m http.server -d site 8000，不能直接双击打开 html。';
    });
})();
