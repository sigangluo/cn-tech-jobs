/* 筛选状态 <-> URL 查询串。纯函数，不碰 DOM，所以可以在 Node 里单测（tests/state.test.js）。
   和官网一样，筛选结果可以收藏、分享：app.js 每次筛选后用 history.replaceState 写回地址栏，打开时再读出来。
   这里只负责格式；取值是否合法（公司还在不在、城市有没有）由 app.js 对照 jobs.json 校验。

   查询串里默认值一律省略。多选项用重复的参数（co=a&co=b），因为取值里可能有逗号。
   公司专属筛选按序号存成 f0 / f1 …，只在选中恰好一家公司时才有意义。 */
(function (root) {
  'use strict';

  const SCALARS = { range: 'r', source: 'src', country: 'cn', yb: 'y', q: 'q', sort: 'sort', view: 'v' };
  const DEFAULTS = { range: 'all', source: '', country: '', yb: '', q: '', sort: 'date', view: 'chart' };
  const SETS = { cos: 'co', cats: 'cat', cities: 'ci' };

  /* S 是 app.js 的筛选状态：标量字段 + Set（cos / cats / cities）+ fac（{序号: Set}） */
  function encodeState(S) {
    const p = new URLSearchParams();
    for (const [k, name] of Object.entries(SCALARS)) if (S[k] !== DEFAULTS[k] && S[k] != null) p.set(name, S[k]);
    for (const [k, name] of Object.entries(SETS)) for (const v of S[k] || []) p.append(name, v);
    for (const [i, set] of Object.entries(S.fac || {})) for (const v of set) p.append('f' + i, v);
    return p.toString();
  }

  /* 返回原始取值：标量是字符串（缺省为默认值），多选是数组，fac 是 {序号: 数组} */
  function decodeState(search) {
    const p = new URLSearchParams(search);
    const out = { fac: {} };
    for (const [k, name] of Object.entries(SCALARS)) out[k] = p.has(name) ? p.get(name) : DEFAULTS[k];
    for (const [k, name] of Object.entries(SETS)) out[k] = p.getAll(name);
    for (const name of new Set(p.keys())) {
      const m = /^f(\d+)$/.exec(name);
      if (m) out.fac[m[1]] = p.getAll(name);
    }
    return out;
  }

  const api = { encodeState, decodeState, DEFAULTS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.JobsState = api;
})(typeof window !== 'undefined' ? window : globalThis);
