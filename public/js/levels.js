// 等级、段位与头饰解锁。
// 数据来源：服务器 welcome 消息下发的等级表（来自数据库 levels 表）；未收到前使用与 db/init.sql 相同的默认值。

let EXP = []; // 索引 = level - 1：达到该等级所需的累计经验
let TIER = []; // 段位：0 新兵 … 6 大师
export let HAT_UNLOCK = { 0: 1, 1: 2, 3: 3, 4: 5, 5: 8, 2: 12 };

(function defaults() {
  const mins = [1, 5, 10, 15, 20, 30, 40];
  let cum = 0;
  for (let lv = 1; lv <= 50; lv++) {
    if (lv > 1) cum += 100 + 50 * (lv - 2);
    EXP.push(cum);
    TIER.push(mins.filter((m) => lv >= m).length - 1);
  }
})();

/** 使用服务器下发的等级表：[{ level, exp, tier, hats: [] }] */
export function setLevelTable(rows) {
  if (!Array.isArray(rows) || !rows.length) return;
  EXP = rows.map((r) => r.exp);
  TIER = rows.map((r) => r.tier);
  HAT_UNLOCK = { 0: 1 };
  for (const r of rows) for (const h of r.hats || []) HAT_UNLOCK[h] = r.level;
}

/** 达到 lv 级所需累计经验；超过等级表后按同一曲线无限延伸（每级 +50），与服务器 bb_level 一致 */
export function expFor(lv) {
  const n = EXP.length;
  if (lv <= n) return EXP[Math.max(0, lv - 1)] ?? 0;
  const d = (n > 1 ? EXP[n - 1] - EXP[n - 2] : 50) + 50;
  const m = lv - n;
  return EXP[n - 1] + 25 * m * m + (d - 25) * m;
}

export function levelOf(exp) {
  let lv = 1;
  while (lv < EXP.length && exp >= EXP[lv]) lv++;
  if (lv === EXP.length) while (exp >= expFor(lv + 1)) lv++;
  return lv;
}

/** 当前等级的起点经验 / 下一级所需经验 */
export const levelFloor = (lv) => expFor(lv);
export const levelCeil = (lv) => expFor(lv + 1);

const TIER_COLORS = ['#8a93a8', '#cd7f32', '#c9d1e0', '#ffb547', '#36d6ff', '#b07cff', '#ff4d5e'];

export function tierOf(lv) {
  const index = TIER[Math.max(0, Math.min(TIER.length - 1, lv - 1))] ?? 0;
  return { index, color: TIER_COLORS[index] };
}

// 商店装饰目录（服务器 welcome 下发）：[{ id, code, level, price }]
let SHOP = [];
export function setShop(list) { if (Array.isArray(list)) SHOP = list; }
export const shopItems = () => SHOP;
export const shopItem = (id) => SHOP.find((x) => x.id === id);

/** 基础头饰按等级解锁；商店装饰需要已购买 */
export function hatUnlocked(hat, lv, items = []) {
  if (shopItem(hat)) return items.includes(hat);
  return lv >= (HAT_UNLOCK[hat] ?? 1);
}

/** 当前等级进度 0~1 */
export function levelProgress(exp) {
  const lv = levelOf(exp);
  const lo = levelFloor(lv), hi = levelCeil(lv);
  return Math.max(0, Math.min(1, (exp - lo) / (hi - lo)));
}

/** 等级徽章 HTML */
export function levelBadge(lv) {
  const { color } = tierOf(lv);
  return `<span class="lvb" style="--tc:${color}">LV.${lv}</span>`;
}
