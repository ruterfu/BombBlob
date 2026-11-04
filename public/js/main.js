import { audio, TRACKS } from './audio.js';
import { Connection, guestLogin, idLogin, savedId, fetchLoginConfig, oauthExchange, UnknownIdError, ApiError, cleanText, cleanChat, stripSpaces, wireLang } from './net.js';
import { SKINS, HATS, BASE_HATS, TEAM_COLORS, POWERUPS, BOMB_FX, ITEM_SLOTS, powerSize, drawAvatar, drawMapPreview } from './themes.js';
import { t, getLang, setLang, onLangChange, applyI18n, displayName, mapText, normalizeLang } from './i18n.js';
import { MenuStage } from './stage.js';
// 所有模块（含对局场景）都在启动时静态加载，之后不再请求任何静态资源
import { GameScene } from './scene.js';
import { icon, hydrateIcons, drawIcon } from './icons.js';
import { getMsaa, setMsaa } from './gfx.js';
import { setLevelTable, levelOf, levelFloor, levelCeil, levelProgress, tierOf, hatUnlocked, HAT_UNLOCK, levelBadge, setShop, shopItems, shopItem } from './levels.js';

const MAX_PLAYERS = 6;
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const state = {
  user: null,
  conn: null,
  maps: [],
  lobby: { rooms: [], online: 0 },
  room: null,
  game: null,
  last: null,
  screen: null,
  resultShown: false,
};
let scene = null;
let stage = null;

// ================= 通用：转场 / 提示 / 特效 =================
let transitioning = null;
function show(screen, instant = false) {
  if (state.screen === screen) return;
  const apply = () => {
    state.screen = screen;
    for (const s of ['login', 'create', 'lobby', 'room', 'game']) $('#screen-' + s).classList.toggle('hidden', s !== screen);
    if (screen === 'game') stage?.stop();
    else {
      stage?.start();
      audio.play('lobby');
    }
    if (screen === 'login') stage?.showLogin(loginSkin, 0);
    if (screen === 'create') stage?.showLogin(charSel?.skin ?? 0, charSel?.hat ?? 0);
    // 两边的装饰炸弹：登录 / 创建角色时用默认样式，进入大厅后换成自己正在用的炸弹特效
    if (screen === 'login' || screen === 'create') stage?.setBombStyle(null, '');
    else if (state.user) stage?.setBombStyle(state.user.skin, state.user.bomb?.style);
    if (screen === 'lobby' && state.user) stage?.showLobby(state.user);
    if (screen === 'room' && state.room) stage?.showRoom(localizedRoom(state.room), state.user.id);
  };
  if (instant || !state.screen) return apply();
  // 圆形遮罩转场
  const tr = $('#transition');
  clearTimeout(transitioning);
  tr.className = 'in';
  audio.fx('whoosh');
  transitioning = setTimeout(() => {
    apply();
    tr.className = 'out';
    transitioning = setTimeout(() => (tr.className = ''), 400);
  }, 300);
}

function toast(msg, err = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').appendChild(el);
  while ($('#toasts').children.length > 4) $('#toasts').firstChild.remove();
  setTimeout(() => el.classList.add('out'), 2800);
  setTimeout(() => el.remove(), 3100);
}

/** 有 GitHub 头像时显示头像图片（右下角叠一个小角色标识颜色），否则画角色头像 */
function avatarEl(person, size = 64, opts) {
  if (!person.avatar) return avatarCanvas(person.skin, person.hat, size, opts);
  const box = document.createElement('span');
  box.className = 'gh-avatar' + (opts?.dead ? ' dead' : '');
  box.style.setProperty('--sz', size * 2 + 'px');
  box.style.setProperty('--skin', (SKINS[person.skin] || SKINS[0]).color);
  const img = document.createElement('img');
  img.src = person.avatar;
  img.alt = '';
  img.referrerPolicy = 'no-referrer';
  img.loading = 'lazy';
  img.onerror = () => box.replaceWith(avatarCanvas(person.skin, person.hat, size, opts)); // 加载失败退回角色头像
  box.appendChild(img);
  return box;
}

function avatarCanvas(skin, hat, size = 64, opts) {
  const c = document.createElement('canvas');
  c.width = c.height = size * 2;
  drawAvatar(c.getContext('2d'), size, size * 1.05, size * 0.72, skin, hat, opts);
  return c;
}

function openModal(id) { $(id).classList.remove('hidden'); audio.fx('whoosh', { vol: 0.5 }); }
function closeModals() { $$('.modal').forEach((m) => m.classList.add('hidden')); }
document.addEventListener('click', (e) => {
  if (e.target.closest('[data-close]')) closeModals();
  else if (e.target.classList.contains('modal') && e.target.id !== 'id-modal' && e.target.id !== 'confirm-modal') closeModals();
});

/** 游戏风格的确认框（替代浏览器 confirm） */
function confirmDialog(text, { title = t('confirm.title'), yes = t('confirm.yes'), no = t('confirm.no') } = {}) {
  return new Promise((resolve) => {
    $('#confirm-title').textContent = title;
    $('#confirm-text').textContent = text;
    $('#confirm-yes').textContent = yes;
    $('#confirm-no').textContent = no;
    openModal('#confirm-modal');
    const done = (v) => {
      $('#confirm-modal').classList.add('hidden');
      resolve(v);
    };
    $('#confirm-yes').onclick = () => done(true);
    $('#confirm-no').onclick = () => done(false);
  });
}

// 按钮：悬停音效 + 点击星星特效
const CLICKABLE = '.btn, .tab, .map-card:not(.locked), .room-row, .swatches button, .chips button, .seg:not(.locked) button, .close-x, .member-row.can, .mini';
let lastHover = null;
document.addEventListener('pointerover', (e) => {
  const el = e.target.closest(CLICKABLE);
  if (el && el !== lastHover && !el.disabled) audio.fx('hover');
  lastHover = el;
});
document.addEventListener('pointerdown', (e) => {
  const el = e.target.closest(CLICKABLE);
  if (!el || el.disabled) return;
  audio.fx('click');
  sparkBurst(e.clientX, e.clientY);
});
function sparkBurst(x, y, n = 6, colors = ['#ffb547', '#ffd27a', '#36d6ff']) {
  const layer = $('#fx-layer');
  const ring = document.createElement('i');
  ring.className = 'ring';
  ring.style.left = x + 'px';
  ring.style.top = y + 'px';
  layer.appendChild(ring);
  setTimeout(() => ring.remove(), 500);
  for (let k = 0; k < n; k++) {
    const s = document.createElement('i');
    s.className = 'spark';
    const a = (k / n) * Math.PI * 2 + Math.random() * 0.5;
    const d = 22 + Math.random() * 26;
    s.style.left = x + 'px';
    s.style.top = y + 'px';
    s.style.background = colors[k % colors.length];
    s.style.setProperty('--dx', Math.cos(a) * d + 'px');
    s.style.setProperty('--dy', Math.sin(a) * d + 'px');
    layer.appendChild(s);
    setTimeout(() => s.remove(), 650);
  }
}
document.addEventListener('contextmenu', (e) => { if (!e.target.closest('input')) e.preventDefault(); });
document.addEventListener('dragstart', (e) => e.preventDefault());

// ================= 形象选择器 =================
function avatarPicker({ canvas, skins, hats, name }, initial, onChange, level = 1, items = []) {
  const ok = (h) => hatUnlocked(h, level, items);
  const sel = { skin: initial.skin ?? Math.floor(Math.random() * SKINS.length), hat: ok(initial.hat ?? 0) ? initial.hat ?? 0 : 0 };
  const ids = [...Array(BASE_HATS).keys(), ...items.filter((i) => shopItem(i)).sort((a, b) => a - b)];
  const redraw = () => {
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawAvatar(ctx, canvas.width / 2, canvas.height * 0.58, canvas.width * 0.3, sel.skin, sel.hat);
    }
    skins.querySelectorAll('button').forEach((b, i) => b.classList.toggle('on', i === sel.skin));
    hats.querySelectorAll('button').forEach((b) => b.classList.toggle('on', +b.dataset.h === sel.hat));
    onChange?.(sel);
  };
  skins.innerHTML = SKINS.map((s, i) => `<button type="button" title="${t('skin.' + i)}" style="background:${s.color}"></button>`).join('');
  hats.innerHTML = ids.map((i) => ok(i)
    ? `<button type="button" data-h="${i}"${shopItem(i) ? ' class="shop"' : ''}>${t('hat.' + i)}</button>`
    : `<button type="button" data-h="${i}" class="locked" title="${t('lv.locked', { lv: HAT_UNLOCK[i] })}">${icon('lock')}<span>${t('hat.' + i)}</span><small>${t('lv.locked', { lv: HAT_UNLOCK[i] })}</small></button>`).join('');
  skins.querySelectorAll('button').forEach((b, i) => (b.onclick = () => { sel.skin = i; redraw(); }));
  hats.querySelectorAll('button').forEach((b) => (b.onclick = () => {
    const h = +b.dataset.h;
    if (!ok(h)) { shake(b); toast(t('lv.locked', { lv: HAT_UNLOCK[h] }), true); return; }
    sel.hat = h; redraw();
  }));
  if (name) name.value = initial.name || '';
  redraw();
  return sel;
}

// ================= 更名（在装扮里，需要消耗 1 张更名卡） =================
let renaming = false;
function renameMode(on) {
  renaming = on;
  const input = $('#profile-name');
  const cards = state.user?.renameCards ?? 0;
  input.readOnly = !on;
  input.classList.toggle('editing', on);
  if (!on) input.value = state.user?.name || '';
  $('#rename-label').textContent = t(on ? 'rename.confirmBtn' : 'rename.btn');
  $('#rename-count').textContent = on ? '' : `×${cards}`;
  $('#rename-hint').textContent = on ? t('rename.editing') : cards > 0 ? t('rename.has', { n: cards }) : t('rename.none');
  if (on) { input.focus(); input.select(); }
}
$('#btn-rename').onclick = async () => {
  const u = state.user;
  if (!u) return;
  if (!renaming) {
    if ((u.renameCards ?? 0) <= 0) {
      if (await confirmDialog(t('rename.noCard', { price: state.renameCardPrice ?? 100 }), { title: t('rename.title'), yes: t('rename.toShop') })) {
        $('#profile-modal').classList.add('hidden');
        openShop();
      }
      return;
    }
    renameMode(true);
    return;
  }
  const name = stripSpaces($('#profile-name').value);
  if (name === u.name) { renameMode(false); return; }
  const err = nameError(name);
  if (err) { shake($('#profile-name')); toast(t('err.' + err), true); return; }
  if (await confirmDialog(t('rename.confirm', { name, n: u.renameCards }), { title: t('rename.title') })) send({ t: 'rename', name });
};
$('#profile-name').addEventListener('keydown', (e) => {
  if (!renaming) return;
  if (e.key === 'Enter') $('#btn-rename').click();
  if (e.key === 'Escape') { e.stopPropagation(); renameMode(false); }
});

// ================= 装饰商店 =================
function renderShop() {
  const u = state.user;
  if (!u) return;
  $('#shop-points').textContent = u.points ?? 0;
  $('#shop-level').innerHTML = levelBadge(u.level);
  const list = $('#shop-list');
  list.innerHTML = '';
  // 道具：更名卡（可叠加购买）
  const price = state.renameCardPrice; // null = 物品不可用
  const tools = document.createElement('div');
  tools.className = 'shop-tier';
  tools.innerHTML = `<div class="shop-tier-head" style="--tc:#36d6ff">${icon('card')}<span>${t('shop.items')}</span></div>`;
  const card = document.createElement('div');
  card.className = 'shop-card tool';
  const short = Math.max(0, price - (u.points || 0));
  card.innerHTML = `<div class="tool-ic">${icon('card')}</div><div class="nm">${t('item.rename')}</div>
    <p class="desc">${t('item.renameDesc')}</p>
    <div class="pr">${priceTag(price)}<span class="own">${t('shop.ownedCount', { n: u.renameCards ?? 0 })}</span></div>
    ${price == null ? unavailableBtn() : short > 0 ? `<button class="btn btn-gray" disabled>${t('shop.short', { n: short })}</button>` : `<button class="btn btn-yellow" data-act="buy">${t('shop.buy')}</button>`}`;
  card.querySelector('[data-act="buy"]')?.addEventListener('click', async () => {
    if (await confirmDialog(t('shop.confirm', { price, name: t('item.rename') }), { title: t('shop.title') })) send({ t: 'buy', item: 'rename' });
  });
  const row0 = document.createElement('div');
  row0.className = 'shop-row';
  row0.appendChild(card);
  tools.appendChild(row0);
  list.appendChild(tools);
  list.appendChild(boostShopSection(u));
  list.appendChild(bombShopSection(u));
  const groups = new Map();
  for (const it of shopItems()) (groups.get(it.level) || groups.set(it.level, []).get(it.level)).push(it);
  for (const [lv, items] of groups) {
    const unlocked = u.level >= lv;
    const sec = document.createElement('div');
    sec.className = 'shop-tier' + (unlocked ? '' : ' locked');
    sec.innerHTML = `<div class="shop-tier-head" style="--tc:${tierOf(lv).color}">${unlocked ? '' : icon('lock')}${levelBadge(lv)}<span>${t('shop.tier', { lv })}</span></div>`;
    const row = document.createElement('div');
    row.className = 'shop-row';
    for (const it of items) {
      const owned = (u.items || []).includes(it.id);
      const equipped = u.hat === it.id;
      const card = document.createElement('div');
      card.className = 'shop-card' + (owned ? ' owned' : '') + (equipped ? ' equipped' : '');
      const cv = document.createElement('canvas');
      cv.width = cv.height = 150;
      const ctx = cv.getContext('2d');
      drawAvatar(ctx, 75, 92, 40, u.skin, it.id);
      card.appendChild(cv);
      const short = Math.max(0, it.price - (u.points || 0));
      let action;
      if (equipped) action = `<button class="btn btn-gray" disabled>${icon('check')}${t('shop.equipped')}</button>`;
      else if (owned) action = `<button class="btn btn-blue" data-act="equip">${t('shop.equip')}</button>`;
      else if (!unlocked) action = `<button class="btn btn-gray" disabled>${icon('lock')}${t('shop.need', { lv })}</button>`;
      else if (short > 0) action = `<button class="btn btn-gray" disabled>${t('shop.short', { n: short })}</button>`;
      else action = `<button class="btn btn-yellow" data-act="buy">${t('shop.buy')}</button>`;
      card.insertAdjacentHTML('beforeend', `<div class="nm">${esc(t('hat.' + it.id))}</div>
        <div class="pr">${owned ? `<span class="own">${t('shop.owned')}</span>` : `${icon('gem')}${t('shop.price', { n: it.price })}`}</div>${action}`);
      card.querySelector('[data-act="buy"]')?.addEventListener('click', async () => {
        const name = t('hat.' + it.id);
        if (await confirmDialog(t('shop.confirm', { price: it.price, name }), { title: t('shop.title') })) send({ t: 'buy', item: it.id });
      });
      card.querySelector('[data-act="equip"]')?.addEventListener('click', () => send({ t: 'profile', hat: it.id }));
      row.appendChild(card);
    }
    sec.appendChild(row);
    list.appendChild(sec);
  }
}
/** 商店：炸弹特效（纯画面；同一时间只有一种，再买会覆盖之前的）。价格与天数来自 store_item.json，price 为 null 表示物品不可用 */
function bombShopSection(u) {
  const shop = state.bombShop || { styles: [] };
  const cur = u.bomb?.style || '';
  const days0 = shop.styles.find((x) => x.days)?.days ?? 7;
  const sec = document.createElement('div');
  sec.className = 'shop-tier';
  sec.innerHTML = `<div class="shop-tier-head" style="--tc:#b14dff">${icon('bomb')}<span>${t('bomb.section')}</span></div><p class="shop-note">${t('bomb.note', { days: days0 })}</p>`;
  const row = document.createElement('div');
  row.className = 'shop-row';
  for (const { id: st, price, days } of shop.styles) {
    const active = cur === st;
    const card = document.createElement('div');
    card.className = 'shop-card bomb-card' + (active ? ' equipped' : '') + (price == null ? ' unavailable' : '');
    card.appendChild(bombPreview(st));
    const short = Math.max(0, (price ?? 0) - (u.points || 0));
    const left = active ? timeLeft(u.bomb.until) : '';
    const btn = price == null ? unavailableBtn()
      : short > 0 ? `<button class="btn btn-gray" disabled>${t('shop.short', { n: short })}</button>`
      : `<button class="btn ${active ? 'btn-blue' : 'btn-yellow'}" data-act="buy">${active ? t('bomb.renew', { n: days }) : t('shop.buy')}</button>`;
    card.insertAdjacentHTML('beforeend', `<div class="nm">${esc(t('bomb.' + st))}</div>
      <p class="desc">${esc(t('bomb.' + st + 'Desc'))}</p>
      <div class="pr">${priceTag(price)}<span class="own">${active ? esc(t('bomb.left', { t: left })) : price == null ? '' : esc(t('bomb.days', { n: days }))}</span></div>
      ${btn}`);
    card.querySelector('[data-act="buy"]')?.addEventListener('click', async () => {
      const name = t('bomb.' + st);
      let msg = t('bomb.confirm', { price, name, days });
      if (active) msg = t('bomb.confirmRenew', { price, name, days, t: timeLeft(u.bomb.until) });
      else if (cur) msg = t('bomb.confirmReplace', { price, name, days, old: t('bomb.' + cur), t: timeLeft(u.bomb.until) });
      if (await confirmDialog(msg, { title: t('shop.title') })) send({ t: 'buy', item: st });
    });
    row.appendChild(card);
  }
  sec.appendChild(row);
  return sec;
}

/** 商店左边：生效中的加成卡（经验卡 / 点数卡各一个图标 + 倍率），悬停显示剩余时间；都没有时隐藏 */
function renderBoostPill() {
  const el = $('#boost-pill');
  const boosts = state.user?.boosts || {};
  const now = Date.now();
  const parts = [], tips = [];
  for (const kind of ['exp', 'points']) {
    const b = boosts[kind];
    if (!b || b.until <= now) continue;
    const name = t(kind === 'exp' ? 'boost.exp' : 'boost.points', { x: b.pct / 100 });
    parts.push(`<span class="bk ${kind}">${icon(kind === 'exp' ? 'star' : 'gem')}<b>×${b.pct / 100}</b></span>`);
    tips.push(`<div class="${kind}">${icon(kind === 'exp' ? 'star' : 'gem')}<span>${esc(name)}</span><b>${esc(t('boost.left', { t: timeLeft(b.until) }))}</b></div>`);
  }
  el.classList.toggle('hidden', !parts.length);
  // 悬停浮层：立即显示每张卡的剩余时间（不用浏览器自带的 title，那个要等一秒多才出现）
  el.innerHTML = parts.join('') + (tips.length ? `<div class="boost-tip">${tips.join('')}</div>` : '');
}

/** 购买成功提示里的商品名：加成卡 / 炸弹特效 / 头饰 */
function boughtName(item) {
  const card = state.boostShop?.cards?.find((c) => c.id === item);
  if (card) return t(card.kind === 'exp' ? 'boost.exp' : 'boost.points', { x: card.pct / 100 });
  return t((BOMB_FX[item] ? 'bomb.' : 'hat.') + item);
}

/** 价格标签；price 为 null（物品不可用）时显示「—」 */
function priceTag(price) {
  return price == null ? `<span class="na">—</span>` : `${icon('gem')}${t('shop.price', { n: price })}`;
}
function unavailableBtn() {
  return `<button class="btn btn-gray" disabled>${t('shop.unavailable')}</button>`;
}

/** 商店：加成卡（经验 / 点数 ×1.5 / ×2 / ×3）。经验与点数各一个位置：同倍率顺延，不同倍率替换。
 *  价格与时长来自 store_item.json，price 为 null 表示物品不可用 */
function boostShopSection(u) {
  const shop = state.boostShop || { cards: [] };
  const h0 = shop.cards.find((c) => c.hours)?.hours ?? 24;
  const sec = document.createElement('div');
  sec.className = 'shop-tier';
  sec.innerHTML = `<div class="shop-tier-head" style="--tc:#3ee08f">${icon('star')}<span>${t('boost.section')}</span></div><p class="shop-note">${t('boost.note', { h: h0 })}</p>`;
  // 经验卡一排、点数卡一排
  const rows = {};
  for (const c of shop.cards) {
    const row = rows[c.kind] || (rows[c.kind] = sec.appendChild(Object.assign(document.createElement('div'), { className: 'shop-row' })));
    const cur = u.boosts?.[c.kind];
    const active = cur?.pct === c.pct;
    const lower = !!cur && cur.pct > c.pct; // 已有更高倍率生效中：不能买低倍率
    const mult = c.pct / 100;
    const h = c.hours;
    const name = t(c.kind === 'exp' ? 'boost.exp' : 'boost.points', { x: mult });
    const card = document.createElement('div');
    card.className = 'shop-card tool boost-card ' + c.kind + (active ? ' equipped' : '') + (c.price == null ? ' unavailable' : '');
    const short = Math.max(0, (c.price ?? 0) - (u.points || 0));
    const btn = c.price == null ? unavailableBtn()
      : lower ? `<span class="btn-tip" data-tip="${esc(t('boost.activeName', { name: t(c.kind === 'exp' ? 'boost.exp' : 'boost.points', { x: cur.pct / 100 }) }))}"><button class="btn btn-gray" disabled>${t('shop.buy')}</button></span>`
      : short > 0 ? `<button class="btn btn-gray" disabled>${t('shop.short', { n: short })}</button>`
      : `<button class="btn ${active ? 'btn-blue' : 'btn-yellow'}" data-act="buy">${t(active ? 'boost.extend' : 'shop.buy', { h })}</button>`;
    card.innerHTML = `<div class="tool-ic">${icon(c.kind === 'exp' ? 'star' : 'gem')}<b>×${mult}</b></div><div class="nm">${esc(name)}</div>
      <p class="desc">${esc(t(c.kind === 'exp' ? 'boost.expDesc' : 'boost.pointsDesc', { x: mult, h: h ?? h0 }))}</p>
      <div class="pr">${priceTag(c.price)}<span class="own">${active ? esc(t('bomb.left', { t: timeLeft(cur.until) })) : c.price == null ? '' : esc(t('boost.hours', { n: h }))}</span></div>
      ${btn}`;
    card.querySelector('[data-act="buy"]')?.addEventListener('click', async () => {
      let msg = t('boost.confirm', { price: c.price, name, h });
      if (active) msg = t('boost.confirmExtend', { price: c.price, name, h, t: timeLeft(cur.until) });
      else if (cur) msg = t('boost.confirmReplace', { price: c.price, name, h, old: t(c.kind === 'exp' ? 'boost.exp' : 'boost.points', { x: cur.pct / 100 }), t: timeLeft(cur.until) });
      if (await confirmDialog(msg, { title: t('shop.title') })) send({ t: 'buy', item: c.id });
    });
    row.appendChild(card);
  }
  return sec;
}

/** 结算：点数加成明细（连杀 / 复活赛排名 / 点数卡，百分比直接相加；失败时显示随机浮动） */
function bonusLine(me) {
  const parts = [];
  if (me.lossPct) parts.push(t('bonus.loss', { n: me.lossPct }));
  const b = me.bonus || {};
  if (b.streak) parts.push(t('bonus.streak', { n: b.streak }));
  if (b.rank) parts.push(t('bonus.rank', { n: b.rank }));
  if (b.card) parts.push(t('bonus.card', { n: b.card }));
  if (!parts.length) return '';
  return `<div class="rw-bonus">${icon('gem')} ${parts.map(esc).join(' · ')}${me.pointsPct ? ` = <b>${me.pointsPct}%</b>` : ''}</div>`;
}

/** 剩余时间：X 天 Y 小时 / Y 小时 Z 分 */
function timeLeft(until) {
  const ms = Math.max(0, (until || 0) - Date.now());
  const d = Math.floor(ms / 86400000), h = Math.floor((ms % 86400000) / 3600000), m = Math.floor((ms % 3600000) / 60000);
  return d > 0 ? t('time.dh', { d, h }) : t('time.hm', { h, m });
}

/** 炸弹特效预览（2D 画布） */
function bombPreview(style) {
  const fx = BOMB_FX[style];
  const cv = document.createElement('canvas');
  cv.width = cv.height = 150;
  const g = cv.getContext('2d');
  const halo = g.createRadialGradient(75, 82, 10, 75, 82, 72);
  halo.addColorStop(0, fx.glow + 'aa');
  halo.addColorStop(1, fx.glow + '00');
  g.fillStyle = halo;
  g.fillRect(0, 0, 150, 150);
  // 特效点缀
  g.fillStyle = fx.parts[1];
  for (let k = 0; k < 14; k++) {
    const a = (k / 14) * Math.PI * 2, r = 46 + (k % 3) * 9;
    g.globalAlpha = 0.35 + (k % 4) * 0.15;
    g.beginPath();
    if (style === 'water') g.ellipse(75 + Math.cos(a) * r, 92 + Math.sin(a) * r * 0.35, 3, 2, 0, 0, Math.PI * 2);
    else g.arc(75 + Math.cos(a) * r * 0.8, 70 + Math.sin(a) * r * 0.7, style === 'poison' ? 6 + (k % 3) * 3 : 2 + (k % 2), 0, Math.PI * 2);
    g.fill();
  }
  g.globalAlpha = 1;
  // 炸弹本体
  const body = g.createRadialGradient(64, 72, 4, 75, 86, 34);
  body.addColorStop(0, '#ffffff');
  body.addColorStop(0.18, fx.inner);
  body.addColorStop(0.55, fx.body);
  body.addColorStop(1, '#0b0b12');
  g.fillStyle = body;
  g.beginPath(); g.arc(75, 86, 32, 0, Math.PI * 2); g.fill();
  g.strokeStyle = fx.glow; g.lineWidth = 3;
  g.beginPath(); g.ellipse(75, 86, 32, 8, 0, 0, Math.PI * 2); g.stroke();
  g.fillStyle = '#8a909c'; g.fillRect(68, 50, 14, 8);
  g.strokeStyle = '#444'; g.lineWidth = 2;
  g.beginPath(); g.moveTo(78, 50); g.quadraticCurveTo(84, 40, 92, 38); g.stroke();
  const sp = g.createRadialGradient(93, 37, 0, 93, 37, 9);
  sp.addColorStop(0, '#fff'); sp.addColorStop(0.4, fx.glow); sp.addColorStop(1, fx.glow + '00');
  g.fillStyle = sp; g.beginPath(); g.arc(93, 37, 9, 0, Math.PI * 2); g.fill();
  return cv;
}

function openShop() {
  renderShop();
  openModal('#shop-modal');
}
$('#points-pill').onclick = openShop;
$('#boost-pill').onclick = openShop;
$('#boost-pill').addEventListener('mouseenter', renderBoostPill); // 悬停时刷新一次剩余时间
setInterval(renderBoostPill, 30000); // 到期后自动消失、剩余时间随之更新
$('#btn-profile-shop').onclick = () => { $('#profile-modal').classList.add('hidden'); openShop(); };

// ================= 启动 / 登录 =================
const loginSkin = Math.floor(Math.random() * SKINS.length); // 登录页展示用的角色颜色
let charSel = null;

// ================= 创建角色（新账号首次登录） =================
function openCreateCharacter() {
  const u = state.user;
  charSel = avatarPicker(
    { skins: $('#char-skins'), hats: $('#char-hats'), name: $('#char-name') },
    { name: '', skin: u.skin, hat: 0 },
    (sel) => { if (state.screen === 'create') stage?.showLogin(sel.skin, sel.hat); },
    u.level ?? 1,
    u.items || [],
  );
  show('create');
  setTimeout(() => $('#char-name').focus(), 450);
}
/** 名字：去掉空格后长度必须大于 0；只允许中文 / 英文字母 / 数字，最多 8 个字（最终以服务器校验为准） */
function nameError(raw) {
  const name = stripSpaces(raw);
  if (name.length === 0) return 'name_invalid';
  if ([...name].length > 8) return 'name_too_long';
  if (cleanText(name) === null) return 'name_chars';
  return null;
}
$('#btn-create-char').onclick = () => {
  const name = stripSpaces($('#char-name').value);
  const err = nameError(name);
  if (err) { shake($('#char-name')); toast(t('err.' + err), true); return; }
  send({ t: 'createCharacter', name, skin: charSel.skin, hat: charSel.hat });
};
$('#char-name').addEventListener('keydown', (e) => e.key === 'Enter' && $('#btn-create-char').click());

/** 登录成功（收到 welcome）后：没有角色 → 创建角色；否则 → 大厅 */
function enterAfterLogin() {
  if (!state.user.hasCharacter) {
    if (state.screen !== 'create') openCreateCharacter();
  } else if (state.screen === 'login' || state.screen === 'create') {
    show('lobby');
  }
}

async function boot() {
  hydrateIcons();
  try {
    stage = new MenuStage($('#stage'));
  } catch (e) {
    console.warn('3D 舞台初始化失败', e);
  }
  $('#btn-guest').onclick = () => {
    audio.unlock();
    // 新建游客账号（之后进入创建角色流程）；老游客用 8 位 ID 登录
    doLogin(() => guestLogin({ lang: getLang() }));
  };
  $('#btn-id-login').onclick = () => {
    audio.unlock();
    const id = $('#login-id').value.trim();
    if (!/^\d{8}$/.test(id)) {
      toast(t('id.badDigits'), true);
      shake($('#login-id'));
      return;
    }
    doLogin(() => idLogin(id, getLang()));
  };
  $('#login-id').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, '').slice(0, 8); });
  $('#login-id').addEventListener('keydown', (e) => e.key === 'Enter' && $('#btn-id-login').click());
  document.addEventListener('pointerdown', () => audio.unlock(), { once: true });
  document.addEventListener('keydown', () => audio.unlock(), { once: true });

  // 进入登录页时请求 /login-info：LOGIN_GITHUB → 只显示 GitHub 登录；LOGIN_GUEST → 只显示 8 位 ID 输入框和游客登录
  let cfg = { guest: false, github: false };
  try { cfg = await fetchLoginConfig(); } catch {
    const n = $('#login-notice');
    n.classList.remove('hidden');
    n.textContent = t('err.network');
  }
  state.loginCfg = cfg;
  // 版本号（服务器 backend/__init__.py 的 VERSION）：登录页与大厅右上角
  for (const el of [$('#ver-login'), $('#ver-lobby')]) el.textContent = cfg.version ? 'v' + cfg.version : '';
  $('#github-block').classList.toggle('hidden', !cfg.github);
  $('#guest-block').classList.toggle('hidden', !cfg.guest);
  $('#login-split').classList.toggle('hidden', !(cfg.guest && cfg.github));
  $('#btn-github').onclick = () => { audio.unlock(); location.href = '/auth/github?lang=' + encodeURIComponent(wireLang(getLang())); };

  // GitHub 回跳：#oauth=<一次性交换码> 或 #oauth_error=<原因>
  const hash = new URLSearchParams(location.hash.slice(1));
  const oauthCode = hash.get('oauth');
  const oauthErr = hash.get('oauth_error');
  if (oauthCode || oauthErr) history.replaceState(null, '', location.pathname);

  // 不自动登录：上次的 8 位游客 ID 只填回输入框，仍需玩家自己点登录
  if (cfg.guest) $('#login-id').value = savedId();
  if (oauthCode) {
    $('#login-loading').classList.remove('hidden');
    $('#login-form').classList.add('hidden');
  }
  show('login', true);
  setTimeout(() => $('#boot').classList.add('done'), 900);
  setTimeout(() => $('#boot').remove(), 1500);
  if (oauthErr) {
    const n = $('#login-notice');
    n.classList.remove('hidden');
    n.textContent = t('oauth.' + (['denied', 'state', 'disabled'].includes(oauthErr) ? oauthErr : 'github'));
  }
  if (oauthCode) await doLogin(() => oauthExchange(oauthCode), true); // 刚刚点了 GitHub 登录并完成授权
}

function shake(el) {
  el.classList.remove('shake');
  void el.offsetWidth;
  el.classList.add('shake');
}

/** 错误码 → 当前语言的提示 */
function errText(e) {
  const code = e instanceof ApiError ? e.code : e?.code || 'unknown';
  const key = 'err.' + code;
  const s = t(key, e?.params);
  return s === key ? t('err.unknown') : s;
}

/** 登录页回到可操作状态：隐藏「正在恢复你的账号…」、显示登录表单。
 *  GitHub 回跳时会先隐藏表单显示转圈；无论之后成功还是失败都要还原，
 *  否则以后回到登录页（会话过期 / 服务器重启 / 被顶号）就只剩一个转圈，卡住不动。 */
function resetLoginForm(notice) {
  $('#login-loading').classList.add('hidden');
  $('#login-form').classList.remove('hidden');
  const n = $('#login-notice');
  n.classList.toggle('hidden', !notice);
  if (notice) n.textContent = notice;
}

/** 登录成功后等待连接建立的时间；超时（还停在登录页）就断开并提示，而不是无限等待 */
const CONNECT_WAIT_MS = 12000;

async function doLogin(fn, auto = false) {
  const btns = [$('#btn-guest'), $('#btn-id-login')];
  btns.forEach((b) => (b.disabled = true));
  try {
    const data = await fn();
    state.user = data.user;
    adoptAccountLang(data.user);
    resetLoginForm();
    showIdModal(data.user, data.created);
    startConnection(data);
  } catch (e) {
    resetLoginForm();
    let text = errText(e);
    if (e instanceof UnknownIdError) shake($('#login-id'));
    const n = $('#login-notice');
    n.classList.remove('hidden');
    n.textContent = text;
    if (!auto) toast(text, true);
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

function showIdModal(user, created) {
  $('#id-title').textContent = t(created ? 'id.created' : 'id.welcome');
  $('#id-name').textContent = `${user.name} · LV.${user.level}` + (user.provider === 'github' ? '  ·  GitHub' : '');
  $('#id-value').textContent = user.id;
  $('#id-tip').textContent = t(user.provider === 'github' ? 'id.tipGithub' : created ? 'id.tipCreated' : 'id.tipBack');
  const cv = $('#id-avatar');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  drawAvatar(ctx, cv.width / 2, cv.height * 0.55, cv.width * 0.32, user.skin, user.hat);
  openModal('#id-modal');
  audio.fx(created ? 'win' : 'coin');
}
$('#btn-id-ok').onclick = () => $('#id-modal').classList.add('hidden');
$('#btn-copy-id').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('#id-value').textContent);
    toast(t('id.copied'));
  } catch {
    toast(t('id.copyFail'), true);
  }
};

/** 重连状态：显示遮罩并冻结本地操作；重连成功后一切以服务器下发的状态为准 */
function setReconnecting(on, attempt = 0) {
  state.reconnecting = on;
  const el = $('#reconnect');
  el.classList.toggle('hidden', !on);
  if (on) $('#reconnect-text').textContent = t('conn.reconnecting', { n: attempt + 1 });
  if (on) input.reset();
  if (scene) scene.frozen = on;
}

/** 结束会话：关闭 WebSocket（不再重连）、清掉等待计时、隐藏重连遮罩。
 *  WebSocket 只在登录成功后建立；回到登录页（退出 / 会话失效 / 连不上）时一定先调用这里。 */
function endSession() {
  clearTimeout(state.connWait);
  state.conn?.close();
  state.conn = null;
  setReconnecting(false);
}

function startConnection(login) {
  endSession();
  // 还在登录页时迟迟连不上（服务器不可用 / 被拦截）：回到登录表单并提示，而不是一直在后台静默重连
  state.connWait = setTimeout(() => {
    if (state.screen !== 'login' || state.conn?.online) return;
    endSession();
    $('#id-modal').classList.add('hidden');
    resetLoginForm(t('err.network'));
  }, CONNECT_WAIT_MS);
  const conn = new Connection(login, {
    open: () => {
      if (state.conn !== conn) return;
      clearTimeout(state.connWait);
      setReconnecting(false);
      if (state.pendingLang) {
        send({ t: 'profile', lang: state.pendingLang });
        state.pendingLang = null;
      }
    },
    message: onMessage,
    close: (code, attempt) => {
      if (state.conn !== conn) return; // 已被替换 / 已结束的旧连接
      if (code === 4001) {
        // 会话失效（服务器重启 / 过期）：结束会话，回到可操作的登录页
        endSession();
        $('#id-modal').classList.add('hidden');
        resetLoginForm(t('conn.expired'));
        if (state.loginCfg?.guest) $('#login-id').value = savedId();
        toast(t('conn.expired'), true);
        show('login');
      } else if (code === 4000) {
        // 被别处登录顶掉：不再重连
        endSession();
        if (state.screen === 'login') resetLoginForm(t('conn.replaced'));
        toast(t('conn.replaced'), true);
      } else if (state.screen !== 'login') {
        setReconnecting(true, attempt);
      }
    },
  });
  state.conn = conn;
}

const send = (msg) => state.conn?.send(msg);

// ================= 消息 =================
function onMessage(m) {
  switch (m.t) {
    case 'welcome':
      state.user = m.user;
      adoptAccountLang(m.user);
      state.maps = m.maps;
      setLevelTable(m.levels);
      setShop(m.shop);
      state.renameCardPrice = m.renameCardPrice;
      state.bombShop = m.bombShop;
      state.boostShop = m.boostShop;
      renderMe();
      if (!m.roomId) {
        // 服务器说我们不在任何房间（例如断线期间对局已结束）：以服务器为准离开房间 / 对局界面
        state.room = null;
        state.inRoom = false;
        if (state.screen === 'room' || state.screen === 'game') { state.game = null; show('lobby'); }
      }
      if (!m.roomId || !m.user.hasCharacter) enterAfterLogin();
      else if (!m.inGame && (state.screen === 'login' || state.screen === 'create')) show('room');
      loadLeaderboard();
      break;
    case 'me':
      if (state.screen === 'create' && m.user.hasCharacter) {
        state.user = m.user;
        renderMe();
        audio.fx('win');
        toast(t('char.done', { name: m.user.name }));
        show('lobby');
        break;
      }
      state.user = m.user;
      renderMe();
      if (!$('#shop-modal').classList.contains('hidden')) renderShop();
      if (!$('#profile-modal').classList.contains('hidden')) renameMode(false);
      break;
    case 'bought':
      audio.fx('coin');
      toast(m.item === 'rename' ? t('shop.boughtCard') : t('shop.bought', { name: boughtName(m.item) }));
      break;
    case 'leaderboard':
      renderLeaderboard(m.list || []);
      break;
    case 'renamed':
      audio.fx('coin');
      toast(t('rename.done', { name: m.name }));
      break;
    case 'lobby':
      state.lobby = m;
      $('#online-pill b').textContent = m.online;
      if (state.screen === 'room' || (state.screen === 'game' && !state.room)) show('lobby');
      if (state.room && !state.inRoom) state.room = null;
      renderRooms();
      break;
    case 'room':
      $('#pw-modal').classList.add('hidden');
      state.room = m.room;
      state.inRoom = true;
      // 对局进行中（重连 / 重新登录）：不切到房间界面，等服务器下发对局状态直接回到游戏
      if (m.room.state !== 'playing' && (state.screen === 'lobby' || state.screen === 'login' || state.screen === 'create')) {
        $('#room-chat').innerHTML = '';
        show('room');
      } else if (state.screen === 'game' && m.room.state === 'waiting' && !state.resultShown) {
        // 断线期间对局已经结束：回到房间
        state.game = null;
        show('room');
      }
      renderRoom();
      break;
    case 'start':
      startGame(m);
      break;
    case 's':
      onSnapshot(m);
      break;
    case 'end':
      showResult(m.result);
      break;
    case 'chat':
      addChat(m);
      break;
    case 'chatlog':
      $('#lobby-chat').innerHTML = '';
      m.list.forEach(addChat);
      break;
    case 'kicked':
      state.room = null;
      state.inRoom = false;
      toast(t('room.kicked'), true);
      show('lobby');
      break;
    case 'error':
      if (m.code === 'room_password') { askRoomPassword(m.params?.id); break; }
      if (m.code === 'room_password_wrong') shake($('#join-password'));
      toast(errText(m), true);
      break;
    case 'warn':
      // 服务器多次发现异常移动 / 异常放炸弹间隔
      toast(t('warn.' + m.code), true);
      break;
    case 'history':
      renderHistory(m.list || []);
      break;
    case 'presence':
      // 对局中有玩家断线 / 重连：全场广播
      if (state.screen === 'game' && state.game && m.id !== state.user.id) {
        const p = state.game.players.find((x) => x.id === m.id);
        broadcastBanner(p || { name: m.name, skin: 0, hat: 0 }, m.on);
        document.getElementById('hp-' + m.id)?.classList.toggle('offline', !m.on);
      }
      break;
    default:
      break;
  }
}

// ================= 大厅 =================
let lastCoins = null;
function renderMe() {
  const u = state.user;
  if (!u) return;
  const box = $('#lobby-me');
  box.innerHTML = '';
  box.appendChild(avatarEl(u, 31));
  const pct = levelProgress(u.exp) * 100;
  const tier = tierOf(u.level);
  const lo = levelFloor(u.level), hi = levelCeil(u.level);
  const expText = hi == null ? 'MAX' : t('lv.exp', { cur: u.exp - lo, need: hi - lo });
  const info = document.createElement('div');
  info.innerHTML = `<div class="nm">${esc(u.name)}${levelBadge(u.level)}<span class="tier" style="--tc:${tier.color}">${t('tier.' + tier.index)}</span></div>
    <div class="expbar" style="--tc:${tier.color}" title="${hi == null ? '' : t('lv.toNext', { lv: u.level + 1, n: hi - u.exp })}"><i style="width:${pct}%"></i><em>${expText}</em></div>
    <div class="uid">${u.provider === 'github' ? `${icon('github')} · ` : ''}ID ${esc(u.id)} · ${u.stats.wins}W / ${u.stats.games}G</div>`;
  box.appendChild(info);
  const pill = $('#points-pill');
  pill.querySelector('b').textContent = u.points ?? 0;
  if (lastCoins !== null && u.points > lastCoins) {
    pill.classList.remove('bump'); void pill.offsetWidth; pill.classList.add('bump');
    audio.fx('coin');
  }
  lastCoins = u.points;
  renderBoostPill();
  if (state.screen === 'lobby' || state.screen === 'room') stage?.setBombStyle(u.skin, u.bomb?.style); // 买了炸弹特效 / 换颜色后立即更新
  if (state.screen === 'lobby') stage?.showLobby(u);
}

function mapName(id) {
  if (id === 'random') return t('map.random');
  return mapText(state.maps.find((m) => m.id === id), 'name') || id;
}

$$('#lobby-tabs .tab').forEach((t) => (t.onclick = () => {
  $$('#lobby-tabs .tab').forEach((x) => x.classList.toggle('on', x === t));
  $$('.lobby-panel .tab-body').forEach((b) => b.classList.toggle('hidden', b.dataset.tab !== t.dataset.tab));
  if (t.dataset.tab === 'rank') loadLeaderboard();
}));

function renderRooms() {
  const list = $('#room-list');
  const rooms = state.lobby.rooms || [];
  if (!rooms.length) {
    list.innerHTML = `<div class="empty">${icon('map')}${t('rooms.empty')}</div>`;
    return;
  }
  list.innerHTML = '';
  rooms.forEach((r, i) => {
    const row = document.createElement('div');
    row.className = 'room-row';
    row.style.animationDelay = i * 0.04 + 's';
    const map = state.maps.find((m) => m.id === r.mapId);
    const cv = document.createElement('canvas');
    cv.width = 300; cv.height = 260;
    if (map) drawMapPreview(cv, map);
    else {
      const c = cv.getContext('2d');
      c.fillStyle = '#121722'; c.fillRect(0, 0, 300, 260);
      drawIcon(c, 'dice', 150, 130, 110, '#8a93a8', 1.6);
    }
    row.appendChild(cv);
    const full = r.players >= MAX_PLAYERS;
    const mid = document.createElement('div');
    mid.innerHTML = `<div class="name">${esc(r.name)}</div>
      <div class="meta"><span class="tag ${r.state}">${r.state === 'playing' ? 'LIVE' : 'OPEN'}</span>
      <span>${esc(mapName(r.mapId))}</span><span>${t(r.mode === 'team' ? 'mode.teamShort' : 'mode.ffaShort')}</span>
      <span>${icon('users')} ${r.players}/${MAX_PLAYERS}</span></div>`;
    row.appendChild(mid);
    const btn = document.createElement('button');
    btn.className = 'btn btn-green btn-small';
    btn.textContent = t(r.state === 'playing' ? 'rooms.playing' : full ? 'rooms.full' : 'rooms.join');
    btn.disabled = r.state === 'playing' || full;
    const join = () => { if (!btn.disabled) (r.locked ? askRoomPassword(r.id) : send({ t: 'joinRoom', id: r.id })); };
    if (r.locked) mid.querySelector('.name').insertAdjacentHTML('afterbegin', `<span class="lock">${icon('lock')}</span>`);
    btn.onclick = (e) => { e.stopPropagation(); join(); };
    row.onclick = join;
    row.appendChild(btn);
    list.appendChild(row);
  });
}

// 排行榜也走加密的 WebSocket
function loadLeaderboard() { send({ t: 'leaderboard' }); }
function renderLeaderboard(list) {
  {
    const ol = $('#leaderboard');
    ol.innerHTML = list.length ? '' : `<div class="empty">${icon('trophy')}${t('rank.empty')}</div>`;
    list.forEach((u, i) => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="rank">${i + 1}</span>`;
      li.appendChild(avatarEl(u, 32));
      li.insertAdjacentHTML('beforeend', `<span>${esc(u.name)}</span>${levelBadge(u.level)}<span class="score">${t('rank.score', { wins: u.stats.wins, kills: u.stats.kills })}</span>`);
      ol.appendChild(li);
    });
  }
}

function mapPicker(root, selected, onPick, locked = false) {
  root.innerHTML = '';
  for (const id of [...state.maps.map((m) => m.id), 'random']) {
    const card = document.createElement('div');
    card.className = 'map-card' + (id === selected ? ' on' : '') + (locked ? ' locked' : '');
    if (id === 'random') {
      card.innerHTML = `<div class="rand">${icon('dice')}</div><div>${t('map.random')}</div>`;
    } else {
      const cv = document.createElement('canvas');
      cv.width = 300; cv.height = 260;
      drawMapPreview(cv, state.maps.find((m) => m.id === id));
      card.appendChild(cv);
      card.insertAdjacentHTML('beforeend', `<div>${esc(mapName(id))}</div>`);
    }
    if (!locked) card.onclick = () => onPick(id);
    root.appendChild(card);
  }
  const desc = document.createElement('div');
  desc.className = 'map-desc';
  desc.style.gridColumn = '1 / -1';
  const m = state.maps.find((x) => x.id === selected);
  desc.textContent = m ? mapText(m, 'desc') : t('map.randomDesc');
  root.appendChild(desc);
}

function segPicker(root, value, onPick, locked = false) {
  root.classList.toggle('locked', locked);
  root.querySelectorAll('button').forEach((b) => {
    b.classList.toggle('on', b.dataset.v === String(value));
    b.onclick = locked ? null : () => onPick(b.dataset.v);
  });
}

const createSel = { mapId: 'meadow', mode: 'ffa', items: true, shrink: true, time: 10, revive: false };
function openCreate() {
  $('#create-name').value = cleanText(t('room.defaultName', { name: state.user.name })) ?? '';
  $('#create-password').value = '';
  const draw = () => {
    mapPicker($('#create-maps'), createSel.mapId, (id) => { createSel.mapId = id; draw(); });
    segPicker($('#create-mode'), createSel.mode, (v) => { createSel.mode = v; draw(); });
    segPicker($('#create-items'), createSel.items ? '1' : '0', (v) => { createSel.items = v === '1'; draw(); });
    segPicker($('#create-revive'), createSel.revive ? '1' : '0', (v) => { createSel.revive = v === '1'; draw(); });
    segPicker($('#create-shrink'), createSel.shrink && !createSel.revive ? '1' : '0', (v) => { createSel.shrink = v === '1'; draw(); }, createSel.revive);
    segPicker($('#create-time'), String(createSel.time), (v) => { createSel.time = Number(v); draw(); });
  };
  draw();
  openModal('#create-modal');
}

// ================= 房间 =================
function renderRoom() {
  const r = state.room;
  if (!r) return;
  const me = state.user.id;
  const isHost = r.hostId === me;
  const team = r.settings.mode === 'team';
  const waiting = r.state === 'waiting';
  $('#room-name').textContent = r.name;
  $('#room-pw').classList.toggle('hidden', !r.password);
  $('#room-pw').innerHTML = r.password ? `${icon('lock')}${esc(r.password)}` : '';
  $('#room-id').textContent = '#' + r.id;
  const humans = r.members.filter((m) => !m.isBot).length;
  const bots = r.members.length - humans;
  $('#room-count').textContent = `${r.members.length}/${MAX_PLAYERS}`;
  if (state.screen === 'room') stage?.showRoom(localizedRoom(r), me);

  const list = $('#slots');
  list.innerHTML = '';
  for (let i = 0; i < MAX_PLAYERS; i++) {
    const m = r.members[i];
    const el = document.createElement('div');
    if (!m) {
      const can = isHost && waiting && bots < r.botLimit;
      el.className = 'member-row empty-slot' + (can ? ' can' : '');
      el.innerHTML = can ? `${icon('plus')} ${t('room.addAi')}` : t('room.empty');
      if (can) el.onclick = addNormalBot;
      list.appendChild(el);
      continue;
    }
    el.className = `member-row${m.id === me ? ' me' : ''}${team ? ' team' + m.team : ''}`;
    el.appendChild(avatarEl(m, 17));
    const status = m.id === r.hostId ? `${icon('crown')}${t('room.host')}` : m.isBot ? `${icon('bot')}${t('room.bot')}` : m.ready ? `${icon('check')}${t('room.isReady')}` : t('room.notReady');
    el.insertAdjacentHTML('beforeend', `<div class="nm"><div class="nmt">${esc(displayName(m.name, m.isBot))}${m.level ? levelBadge(m.level) : ''}</div><div class="st ${m.ready || m.isBot ? 'ready' : ''}">${status}${m.connected ? '' : ` · <span class="off">${t('room.offline')}</span>`}</div></div>`);
    if (m.isBot) {
      // AI 难度：房主可点击修改（形象随难度一起换）
      const lv = AI_LEVELS.includes(m.ai) ? m.ai : 'normal';
      const canEdit = isHost && waiting;
      const tag = document.createElement(canEdit ? 'button' : 'span');
      tag.className = 'ai-lv ' + lv;
      tag.textContent = t('ai.' + lv) + (canEdit ? ' ▾' : '');
      if (canEdit) {
        tag.title = t('ai.change');
        tag.onclick = (e) => { e.stopPropagation(); openBotPicker(m.id, lv); };
      }
      el.querySelector('.st').appendChild(tag);
    }
    if (team) {
      const canSwitch = waiting && (m.id === me || isHost);
      const tb = document.createElement('button');
      tb.className = 'mini';
      tb.style.background = TEAM_COLORS[m.team];
      tb.style.color = '#fff';
      tb.textContent = t('team.' + m.team) + (canSwitch ? '⇄' : '');
      tb.disabled = !canSwitch;
      tb.onclick = () => send({ t: 'team', id: m.id, team: 1 - m.team });
      el.appendChild(tb);
    }
    if (isHost && m.id !== me && waiting) {
      const k = document.createElement('button');
      k.className = 'mini kick';
      k.innerHTML = icon('close');
      k.title = t(m.isBot ? 'room.removeBot' : 'room.kick');
      k.onclick = () => send({ t: 'kick', id: m.id });
      el.appendChild(k);
    }
    list.appendChild(el);
  }

  $('#map-host-hint').textContent = t(isHost ? 'room.hostCanPick' : 'room.hostOnly');
  mapPicker($('#map-picker'), r.settings.mapId, (id) => send({ t: 'settings', mapId: id }), !isHost || !waiting);
  const locked = !isHost || !waiting;
  segPicker($('#set-mode'), r.settings.mode, (v) => send({ t: 'settings', mode: v }), locked);
  segPicker($('#set-items'), r.settings.items === false ? '0' : '1', (v) => send({ t: 'settings', items: v === '1' }), locked);
  segPicker($('#set-revive'), r.settings.revive ? '1' : '0', (v) => send({ t: 'settings', revive: v === '1' }), locked);
  // 复活赛不缩圈
  segPicker($('#set-shrink'), r.settings.revive || r.settings.shrink === false ? '0' : '1', (v) => send({ t: 'settings', shrink: v === '1' }), locked || !!r.settings.revive);
  segPicker($('#set-time'), String(r.settings.time || 10), (v) => send({ t: 'settings', time: Number(v) }), locked);

  const addBot = $('#btn-add-bot');
  addBot.classList.toggle('hidden', !isHost);
  addBot.disabled = !waiting || bots >= r.botLimit || r.members.length >= MAX_PLAYERS;
  addBot.innerHTML = `${icon('bot')}${t('room.addAiCount', { n: bots, max: r.botLimit })}`;

  const mine = r.members.find((m) => m.id === me);
  const ready = $('#btn-ready');
  ready.className = 'btn btn-huge ' + (mine?.ready ? 'btn-gray' : 'btn-green pulse');
  ready.classList.toggle('hidden', isHost);
  ready.innerHTML = mine?.ready ? t('room.unready') : `${icon('check')}${t('room.ready')}`;
  const start = $('#btn-start');
  const othersReady = r.members.every((m) => m.isBot || m.id === r.hostId || m.ready);
  const canStart = waiting && r.members.length >= 2 && othersReady;
  start.className = 'btn btn-yellow btn-huge' + (canStart ? ' pulse' : '');
  start.innerHTML = `${icon('play')}<span data-i18n="room.start">${t('room.start')}</span>`;
  start.classList.toggle('hidden', !isHost);
  start.disabled = !waiting;
  $('#room-hint').textContent = !waiting
    ? t('room.inProgress')
    : isHost
      ? t(r.members.length < 2 ? 'room.needTwo' : othersReady ? 'room.allReady' : 'room.waitOthers')
      : t(mine?.ready ? 'room.waitHost' : 'room.pleaseReady');
}

// ================= 聊天 =================
/** 系统消息：服务器只发 key + 参数 */
function sysText(m) {
  if (m.key) return t('sys.' + m.key, { ...(m.params || {}), name: displayName(m.params?.name || '', false) });
  return m.text || '';
}

function addChat(m) {
  const target = m.scope === 'lobby' ? $('#lobby-chat') : $('#room-chat');
  const line = document.createElement('div');
  if (m.sys) {
    line.className = 'sys';
    line.textContent = sysText(m);
  } else {
    line.innerHTML = `<b style="color:${(SKINS[m.skin] || SKINS[0]).color}">${esc(m.from)}:</b>${esc(m.text)}`;
  }
  target.appendChild(line);
  while (target.children.length > 100) target.firstChild.remove();
  target.scrollTop = target.scrollHeight;
  if (state.screen === 'game' && m.scope === 'room') {
    const g = document.createElement('div');
    g.textContent = m.sys ? sysText(m) : `${m.from}: ${m.text}`;
    $('#game-chat').appendChild(g);
    setTimeout(() => g.remove(), 8000);
  }
  if (!m.sys) audio.fx('chat');
}
$$('.chat-form').forEach((f) => {
  f.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = f.querySelector('input');
    const text = cleanChat(input.value); // 聊天：不限制字符，显示时一律当纯文本（转义 / textContent）
    if (text) send({ t: 'chat', text });
    input.value = '';
  });
});

// ================= 游戏 =================
async function ensureScene() {
  if (scene) return scene;
  scene = new GameScene($('#game-view'));
  scene.onMove = (mv) => send({ t: 'mv', ...mv, q: nextSeq() });
  if (new URLSearchParams(location.search).has('debug')) window.__scene = scene; // 调试用
  return scene;
}

async function startGame(info) {
  // 重连回到同一局：直接按服务器状态重建场景（不重播开场动画）
  const rejoin = !!info.rejoin;
  state.game = info;
  state.last = null;
  state.resultShown = false;
  state.lastCd = null;
  state.prevHearts = {};
  net.pending.clear();
  net.inputLat = 0;
  net.samples = [];
  net.lastAck = 0;
  net.snapTimes = [];
  $('#result-modal').classList.add('hidden');
  $('#hud-banner').classList.add('hidden');
  $('#spectate').classList.add('hidden');
  $('#game-chat').innerHTML = '';
  $('#killfeed').innerHTML = '';
  $('#pickup-pop').innerHTML = '';
  show('game');
  // 开局等待其他玩家：显示连接状态，直到服务器开始倒计时
  if (!rejoin || info.phase === 'wait') renderWaitStart(null);
  const sc = await ensureScene();
  sc.load({ ...info, players: info.players.map((p) => ({ ...p, name: displayName(p.name, p.isBot) })) }, state.user.id);
  if (info.k) sc.rebuildBlocks(info.k); // 当前地图方块（重连时尤其重要）
  if (rejoin) {
    sc.introT = 1;
    sc.forceSync = true;
    sc.frozen = false;
    toast(t('conn.rejoined'));
  }
  $('#hud-map').textContent = `${mapName(info.mapId)} · ${t(info.mode === 'team' ? 'mode.team' : 'mode.ffa')}`;
  audio.play(TRACKS[info.theme] ? info.theme : 'meadow');
  buildHudPlayers();
  buildItemBar(info.items !== false);
  input.reset();
  send({ t: 'loaded' }); // 场景加载完成：告诉服务器自己已就绪
}

/** 开局等待玩家连接：wait = 还没就绪的玩家 id 列表（null 表示还没收到服务器状态，全部显示连接中） */
function renderWaitStart(wait, left) {
  const box = $('#wait-start');
  if (!state.game) return box.classList.add('hidden');
  box.classList.remove('hidden');
  const humans = state.game.players.filter((p) => !p.isBot);
  $('#wait-list').innerHTML = humans.map((p) => {
    const ok = wait ? !wait.includes(p.id) : false;
    return `<div class="row${ok ? ' ok' : ''}"><span class="nm">${esc(displayName(p.name, false))}${p.id === state.user.id ? ` <small>(${esc(t('wait.you'))})</small>` : ''}</span><span class="st">${ok ? `${icon('check')}${esc(t('wait.ready'))}` : esc(t('wait.loading'))}</span></div>`;
  }).join('');
  $('#wait-left').textContent = left != null ? t('wait.left', { n: left }) : '';
}

/** 道具栏：左下角 6 格。点击或按数字键 1–6 使用 */
function buildItemBar(on) {
  const dock = $('#item-dock');
  dock.classList.toggle('hidden', !on);
  $('#game-chat').classList.toggle('above-items', on);
  const bar = $('#item-bar');
  bar.innerHTML = '';
  for (let i = 0; i < ITEM_SLOTS; i++) {
    const b = document.createElement('button');
    b.className = 'slot empty';
    b.dataset.s = i;
    b.innerHTML = `<b>${i + 1}</b><span class="ic"></span>`;
    b.addEventListener('pointerdown', (e) => { e.preventDefault(); useItem(i); });
    bar.appendChild(b);
  }
  state.itemSig = '';
  $('#fx-bar').innerHTML = '';
}

function useItem(i) {
  const kind = state.myItems?.[i];
  const slot = $('#item-bar').children[i];
  if (!kind) { slot?.classList.remove('shake'); void slot?.offsetWidth; slot?.classList.add('shake'); return; }
  send({ t: 'use', s: i });
}

const FX_KEYS = [['ish', 'ishield'], ['bt', 'boots'], ['gh', 'ghost'], ['wg', 'wings']];
function updateItemBar(me) {
  if (!me) return;
  const items = (me.it || '').split(',');
  state.myItems = items;
  const sig = items.join(',') + (me.tr > 0 ? 't' : '');
  if (sig !== state.itemSig) {
    state.itemSig = sig;
    [...$('#item-bar').children].forEach((b, i) => {
      const kind = items[i];
      const def = POWERUPS[kind];
      b.classList.toggle('empty', !def);
      // 针只能在被困时用；其他道具被困时不能用
      b.classList.toggle('usable', !!def && (kind === 'needle' ? me.tr > 0 : !(me.tr > 0)));
      b.style.setProperty('--pc', def ? def.color : 'transparent');
      b.querySelector('.ic').innerHTML = def ? icon(def.icon) : '';
      b.title = def ? `${t('pu.' + kind)} · ${t('pu.desc.' + kind)}` : '';
    });
  }
  // 正在生效的效果（剩余秒数）
  const html = FX_KEYS.filter(([k]) => me[k] > 0).map(([k, kind]) => {
    const def = POWERUPS[kind];
    return `<span class="fx" style="--pc:${def.color}">${icon(def.icon)}${Math.ceil(me[k])}s</span>`;
  }).join('');
  const fx = $('#fx-bar');
  if (fx.innerHTML !== html) fx.innerHTML = html;
}

function buildHudPlayers() {
  const root = $('#hud-players');
  root.innerHTML = '';
  state.game.players.forEach((p, i) => {
    const el = document.createElement('div');
    el.className = 'hp' + (p.id === state.user.id ? ' me' : '');
    el.id = 'hp-' + p.id;
    el.style.animationDelay = i * 0.06 + 's';
    if (state.game.mode === 'team') el.style.borderColor = TEAM_COLORS[p.team];
    el.appendChild(avatarEl(p, 22));
    // 两行：名字 + 状态（靠右） / 能力数值 + 击倒数（靠右）；被困倒计时条贴在整行底部
    el.insertAdjacentHTML('beforeend', `<div class="hp-main"><div class="hp-row"><div class="n">${p.level ? levelBadge(p.level) : ''}${esc(displayName(p.name, p.isBot))}</div><div class="hearts"></div></div><div class="hp-row"><div class="pw"></div><div class="kl"></div></div></div><i class="tbar"></i>`);
    root.appendChild(el);
  });
}

function countdownText(text, cls = '') {
  const center = $('#hud-center');
  center.textContent = text;
  center.className = 'hud-center ' + cls;
  void center.offsetWidth;
  center.classList.add('anim');
}

let hudTick = 0;
function onSnapshot(s) {
  if (!state.game || state.screen !== 'game') return;
  state.last = s;
  if (scene) scene.rtt = state.conn?.ping ?? 0;
  scene?.pushState(s);
  playEvents(s);
  // 输入确认延迟：发送输入 → 服务器回传已处理该序号
  const now = performance.now();
  const meSnap = s.p.find((p) => p.id === state.user.id);
  updateItemBar(meSnap);
  if (meSnap && meSnap.q > net.lastAck) {
    const t0 = net.pending.get(meSnap.q);
    if (t0 && s.ph === 'play') {
      // 取最近 20 次输入确认延迟的中位数（避免开局加载卡顿造成的异常值）
      net.samples.push(now - t0);
      if (net.samples.length > 20) net.samples.shift();
      const sorted = [...net.samples].sort((a, b) => a - b);
      net.inputLat = sorted[Math.floor(sorted.length / 2)];
    }
    for (const k of net.pending.keys()) if (k <= meSnap.q) net.pending.delete(k);
    net.lastAck = meSnap.q;
  }
  net.snapTimes.push(now);
  while (net.snapTimes.length && now - net.snapTimes[0] > 1000) net.snapTimes.shift();

  if (s.ph === 'wait') renderWaitStart(s.wt || [], s.wl);
  else $('#wait-start').classList.add('hidden');
  if (s.ph === 'countdown' && s.cd !== state.lastCd) {
    state.lastCd = s.cd;
    countdownText(s.cd);
    audio.fx('beep');
  } else if (s.ph === 'play' && state.lastCd !== 'go') {
    state.lastCd = 'go';
    countdownText('FIGHT', 'go');
    if (state.game) pickupPop('shield', t('hud.startInvuln'));
    setTimeout(() => { if (state.lastCd === 'go') $('#hud-center').textContent = ''; }, 800);
  }

  if (++hudTick % 3 !== 0) return;
  const tl = Math.ceil(s.tl);
  $('#hud-timer').textContent = `${Math.floor(tl / 60)}:${String(tl % 60).padStart(2, '0')}`;
  $('#hud-timer-wrap').classList.toggle('sd', !!s.sd);
  const m = scene?.metrics || {};
  $('#hud-net').innerHTML = `<span>${t('hud.input')} <b>${Math.round(net.inputLat)}</b>ms</span><span><b>${m.fps || 0}</b> FPS</span><span>${t('hud.sync')} <b>${net.snapTimes.length}</b> Hz</span>`;
  const mine = s.p.find((p) => p.id === state.user.id);
  $('#spectate').classList.toggle('hidden', !mine || !!mine.a || s.ph === 'end' || state.resultShown);
  // 复活赛：被击倒后显示复活倒计时，而不是「观战中」
  if (mine && !mine.a) $('#spectate span').textContent = mine.rs ? t('hud.respawn', { n: Math.ceil(mine.rs) }) : t('hud.spectate');
  for (const p of s.p) {
    const el = document.getElementById('hp-' + p.id);
    if (!el) continue;
    el.classList.toggle('dead', !p.a);
    el.classList.toggle('trapped', !!(p.a && p.tr));
    el.querySelector('.hearts').innerHTML = !p.a
      ? `<span class="out">${p.rs ? t('hud.respawn', { n: Math.ceil(p.rs) }) : t('hud.out')}</span>`
      : p.tr
        ? `<span class="trap">${t('hud.trapped', { s: p.tr.toFixed(1) })}</span>`
        : `${p.sh ? `<span class="sh">${icon('shield')}</span>` : ''}<span class="ok">${t(p.iv ? 'hud.invuln' : 'hud.alive')}</span>`;
    el.querySelector('.tbar').style.width = p.a && p.tr ? `${p.tr * 10}%` : '0';
    const spd = p.s * 5;
    el.querySelector('.pw').innerHTML = `<span>${icon('bomb')}${p.mb}</span><span>${icon('flame')}${powerSize(p.r)}</span><span class="${spd > 0 ? 'up' : spd < 0 ? 'down' : ''}">${icon('shoe')}${spd > 0 ? '+' : ''}${spd}%</span>${p.k ? `<span>${icon('kick')}</span>` : ''}`;
    el.querySelector('.kl').innerHTML = `${icon('target')}${p.kl}`;
  }
}

function feed(html, cls = '') {
  const root = $('#killfeed');
  const d = document.createElement('div');
  d.className = cls;
  d.innerHTML = html;
  root.appendChild(d);
  while (root.children.length > 5) root.firstChild.remove();
  setTimeout(() => d.remove(), 4200);
}

function pickupPop(type, extra) {
  const def = POWERUPS[type];
  if (!def) return;
  const d = document.createElement('div');
  d.innerHTML = `<span style="color:${def.color};display:flex">${icon(def.icon)}</span>${esc(t('pu.' + type))}${extra ? ` <small>${esc(extra)}</small>` : ''}`;
  $('#pickup-pop').appendChild(d);
  setTimeout(() => d.remove(), 1700);
}

const TIP_MS = 5000;
function itemTip(type, mine) {
  const def = POWERUPS[type];
  const root = $('#item-tips');
  if (!def || !root) return;
  const params = mine ? { n: mine.mb, size: powerSize(mine.r), pct: (mine.s >= 0 ? '+' : '') + mine.s * 5 + '%' } : {};
  // 同类道具连续拾取：刷新已有卡片
  root.querySelector(`[data-type="${type}"]`)?.remove();
  const d = document.createElement('div');
  d.className = 'item-tip';
  d.dataset.type = type;
  d.style.setProperty('--pc', def.color);
  d.innerHTML = `<span class="ic-box">${icon(def.icon)}</span>
    <div class="tx"><div class="hd"><small>${t('tip.item')}</small><b>${esc(t('pu.' + type))}</b></div>
    <p>${esc(t('pu.desc.' + type))}</p>${mine ? `<em>${esc(t('pu.stat.' + type, params))}</em>` : ''}</div>
    <i class="timer" style="animation-duration:${TIP_MS}ms"></i>`;
  root.prepend(d);
  while (root.children.length > 3) root.lastChild.remove();
  setTimeout(() => { d.classList.add('out'); setTimeout(() => d.remove(), 350); }, TIP_MS);
}

/** 对局中有人断线 / 重连：屏幕上方显示几秒
 *  【头像】名字
 *          断开连接 / 重新连接 */
function broadcastBanner(person, good) {
  const el = $('#hud-broadcast');
  const d = document.createElement('div');
  d.className = 'bc ' + (good ? 'on' : 'off');
  const who = document.createElement('div');
  who.className = 'who';
  who.appendChild(avatarEl(person, 16));
  who.insertAdjacentHTML('beforeend', `<b>${esc(displayName(person.name, person.isBot))}</b>`);
  d.appendChild(who);
  d.insertAdjacentHTML('beforeend', `<small>${icon(good ? 'wifi' : 'wifiOff')}${t(good ? 'ev.reconnected' : 'ev.disconnected')}</small>`);
  el.appendChild(d);
  audio.fx(good ? 'shield' : 'hit', { vol: 0.5 });
  while (el.children.length > 3) el.firstChild.remove();
  setTimeout(() => { d.classList.add('out'); setTimeout(() => d.remove(), 400); }, 3200);
}

function hurtFx(id) {
  const el = document.getElementById('hp-' + id);
  if (el) { el.classList.remove('hurt'); void el.offsetWidth; el.classList.add('hurt'); }
}

function playEvents(s) {
  const me = state.user.id;
  const name = (id) => { const p = state.game.players.find((x) => x.id === id); return esc(p ? displayName(p.name, p.isBot) : ''); };
  let booms = 0;
  for (const e of s.e) {
    switch (e.k) {
      case 'place': audio.fx('place', { vol: 0.7, st: e.st }); break;
      case 'boom': if (booms++ < 2) audio.fx('boom', { st: e.st }); break;
      case 'crate': audio.fx('crate', { vol: 0.6 }); break;
      case 'pick':
        audio.fx('pick', { vol: e.id === me ? 1 : 0.35 });
        if (e.id === me) {
          const mine = s.p.find((p) => p.id === me);
          itemTip(e.type, POWERUPS[e.type]?.item ? null : mine);
        }
        break;
      case 'use':
        // 使用道具：自己有音效；用针脱困所有人都看得到
        if (e.id === me) audio.fx(e.it === 'needle' ? 'shield' : 'pick');
        if (e.it === 'needle') {
          feed(`${icon('needle')} ${t('ev.needle', { name: name(e.id) })}`);
          if (e.id !== me) audio.fx('shield', { vol: 0.4 });
        }
        break;
      case 'trap':
        audio.fx('hit', { vol: e.id === me ? 1 : 0.5 });
        hurtFx(e.id);
        feed(`${icon('target')} ${t('ev.trapped', { name: name(e.id) })}`);
        if (e.id === me) {
          const f = $('#hit-flash');
          f.classList.remove('on'); void f.offsetWidth; f.classList.add('on');
          toast(t(state.game.mode === 'team' ? 'ev.trappedMeTeam' : 'ev.trappedMe'), true);
        }
        break;
      case 'rescue':
        audio.fx('shield');
        feed(`${icon('shield')} ${t('ev.rescued', { by: name(e.by), name: name(e.id) })}`);
        if (e.id === me) pickupPop('shield', t('ev.rescuedMe'));
        break;
      case 'pop':
        audio.fx('boom', { vol: 0.6 });
        feed(`${icon('close')} ${t('ev.popped', { by: name(e.by), name: name(e.id) })}`);
        break;
      case 'barrel':
        audio.fx('boom', { vol: 0.8 });
        break;
      case 'steel':
        audio.fx('kick', { vol: 0.6 });
        break;
      case 'shield':
        audio.fx('shield');
        if (e.id === me) pickupPop('shield', t('ev.blocked'));
        break;
      case 'die':
        audio.fx('die');
        hurtFx(e.id);
        feed(`${icon('skull')} ${t(e.rs ? 'ev.downed' : 'ev.eliminated', { name: name(e.id) })}`);
        if (e.id === me) {
          $('#spectate').classList.remove('hidden');
          const f = $('#hit-flash');
          f.classList.remove('on'); void f.offsetWidth; f.classList.add('on');
        }
        break;
      case 'tele': audio.fx('tele', { vol: 0.6 }); break;
      case 'respawn': if (e.id === me) audio.fx('go', { vol: 0.6 }); break;
      case 'kick': audio.fx('kick'); break;
      case 'wall': audio.fx('wall', { vol: 0.5 }); break;
      case 'go': audio.fx('go'); break;
      case 'sd':
        audio.fx('sd');
        $('#hud-banner').classList.remove('hidden');
        setTimeout(() => $('#hud-banner').classList.add('hidden'), 4000);
        break;
      default: break;
    }
  }
}

function confetti(n = 90) {
  const root = $('#confetti');
  root.innerHTML = '';
  const colors = ['#ffb547', '#ffd27a', '#36d6ff', '#ffffff'];
  for (let i = 0; i < n; i++) {
    const c = document.createElement('i');
    c.style.left = Math.random() * 100 + '%';
    c.style.background = colors[i % colors.length];
    c.style.animationDuration = 2.5 + Math.random() * 2.5 + 's';
    c.style.animationDelay = Math.random() * 1.5 + 's';
    root.appendChild(c);
  }
}

function showResult(result) {
  if (state.screen !== 'game' || state.resultShown) return;
  state.resultShown = true;
  $('#spectate').classList.add('hidden');
  const me = result.players.find((p) => p.id === state.user.id);
  const win = !!me?.win;
  const modal = $('#result-modal');
  modal.classList.toggle('lose', !win && !result.draw);
  const title = $('#result-title');
  if (result.draw) title.innerHTML = `DRAW<small>${t('result.draw')}</small>`;
  else if (win) title.innerHTML = `VICTORY<small>${t('result.win')}</small>`;
  else if (result.mode === 'team') title.innerHTML = `DEFEAT<small>${t('result.teamWin', { team: t('team.' + result.winnerTeam) })}</small>`;
  else title.innerHTML = `DEFEAT<small>${t('result.lose')}</small>`;
  const nStars = win ? 3 : result.draw && me?.alive ? 2 : me && me.place <= 2 ? 1 : 0;
  $('#result-stars').innerHTML = [0, 1, 2].map((i) => `<span class="${i < nStars ? '' : 'off'}" style="animation-delay:${0.3 + i * 0.2}s">${icon('star')}</span>`).join('');
  audio.fx(win ? 'win' : 'lose');
  const ol = $('#result-list');
  ol.innerHTML = '';
  result.players.forEach((p, i) => {
    const li = document.createElement('li');
    if (p.win) li.className = 'win';
    li.style.animationDelay = 0.5 + i * 0.08 + 's';
    li.innerHTML = `<span class="place">${p.place}</span>`;
    li.appendChild(avatarCanvas(p.skin, p.hat, 19, { dead: !p.alive }));
    const team = result.mode === 'team' ? ` <small style="color:${TEAM_COLORS[p.team]}">${t('team.' + p.team)}</small>` : '';
    if (p.quit) li.classList.add('quit');
    li.insertAdjacentHTML('beforeend', `<span>${esc(displayName(p.name, p.isBot))}${team}${p.quit ? ` <small class="quit-tag">${t('result.quit')}</small>` : ''}</span><span class="k">${t('result.kills')} <b>${p.kills}</b>${p.rescues ? ` ${t('result.rescues')} <b>${p.rescues}</b>` : ''}${p.points ? `<span class="pts">${icon('gem')} +${p.points}</span>` : ''}</span>`);
    ol.appendChild(li);
  });
  const rw = $('#result-reward');
  if (me && (me.exp || me.points)) {
    const total = me.totalExp ?? 0, prev = me.prevExp ?? Math.max(0, total - me.exp);
    const lv0 = levelOf(prev), lv1 = me.level ?? levelOf(total);
    const tier = tierOf(lv1);
    const unlocked = (me.unlocked || []).map((h) => t('hat.' + h)).join(' / ');
    rw.innerHTML = `<div class="rw-row"><span>${icon('star')}+${me.exp} EXP${me.expBoost ? `<small class="boost-tag">×${me.expBoost / 100}</small>` : ''}</span>${me.points ? `<span class="pts">${icon('gem')}+${me.points}</span>` : ''}</div>
      ${bonusLine(me)}
      <div class="rw-lv"><span class="rw-badge">${levelBadge(lv0)}</span><div class="expbar big" style="--tc:${tier.color}"><i style="width:${levelProgress(prev) * 100}%"></i><em></em></div></div>
      ${me.levelUp ? `<div class="rw-up" style="--tc:${tier.color}">${t('lv.up', { lv: lv1, tier: t('tier.' + tier.index) })}</div>` : ''}
      ${unlocked ? `<div class="rw-unlock">${icon('crown')} ${t('lv.unlocked', { hats: esc(unlocked) })}</div>` : ''}
      ${(me.shopUnlocked || []).length ? `<div class="rw-unlock shop">${icon('gem')} ${t('lv.shopNew')}</div>` : ''}`;
    rw.classList.remove('hidden');
    animateExp(rw, prev, total);
    setTimeout(() => audio.fx('coin'), 700);
  } else {
    rw.innerHTML = me ? `<small style="color:var(--muted)">${t('result.noReward')}</small>` : '';
    rw.classList.toggle('hidden', !me);
  }
  modal.classList.remove('hidden');
  if (win) confetti();
  else $('#confetti').innerHTML = '';
  clearTimeout(state.backTimer);
  state.backTimer = setTimeout(backToRoom, 15000);
}

function animateExp(rw, from, to) {
  const bar = rw.querySelector('.expbar i'), label = rw.querySelector('.expbar em'), badge = rw.querySelector('.rw-badge');
  const t0 = performance.now() + 900, dur = 1400;
  let shownLv = levelOf(from);
  const step = (now) => {
    if (!rw.isConnected) return;
    const k = Math.max(0, Math.min(1, (now - t0) / dur));
    const v = Math.round(from + (to - from) * (1 - (1 - k) ** 3));
    const lv = levelOf(v);
    if (lv !== shownLv) { shownLv = lv; badge.innerHTML = levelBadge(lv); badge.classList.remove('pop'); void badge.offsetWidth; badge.classList.add('pop'); audio.fx('shield'); }
    const lo = levelFloor(lv), hi = levelCeil(lv);
    bar.style.width = levelProgress(v) * 100 + '%';
    label.textContent = hi == null ? 'MAX' : t('lv.exp', { cur: v - lo, need: hi - lo });
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function backToRoom() {
  clearTimeout(state.backTimer);
  if (state.screen !== 'game') return;
  state.game = null;
  input.reset();
  const dest = state.room && state.inRoom ? 'room' : 'lobby';
  show(dest);
  setTimeout(() => {
    $('#result-modal').classList.add('hidden');
    if (dest === 'room') renderRoom();
  }, 320);
  loadLeaderboard();
}

// ================= 输入：移动在客户端计算后上报位置，服务器校验；炸弹 / 爆炸 / 伤害判定在服务器 =================
const KEYMAP = {
  ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down',
  ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right',
};
const net = { seq: 0, pending: new Map(), inputLat: 0, lastAck: 0, snapTimes: [], samples: [] };
function nextSeq() {
  const q = ++net.seq;
  net.pending.set(q, performance.now());
  return q;
}
const input = {
  held: [],
  sent: null,
  reset() { this.held = []; this.sync(true); },
  press(d) {
    if (!this.held.includes(d)) {
      this.held.push(d);
      scene?.localTap(d); // 本地立即响应
    }
    this.sync();
  },
  release(d) { this.held = this.held.filter((x) => x !== d); this.sync(); },
  sync(force) {
    const d = this.held[this.held.length - 1] || null;
    scene?.setLocalDir(d);
    if (d !== this.sent || force) {
      this.sent = d;
      send({ t: 'in', d, q: nextSeq() });
    }
  },
  bomb() {
    const pos = scene?.localBomb(); // 本地立即显示炸弹
    send({ t: 'bomb', q: nextSeq(), ...(pos || {}) });
  },
};

function gameActive() {
  return state.screen === 'game' && state.game && !state.resultShown && document.activeElement?.tagName !== 'INPUT';
}
const SLOT_KEYS = { Digit1: 0, Digit2: 1, Digit3: 2, Digit4: 3, Digit5: 4, Digit6: 5, Numpad1: 0, Numpad2: 1, Numpad3: 2, Numpad4: 3, Numpad5: 4, Numpad6: 5 };
window.addEventListener('keydown', (e) => {
  if (!gameActive()) {
    if (state.screen === 'game' && state.resultShown && (e.code === 'Enter' || e.code === 'Space')) backToRoom();
    return;
  }
  const d = KEYMAP[e.code];
  if (d) { e.preventDefault(); input.press(d); }
  if ((e.code === 'Space' || e.code === 'KeyJ' || e.code === 'KeyK') && !e.repeat) { e.preventDefault(); input.bomb(); }
  // 数字键 1–6：使用道具栏对应格子
  const slot = SLOT_KEYS[e.code];
  if (slot !== undefined && !e.repeat) { e.preventDefault(); useItem(slot); }
});
window.addEventListener('keyup', (e) => {
  const d = KEYMAP[e.code];
  if (d && state.screen === 'game') input.release(d);
});
window.addEventListener('blur', () => { if (state.screen === 'game') input.reset(); });
$$('#touch .dpad button').forEach((b) => {
  const d = b.dataset.d;
  b.addEventListener('pointerdown', (e) => { e.preventDefault(); input.press(d); });
  for (const ev of ['pointerup', 'pointerleave', 'pointercancel']) b.addEventListener(ev, () => input.release(d));
});
$('#touch-bomb').addEventListener('pointerdown', (e) => { e.preventDefault(); input.bomb(); });

// ================= 按钮 =================
$('#btn-refresh').onclick = () => { send({ t: 'lobby' }); loadLeaderboard(); };
$('#btn-quick').onclick = () => send({ t: 'quickJoin' });
$('#btn-create').onclick = openCreate;
const PW_RE = /^[A-Za-z0-9]{6}$/;
$('#btn-create-ok').onclick = () => {
  const password = $('#create-password').value.trim();
  if (password && !PW_RE.test(password)) { shake($('#create-password')); toast(t('err.room_password_format'), true); return; }
  const name = cleanText($('#create-name').value);
  if (name === null) { shake($('#create-name')); toast(t('err.text_invalid'), true); return; }
  send({ t: 'createRoom', name, ...createSel, ...(password ? { password } : {}) });
  closeModals();
};
for (const id of ['#create-password', '#join-password']) {
  $(id).addEventListener('input', (e) => { e.target.value = e.target.value.replace(/[^A-Za-z0-9]/g, '').slice(0, 6); });
}

// ================= 房间密码 =================
let pwRoomId = null;
function askRoomPassword(id) {
  pwRoomId = id;
  $('#join-password').value = '';
  openModal('#pw-modal');
  setTimeout(() => $('#join-password').focus(), 50);
}
$('#btn-join-pw').onclick = () => {
  const password = $('#join-password').value.trim();
  if (!PW_RE.test(password)) { shake($('#join-password')); toast(t('err.room_password_format'), true); return; }
  send({ t: 'joinRoom', id: pwRoomId, password });
};
$('#join-password').addEventListener('keydown', (e) => e.key === 'Enter' && $('#btn-join-pw').click());

// ================= 对战记录 =================
$('#btn-history').onclick = () => {
  $('#history-list').innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  openModal('#history-modal');
  send({ t: 'history' });
};
function timeAgo(iso) {
  const d = new Date(iso);
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return t('history.justNow');
  if (sec < 3600) return t('history.minAgo', { n: Math.floor(sec / 60) });
  if (sec < 86400) return t('history.hourAgo', { n: Math.floor(sec / 3600) });
  return d.toLocaleDateString(getLang(), { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(getLang(), { hour: '2-digit', minute: '2-digit' });
}
function renderHistory(list) {
  const root = $('#history-list');
  if (!list.length) { root.innerHTML = `<div class="empty">${icon('history')}${t('history.empty')}</div>`; return; }
  root.innerHTML = '';
  for (const g of list) {
    const res = g.quit ? 'quit' : g.win ? 'win' : g.draw ? 'draw' : 'lose';
    const card = document.createElement('div');
    card.className = 'hist ' + res;
    const mins = Math.floor(g.duration / 60), secs = String(g.duration % 60).padStart(2, '0');
    card.innerHTML = `<div class="hist-res"><b>${t('history.' + res)}</b><small>#${g.place}</small></div>
      <div class="hist-main">
        <div class="hist-top"><span class="map">${esc(mapName(g.mapId))}</span><span>${t(g.mode === 'team' ? 'mode.teamShort' : 'mode.ffaShort')}</span><span>${mins}:${secs}</span><span class="ago">${timeAgo(g.at)}</span></div>
        <div class="hist-players"></div>
      </div>
      <div class="hist-gain"><span>${icon('star')}+${g.exp}</span>${g.points ? `<span class="pts">${icon('gem')}+${g.points}</span>` : ''}<small>${t('result.kills')} ${g.kills}${g.rescues ? ` · ${t('result.rescues')} ${g.rescues}` : ''}</small></div>`;
    const ps = card.querySelector('.hist-players');
    for (const p of g.players) {
      const chip = document.createElement('span');
      chip.className = 'hist-p' + (p.me ? ' me' : '') + (p.win ? ' won' : '') + (p.quit ? ' left' : '');
      if (g.mode === 'team') chip.style.setProperty('--tc', TEAM_COLORS[p.team]);
      chip.appendChild(avatarEl(p, 11));
      chip.insertAdjacentHTML('beforeend', `<span>${esc(displayName(p.name, p.isBot))}</span>`);
      ps.appendChild(chip);
    }
    root.appendChild(card);
  }
}
$('#btn-leave-room').onclick = () => {
  state.inRoom = false;
  state.room = null;
  send({ t: 'leaveRoom' });
  show('lobby');
};
$('#btn-add-bot').onclick = addNormalBot;

/** 添加 AI：直接加一个「中等」，之后可在左侧成员列表点难度标签修改 */
function addNormalBot() {
  send({ t: 'addBot', level: 'normal' });
}

/** 修改某个 AI 的难度（左侧成员列表里点难度标签打开） */
const AI_LEVELS = ['easy', 'normal', 'hard'];
function openBotPicker(id, current) {
  const box = $('#bot-levels');
  box.innerHTML = '';
  for (const lv of AI_LEVELS) {
    const b = document.createElement('button');
    b.className = lv + (lv === current ? ' on' : '');
    b.innerHTML = `<b>${esc(t('ai.' + lv))}</b><small>${esc(t('ai.' + lv + 'Desc'))}</small>`;
    b.onclick = () => {
      if (lv !== current) send({ t: 'botLevel', id, level: lv });
      closeModals();
    };
    box.appendChild(b);
  }
  openModal('#bot-modal');
}
$('#btn-ready').onclick = () => {
  const mine = state.room?.members.find((m) => m.id === state.user.id);
  send({ t: 'ready', v: !mine?.ready });
};
$('#btn-start').onclick = () => {
  // 延迟大时，开始消息要过一会儿才回来：先让按钮显示「正在开始…」，避免看起来卡住不动
  const b = $('#btn-start');
  b.classList.add('busy');
  b.innerHTML = `<span class="spinner inline"></span>${t('wait.starting')}`;
  clearTimeout(state.startBusyT);
  state.startBusyT = setTimeout(() => { if (state.screen === 'room' && state.room) renderRoom(); }, 8000); // 一直没回应：恢复按钮
  send({ t: 'start' });
};
$('#btn-back-room').onclick = backToRoom;
$('#btn-quit').onclick = async () => {
  if (state.resultShown) return backToRoom();
  const ok = await confirmDialog(t('quit.text'), { title: t('quit.title'), yes: t('quit.yes'), no: t('quit.no') });
  if (!ok || state.screen !== 'game') return;
  state.inRoom = false;
  state.room = null;
  state.game = null;
  input.reset();
  send({ t: 'leaveRoom' });
  show('lobby');
};
$('#btn-logout').onclick = async () => {
  const tip = state.user.provider === 'github' ? t('logout.github') : t('logout.guest', { id: state.user.id });
  const ok = await confirmDialog(tip, { title: t('logout.title'), yes: t('logout.yes'), no: t('common.cancel') });
  if (!ok) return;
  endSession();
  state.user = null;
  state.room = null;
  resetLoginForm();
  if (state.loginCfg?.guest) $('#login-id').value = savedId();
  show('login');
};

let profileSel;
$('#btn-profile').onclick = () => {
  profileSel = avatarPicker(
    { canvas: $('#profile-avatar'), skins: $('#profile-skins'), hats: $('#profile-hats'), name: $('#profile-name') },
    state.user,
    null,
    state.user.level,
    state.user.items || [],
  );
  renameMode(false);
  openModal('#profile-modal');
};
$('#btn-profile-ok').onclick = () => {
  send({ t: 'profile', skin: profileSel.skin, hat: profileSel.hat });
  closeModals();
};

function syncRange(el) { el.style.setProperty('--v', el.value * 100 + '%'); }
$$('.sound-btn').forEach((b) => (b.onclick = () => {
  audio.unlock();
  $('#vol-music').value = audio.musicVol;
  $('#vol-sfx').value = audio.sfxVol;
  syncRange($('#vol-music'));
  syncRange($('#vol-sfx'));
  $('#track-name').textContent = audio.track ? t('settings.nowPlaying', { title: TRACKS[audio.track].title }) : '';
  drawMsaaSeg();
  openModal('#sound-modal');
}));
/** 多重采样：无 / 2× / 4× / 8×（默认 4×），立即生效并保存在本地 */
function drawMsaaSeg() {
  segPicker($('#msaa-seg'), String(getMsaa()), (v) => {
    const n = Number(v);
    setMsaa(n);
    stage?.setMsaa(n);
    scene?.setMsaa(n);
    drawMsaaSeg();
  });
}
$('#vol-music').oninput = (e) => { audio.setMusicVolume(Number(e.target.value)); syncRange(e.target); };
$('#vol-sfx').oninput = (e) => { audio.setSfxVolume(Number(e.target.value)); syncRange(e.target); audio.fx('pick'); };

// ================= 延迟徽章（右上角） =================
setInterval(() => {
  const ms = state.conn?.ws?.readyState === 1 ? state.conn.ping : null;
  const q = ms == null ? 1 : ms < 60 ? 4 : ms < 100 ? 3 : ms < 180 ? 2 : 1;
  $$('.ping-badge').forEach((b) => {
    b.dataset.q = q;
    b.querySelector('span').textContent = ms == null ? '--' : ms;
    b.title = t('title.ping');
  });
}, 500);

// ================= 全屏 =================
function enterFullscreen() {
  const el = document.documentElement;
  if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen().catch(() => {});
}
$$('.fs-btn').forEach((b) => (b.onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else enterFullscreen();
}));
document.addEventListener('fullscreenchange', () => {
  $$('.fs-btn').forEach((b) => (b.title = t(document.fullscreenElement ? 'title.exitFullscreen' : 'title.fullscreen')));
});

// ================= 语言 =================
/** 登录后：账号已有语言则采用它；没有则把当前语言写入账号 */
function adoptAccountLang(user) {
  const l = normalizeLang(user?.lang);
  if (l) setLang(l);
  else if (user && state.conn) send({ t: 'profile', lang: getLang() });
  else if (user) state.pendingLang = getLang();
}

/** 语言切换器（登录页左下角 / 设置弹窗） */
document.addEventListener('click', (e) => {
  const b = e.target.closest('.lang-seg button');
  if (!b) return;
  setLang(b.dataset.lang);
  if (state.user) {
    state.user.lang = b.dataset.lang;
    send({ t: 'profile', lang: b.dataset.lang }); // 写回该账号记录
  }
});

/** 语言变化后重绘动态内容 */
onLangChange(() => {
  $$('.swatches button').forEach((b, i) => (b.title = t('skin.' + (i % SKINS.length))));
  if (state.user) renderMe();
  renderRooms();
  loadLeaderboard();
  if (state.room) renderRoom();
  if (state.game) {
    $('#hud-map').textContent = `${mapName(state.game.mapId)} · ${t(state.game.mode === 'team' ? 'mode.team' : 'mode.ffa')}`;
    buildHudPlayers();
  }
  if (!$('#create-modal').classList.contains('hidden')) openCreate();
});

/** 把房间成员名按语言转换（机器人代号），用于 3D 台座标签 */
function localizedRoom(r) {
  return { ...r, members: r.members.map((m) => ({ ...m, name: displayName(m.name, m.isBot) })) };
}

applyI18n();
boot();
