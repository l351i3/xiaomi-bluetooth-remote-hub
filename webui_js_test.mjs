// webui_js_test.mjs — t1_webui 前端 JS 逻辑测试（Node vm + DOM stub）
// 覆盖 v2.4「⟳ 按住连发」（渲染 + save 派生）、v2.7 配置指纹（save 带 rev / 409 提示刷新）、
// v2.9「初始 tab 跟随当前激活目标」（/api/state → TAB；取不到回退 atv）、
// v2.10 自定义 URL/RUN 输入（customApp 哨兵→prompt→选项追加；save 哨兵清理；opts 回显）、
// v2.11 APP:CLOSE 渲染（#116 选项/selected + extLabel 特判）
// 用法: node webui_js_test.mjs   （需要 T1 :8765 可访问，读线上真实配置做 mock 数据；v2.7 需已部署）
//      T1 地址默认取下方常量，可用环境变量 T1_IP 覆盖（发布版常量已脱敏为占位符，届时需替换或设 T1_IP）
import fs from 'node:fs';
import vm from 'node:vm';

const SRC = new URL('./t1_webui.py', import.meta.url).pathname;
const T1IP = process.env.T1_IP || 'T1_IP'; // ← 改成你的 T1 地址（或设环境变量 T1_IP）
const API = `http://${T1IP}:8765/api/keymap`;

let pass = 0, fail = 0;
function check(name, got, want) {
  const okv = JSON.stringify(got) === JSON.stringify(want);
  console.log((okv ? '  PASS ' : '  FAIL ') + name + (okv ? '' : ` | got=${JSON.stringify(got)} want=${JSON.stringify(want)}`));
  okv ? pass++ : fail++;
}
function assert(name, cond) { check(name, !!cond, true); }

// —— 提取 PAGE_KEYMAP 的 <script> ——
const py = fs.readFileSync(SRC, 'utf8');
const mm = py.match(/PAGE_KEYMAP = """([\s\S]*?)"""/);
if (!mm) { console.error('PAGE_KEYMAP 提取失败'); process.exit(1); }
const html = mm[1].replace('%%CSS%%', '');
const sm = html.match(/<script>([\s\S]*?)<\/script>/);
if (!sm) { console.error('<script> 提取失败'); process.exit(1); }
// v2.10: 模拟 Python 字符串求值——源码里的 \\s 经 Python 求值后 = 浏览器实际收到的 \s
// （此前直接测源码原文，正则语义与浏览器不一致；所有含反斜杠的行仅此一处，替换安全）
const script = sm[1].replace(/\\\\/g, '\\');

// —— 线上真实配置（mock 数据源）——
const LIVE = await (await fetch(API)).json();
if (!LIVE.repeat_opt) { console.error('线上缺少 repeat_opt（部署未生效？）'); process.exit(1); }
if (!LIVE.rev) { console.error('线上缺少 rev（v2.7 部署未生效？）'); process.exit(1); }

// —— DOM stub ——
const nodes = {};
function getNode(id) {
  const node = {
    id, textContent: '', className: '', children: [], dataset: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {},
    appendChild(c) { node.children.push(c); },
  };
  let _html = '';
  Object.defineProperty(node, 'innerHTML', {
    get() { return _html; },
    set(v) { _html = v; if (v === '') node.children.length = 0; },
  });
  return node;
}
function tabStub(t) {
  return { dataset: { t }, classList: { toggle() {}, add() {}, remove() {} }, _h: null,
    addEventListener(ev, fn) { this._h = fn; } };
}
const tabStubs = ['atv', 'mac', 'win'].map(tabStub);
const SELECTS = [];
const btnStub = (id) => ({ id, _h: null, addEventListener(ev, fn) { this._h = fn; } });
const saveBtn = btnStub('save'), resetBtn = btnStub('reset');

const document = {
  getElementById(id) {
    if (id === 'save') return saveBtn;
    if (id === 'reset') return resetBtn;
    return (nodes[id] ??= getNode(id));
  },
  querySelectorAll(sel) {
    if (sel === '.tab') return tabStubs;
    if (sel === 'select[data-code]') return SELECTS;
    return [];
  },
  createElement() { return { innerHTML: '', className: '', children: [] }; },
};

let posted = null;
let fetchMode = 'ok';                       // 'ok' | 'stale'（v2.7 409 场景）
let stateValue = 'mac';                     // v2.9: 当前激活目标（mock，用非默认值以证明 boot 生效）
async function stubFetch(url, opts) {
  if (opts && opts.method === 'POST') {
    posted = JSON.parse(opts.body);
    if (fetchMode === 'stale') {
      return { status: 409, json: async () => ({ ok: false, error: 'stale',
        msg: '配置已变化（可能在其他页面/终端操作过），请刷新页面后重试' }) };
    }
    return { status: 200, json: async () => ({ ok: true, rev: LIVE.rev }) };
  }
  if (String(url).includes('/api/state')) {                      // v2.9
    return { status: 200, json: async () => ({ voice_target: stateValue }) };
  }
  return { status: 200, json: async () => LIVE };
}

const ctx = vm.createContext({ document, fetch: stubFetch, prompt: () => null,
  confirm: () => true, setTimeout, clearTimeout, console });
vm.runInContext(script, ctx);
await new Promise(r => setTimeout(r, 100));   // 等 load()

// —— 渲染断言 ——
check('无加载错误', nodes['grid'].textContent, '');
check('初始渲染 13 行', nodes['grid'].children.length, 13);
assert('初始 tab=当前目标 mac（v2.9）', nodes['hint'].textContent.includes('macOS'));

tabStubs[0]._h();                              // 切到 ATV
check('切到 ATV 渲染 13 行', nodes['grid'].children.length, 13);
tabStubs[1]._h();                              // 切到 Mac tab
check('渲染 13 行(mac)', nodes['grid'].children.length, 13);
assert('hint 文案提及按住连发', nodes['hint'].textContent.includes('按住连发'));

const byCode = {};
for (const row of nodes['grid'].children) {
  const m = row.innerHTML.match(/data-code="(\d+)"/);
  if (m) byCode[m[1]] = row.innerHTML;
}
assert('#158 行存在', byCode['158']);
assert('#158 长按列=按住连发 selected', byCode['158'].includes('data-f="long" data-prev="__REPEAT__"'));
assert('#158 长按列可编辑(非disabled)', !/data-f="long"[^>]* disabled/.test(byCode['158']));
assert('#127 长按列=按住连发 selected', byCode['127'].includes('data-f="long" data-prev="__REPEAT__"'));
assert('#102 长按列=APP:PICK selected', byCode['102'].includes('data-f="long" data-prev="APP:PICK"'));
assert('#103 长按列=按住连发 selected', byCode['103'].includes('data-f="long" data-prev="__REPEAT__"'));
assert('#158 长按下拉含连发选项', byCode['158'].includes('⟳ 按住连发（连续重复）'));
assert('#63 locked 全禁(3 sel)', (byCode['63'].match(/\bdisabled\b/g) || []).length >= 3);
assert('#28 长按列普通下拉(含回车选项)', byCode['28'].includes('>回车</option>'));

// —— v2.11: APP:CLOSE 渲染（来源 = KB_CHOICES 新项 + keymap #116 long 生产绑定）——
assert('#116 下拉含关闭当前应用选项', (byCode['116'] || '').includes('★ 关闭当前应用（长按电源键）'));
assert('#116 长按列=APP:CLOSE selected', (byCode['116'] || '').includes('data-f="long" data-prev="APP:CLOSE"'));
assert('extLabel APP:CLOSE 特判', ctx.extLabel('APP:CLOSE') === '关闭当前应用（长按电源键）');

// —— v2.5: FOCUS_INPUT 渲染（依赖线上 mac 份 #41 已配）——
assert('#41 单击=跳转输入框 selected', (byCode['41'] || '').includes('data-f="single" data-prev="FOCUS_INPUT"'));
assert('#41 单击下拉含跳转输入框选项', (byCode['41'] || '').includes('★ 跳转输入框'));

// —— save() 派生断言 ——
function fill158(single, long) {
  SELECTS.length = 0;
  SELECTS.push(
    { dataset: { code: '158', f: 'single' }, value: single },
    { dataset: { code: '158', f: 'double' }, value: '' },
    { dataset: { code: '158', f: 'long' }, value: long },
  );
}
fill158('BACKSPACE', '__REPEAT__');           // 长按列选「按住连发」
await ctx.save();
check('save target=mac', posted.target, 'mac');
check('save 连发派生', posted.keys['158'], { single: 'BACKSPACE', double: null, long: null, repeat: true });
check('save 带 rev(v2.7)', posted.rev, LIVE.rev);

posted = null;
fill158('BACKSPACE', '');                     // 长按列改回「无」
await ctx.save();
check('save 撤销连发', posted.keys['158'], { single: 'BACKSPACE', double: null, long: null, repeat: false });

// —— v2.7: 409 处理（旧页面保存被拒 → 提示刷新，而非静默覆盖）——
fetchMode = 'stale';
nodes['toast'].textContent = '';
fill158('BACKSPACE', '__REPEAT__');
await ctx.save();
assert('409 时 toast 提示刷新', nodes['toast'].textContent.includes('刷新'));
assert('409 时 toast 含警示', nodes['toast'].textContent.includes('⚠'));
fetchMode = 'ok';

// —— v2.10: save() 哨兵清理（URL/RUN 占位不落盘）+ 合法值透传 ——
SELECTS.length = 0;
SELECTS.push(
  { dataset: { code: '116', f: 'single' }, value: '__CUSTOM_URL__' },
  { dataset: { code: '116', f: 'double' }, value: '' },
  { dataset: { code: '116', f: 'long' }, value: '__CUSTOM_RUN__' },
);
posted = null;
await ctx.save();
check('save 清 URL/RUN 占位', posted.keys['116'], { single: null, double: null, long: null, repeat: false });

SELECTS.length = 0;
SELECTS.push(
  { dataset: { code: '116', f: 'single' }, value: 'URL:https://www.baidu.com' },
  { dataset: { code: '116', f: 'double' }, value: '' },
  { dataset: { code: '116', f: 'long' }, value: '' },
);
posted = null;
await ctx.save();
check('save URL 值原样透传', posted.keys['116'],
  { single: 'URL:https://www.baidu.com', double: null, long: null, repeat: false });

// —— v2.10: customApp 泛化（URL/RUN 哨兵 → prompt → 选项追加；取消恢复）——
let promptAnswer = null;
const n2 = {};
const getN2 = (id) => (n2[id] ??= getNode(id));
const document2 = {
  getElementById: (id) => (id === 'save' ? btnStub('save2') : id === 'reset' ? btnStub('reset2') : getN2(id)),
  querySelectorAll: () => [],
  createElement: () => ({ innerHTML: '', className: '', children: [], value: '', textContent: '' }),
};
const fetch2 = async () => ({ status: 200, json: async () => LIVE });
const ctx2 = vm.createContext({ document: document2, fetch: fetch2, prompt: () => promptAnswer,
  confirm: () => true, setTimeout, clearTimeout, console });
vm.runInContext(script, ctx2);
await new Promise(r => setTimeout(r, 100));

const mkSel = () => ({ value: '', dataset: {}, children: [], appendChild(c) { this.children.push(c); } });

const c1 = mkSel(); c1.value = '__CUSTOM_URL__'; c1.dataset.prev = 'ENTER'; promptAnswer = null;
ctx2.customApp(c1);
check('custom URL 取消恢复原值', [c1.value, c1.dataset.prev, c1.children.length], ['ENTER', 'ENTER', 0]);

const c2 = mkSel(); c2.value = '__CUSTOM_URL__'; c2.dataset.prev = 'ENTER'; promptAnswer = 'https://a b.com';
ctx2.customApp(c2);
check('custom URL 含空格拒绝', c2.value, 'ENTER');
assert('custom URL 含空格 toast 提示', n2['toast'].textContent.includes('不能含空格'));

const c3 = mkSel(); c3.value = '__CUSTOM_URL__'; c3.dataset.prev = ''; promptAnswer = 'https://www.baidu.com';
ctx2.customApp(c3);
check('custom URL 选中新值', c3.value, 'URL:https://www.baidu.com');
check('custom URL 追加选项', [c3.children.length, c3.children[0].value, c3.children[0].textContent],
  [1, 'URL:https://www.baidu.com', '打开网页 https://www.baidu.com']);

const c4 = mkSel(); c4.value = '__CUSTOM_URL__'; c4.dataset.prev = '';
ctx2.customApp(c4);
c4.value = '__CUSTOM_URL__';
ctx2.customApp(c4);
check('custom URL 重复输入不重复追加', [c4.value, c4.children.length], ['URL:https://www.baidu.com', 1]);

const c5 = mkSel(); c5.value = '__CUSTOM_RUN__'; c5.dataset.prev = ''; promptAnswer = 'calc.exe';
ctx2.customApp(c5);
check('custom RUN 选中新值', c5.value, 'RUN:calc.exe');
check('custom RUN 选项文案', c5.children[0].textContent, '执行 calc.exe');

const c6 = mkSel(); c6.value = '__CUSTOM_APP__'; c6.dataset.prev = ''; promptAnswer = 'Chrome';
ctx2.customApp(c6);
check('custom APP 老路径不变', [c6.value, c6.children[0].textContent], ['APP:Chrome', '打开/切换到 Chrome']);

assert('opts 回显 URL 值(标签)', ctx2.opts([['', '— 无 —']], 'URL:https://x').includes('打开网页 https://x'));
assert('opts 回显 RUN 值(标签)', ctx2.opts([['', '— 无 —']], 'RUN:foo.sh').includes('执行 foo.sh'));
assert('opts 值引号转义', ctx2.opts([['', '— 无 —']], 'URL:a"b').includes('&quot;'));

// —— v2.9: 初始 tab 跟随状态（补 win 场景 + 取不到时回退 atv；主场景 mac 已断言）——
async function runBoot(state) {
  const n2 = {};
  const getNode2 = (id) => (n2[id] ??= { id, textContent: '', className: '', children: [],
    dataset: {}, classList: { add() {}, remove() {}, toggle() {} }, addEventListener() {},
    appendChild(c) { this.children.push(c); }, innerHTML: '' });
  const tabs2 = ['atv', 'mac', 'win'].map(tabStub);
  const document2 = {
    getElementById: (id) => getNode2(id),
    querySelectorAll: (sel) => (sel === '.tab' ? tabs2 : []),
    createElement: () => ({ innerHTML: '', className: '', children: [] }),
  };
  const fetch2 = async (url) => {
    if (String(url).includes('/api/state')) {
      if (state === '__FAIL__') throw new Error('net down');
      return { status: 200, json: async () => ({ voice_target: state }) };
    }
    return { status: 200, json: async () => LIVE };
  };
  const ctx2 = vm.createContext({ document: document2, fetch: fetch2, prompt: () => null,
    confirm: () => true, setTimeout, clearTimeout, console });
  vm.runInContext(script, ctx2);
  await new Promise(r => setTimeout(r, 100));
  return n2;
}
assert('初始 tab=win（v2.9）', (await runBoot('win'))['hint'].textContent.includes('Windows'));
assert('state 取不到回退 atv（v2.9）', (await runBoot('__FAIL__'))['hint'].textContent.includes('ATV'));

console.log(`\n== JS harness: ${pass} PASS / ${fail} FAIL ==`);
process.exit(fail ? 1 : 0);
