// 前端筛选状态 <-> URL 的往返测试。运行：node tests/state.test.js（CI 里也会跑）
const assert = require('node:assert/strict');
const { encodeState, decodeState, DEFAULTS } = require('../site/assets/state.js');

const base = () => ({ ...DEFAULTS, cos: new Set(), cats: new Set(), cities: new Set(), fac: {} });

// 默认状态编码为空串，地址栏保持干净
assert.equal(encodeState(base()), '');

// 往返：标量、多选、公司专属筛选
const S = base();
Object.assign(S, { range: '30', q: 'C++ 开发', yb: '0', sort: 'yasc', view: 'table', source: 'inferred', country: '中国' });
S.cos.add('bytedance'); S.cities.add('北京'); S.cities.add('San Jose(USA)'); S.cats.add('技术');
S.fac[1] = new Set(['A、B', '含,逗号']);
const back = decodeState('?' + encodeState(S));
assert.equal(back.range, '30');
assert.equal(back.q, 'C++ 开发');
assert.equal(back.yb, '0');                 // 「0」是合法的年限档（未提及），不能被当成空
assert.equal(back.sort, 'yasc');
assert.equal(back.view, 'table');
assert.equal(back.source, 'inferred');
assert.equal(back.country, '中国');
assert.deepEqual(back.cos, ['bytedance']);
assert.deepEqual(back.cats, ['技术']);
assert.deepEqual(back.cities.sort(), ['San Jose(USA)', '北京']);
assert.deepEqual(back.fac[1].sort(), ['A、B', '含,逗号']);

// 空查询串 = 全部默认；未知参数被忽略
const empty = decodeState('');
assert.equal(empty.range, 'all');
assert.deepEqual(empty.cos, []);
assert.deepEqual(empty.fac, {});
assert.deepEqual(decodeState('?utm_source=x').cos, []);

console.log('state.test.js: ok');
