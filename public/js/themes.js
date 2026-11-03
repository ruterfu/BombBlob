// 角色外观、地图主题配色、头像与地图缩略图
import { ICONS } from './icons.js';

export const SKINS = [
  { name: '赤焰', color: '#e5484d' },
  { name: '苍蓝', color: '#3d8bff' },
  { name: '翠影', color: '#2fb872' },
  { name: '琥珀', color: '#f0a33a' },
  { name: '紫晶', color: '#8b5cf6' },
  { name: '熔橙', color: '#f26b38' },
  { name: '青钢', color: '#22b3c4' },
  { name: '绯红', color: '#d9467f' },
];

export const HATS = ['无', '战术头带', '王冠', '耳机', '犄角', '鸭舌帽', '贝雷帽', '护目镜', '头巾', '牛仔帽', '骑士盔', '光环', '礼帽', '巫师帽', '冰晶冠', '烈焰冠', '龙角', '星环'];
export const BASE_HATS = 6; // 0–5 按等级免费解锁，6 起为商店装饰

export const TEAM_COLORS = ['#ff5a5f', '#3d9bff'];
export const TEAM_NAMES = ['红队', '蓝队'];

export const THEMES = {
  meadow: {
    floorA: '#5d8545', floorB: '#557c3e', ice: '#a9d4ee',
    wall: '#6a6c72', wallTop: '#8c8e94',
    crate: '#9a6a3a', crateLine: '#4a2f18',
    liquid: '#3b8fc4', liquidEmissive: '#000000',
    bush: '#3e7a37', conveyor: '#3a3d44', tele: '#6fe3ff',
    flameOuter: '#ff7a1f', flameInner: '#ffd27a',
  },
  frost: {
    floorA: '#dbe6f0', floorB: '#ccdae7', ice: '#8fc3e6',
    wall: '#556e86', wallTop: '#a9bccd',
    crate: '#7cb4d8', crateLine: '#2b5f87',
    liquid: '#3c9bd0', liquidEmissive: '#0d4a73',
    bush: '#4c7a6a', conveyor: '#3a3d44', tele: '#7dfcff',
    flameOuter: '#4fb4ff', flameInner: '#e8f7ff',
  },
  jungle: {
    floorA: '#4d7c3b', floorB: '#447234', ice: '#a9d4ee',
    wall: '#6c6253', wallTop: '#8d8374',
    crate: '#7a5530', crateLine: '#3f2a15',
    liquid: '#2f8a95', liquidEmissive: '#000000',
    bush: '#2c6b2a', conveyor: '#3a3d44', tele: '#7dfcff',
    flameOuter: '#ff8a2a', flameInner: '#ffe08a',
  },
  neon: {
    floorA: '#151228', floorB: '#1b1733', ice: '#3d6dff',
    wall: '#2b2457', wallTop: '#ff3d9a', wallEmissive: '#14082a',
    crate: '#1fb6e0', crateLine: '#0a4d63', crateEmissive: '#05303f',
    liquid: '#05040f', liquidEmissive: '#000000',
    bush: '#3b2f8a', conveyor: '#2a2550', tele: '#7dfcff',
    flameOuter: '#d24bff', flameInner: '#f6d8ff',
  },
  foundry: {
    floorA: '#3b3e45', floorB: '#34373d', ice: '#a9d4ee',
    wall: '#4a4e57', wallTop: '#a8721f',
    crate: '#5d6672', crateLine: '#262b32',
    liquid: '#ff6a1f', liquidEmissive: '#ff4a0a',
    bush: '#5b5f66', conveyor: '#25282e', tele: '#ffb347',
    flameOuter: '#ff6a1f', flameInner: '#ffd27a',
  },
  desert: {
    floorA: '#c9a46a', floorB: '#bf9a5f', ice: '#a9d4ee',
    wall: '#8a6646', wallTop: '#b98f63',
    crate: '#9a6a3a', crateLine: '#4a2f18',
    liquid: '#2fa3a8', liquidEmissive: '#000000',
    bush: '#7d8a3a', conveyor: '#3a3d44', tele: '#6fe3ff',
    flameOuter: '#ff7a1f', flameInner: '#ffe0a0',
  },
  harbor: {
    floorA: '#323a44', floorB: '#2c343d', ice: '#a9d4ee',
    wall: '#3f4854', wallTop: '#d1a52a',
    crate: '#3f6f8f', crateLine: '#1b3345',
    liquid: '#123650', liquidEmissive: '#061a2a',
    bush: '#2f4a3a', conveyor: '#1e2328', tele: '#6fe3ff',
    flameOuter: '#ff7a1f', flameInner: '#ffd27a',
  },
  temple: {
    floorA: '#e6d9bf', floorB: '#dccfb3', ice: '#9fd6f0',
    wall: '#b3a283', wallTop: '#f2e6c8',
    crate: '#c08a4a', crateLine: '#5a3a1a',
    liquid: '#86c9ee', liquidEmissive: '#000000',
    bush: '#7aa36a', conveyor: '#3a3d44', tele: '#ffcf5a',
    flameOuter: '#ff7a1f', flameInner: '#ffe6a8',
  },
};
THEMES.candy = THEMES.foundry; // 兼容旧 id

export const POWERUPS = {
  bomb: { icon: 'bomb', name: '炸弹 · 可连放 +1', color: '#5b7cff' },
  fire: { icon: 'flame', name: '爆炸威力 +1', color: '#ff7a1f' },
  max: { icon: 'burst', name: '威力满级', color: '#ff3b3b' },
  speed: { icon: 'shoe', name: '红色跑鞋 · 速度 +5%', color: '#ff3b3b' },
  slow: { icon: 'shoe', name: '绿色跑鞋 · 速度 -5%', color: '#2fd06a' },
  kick: { icon: 'kick', name: '踢弹', color: '#c9a04a' },
  shield: { icon: 'shield', name: '护盾 · 免疫一次伤害', color: '#4fb3ff' },
};

/** 威力（每个方向的格数）→ 十字覆盖尺寸，例如 1 → "3×3" */
export const powerSize = (r) => `${2 * r + 1}×${2 * r + 1}`;

/** 在 2D canvas 上画角色头像（列表、HUD 使用） */
export function drawAvatar(ctx, cx, cy, r, skin, hat, opts = {}) {
  const color = (SKINS[skin] || SKINS[0]).color;
  ctx.save();
  ctx.translate(cx, cy);
  // 身体：高光 + 暗部
  const g = ctx.createRadialGradient(-r * 0.4, -r * 0.45, r * 0.05, 0, 0, r * 1.15);
  g.addColorStop(0, shade(color, 0.55));
  g.addColorStop(0.35, color);
  g.addColorStop(1, shade(color, -0.55));
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.ellipse(0, r * 0.1, r * 0.95, r * 0.86, 0, 0, Math.PI * 2);
  ctx.fill();
  // 边缘光
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.lineWidth = Math.max(1, r * 0.06);
  ctx.beginPath();
  ctx.ellipse(0, r * 0.1, r * 0.9, r * 0.81, 0, Math.PI * 1.1, Math.PI * 1.6);
  ctx.stroke();
  // 眼睛：竖向胶囊 + 斜眉，带一点态度
  for (const s of [-1, 1]) {
    ctx.fillStyle = '#f4f6fb';
    roundRect(ctx, s * r * 0.3 - r * 0.1, -r * 0.18, r * 0.2, r * 0.36, r * 0.1);
    ctx.fill();
    ctx.fillStyle = '#14161f';
    roundRect(ctx, s * r * 0.3 - r * 0.055 + s * r * 0.02, -r * 0.08, r * 0.11, r * 0.22, r * 0.055);
    ctx.fill();
    ctx.strokeStyle = shade(color, -0.65);
    ctx.lineWidth = Math.max(1.2, r * 0.08);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(s * r * 0.48, -r * 0.3);
    ctx.lineTo(s * r * 0.16, -r * 0.24);
    ctx.stroke();
  }
  drawHat2D(ctx, r, hat, color);
  if (opts.dead) {
    ctx.fillStyle = 'rgba(10,12,20,0.6)';
    ctx.beginPath();
    ctx.ellipse(0, r * 0.1, r * 0.98, r * 0.9, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function drawHat2D(ctx, r, hat, color) {
  ctx.save();
  switch (hat) {
    case 1: { // 战术头带
      ctx.fillStyle = '#1d2028';
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.42, r * 0.9, r * 0.13, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#e5484d';
      ctx.fillRect(-r * 0.12, -r * 0.5, r * 0.24, r * 0.15);
      ctx.strokeStyle = '#1d2028';
      ctx.lineWidth = r * 0.1;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(r * 0.85, -r * 0.4);
      ctx.lineTo(r * 1.1, -r * 0.15);
      ctx.stroke();
      break;
    }
    case 2: { // 王冠（金属）
      const g = ctx.createLinearGradient(0, -r * 1.05, 0, -r * 0.6);
      g.addColorStop(0, '#fff2b8');
      g.addColorStop(1, '#b8861f');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(-r * 0.4, -r * 0.62);
      ctx.lineTo(-r * 0.44, -r * 0.98);
      ctx.lineTo(-r * 0.2, -r * 0.8);
      ctx.lineTo(0, -r * 1.06);
      ctx.lineTo(r * 0.2, -r * 0.8);
      ctx.lineTo(r * 0.44, -r * 0.98);
      ctx.lineTo(r * 0.4, -r * 0.62);
      ctx.closePath();
      ctx.fill();
      break;
    }
    case 3: { // 耳机
      ctx.strokeStyle = '#1d2028';
      ctx.lineWidth = r * 0.12;
      ctx.beginPath();
      ctx.arc(0, -r * 0.05, r * 0.88, Math.PI * 1.12, Math.PI * 1.88);
      ctx.stroke();
      for (const s of [-1, 1]) {
        ctx.fillStyle = '#2a2e38';
        roundRect(ctx, s * r * 0.88 - r * 0.14, -r * 0.2, r * 0.28, r * 0.42, r * 0.1);
        ctx.fill();
        ctx.fillStyle = '#3df2ff';
        ctx.fillRect(s * r * 0.88 - r * 0.03, -r * 0.08, r * 0.06, r * 0.18);
      }
      break;
    }
    case 4: // 犄角
      ctx.fillStyle = '#e9e1d2';
      for (const s of [-1, 1]) {
        ctx.beginPath();
        ctx.moveTo(s * r * 0.48, -r * 0.55);
        ctx.quadraticCurveTo(s * r * 0.85, -r * 0.9, s * r * 0.62, -r * 1.15);
        ctx.lineTo(s * r * 0.26, -r * 0.68);
        ctx.closePath();
        ctx.fill();
      }
      break;
    case 5: // 鸭舌帽
      ctx.fillStyle = '#1d2028';
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.55, r * 0.72, r * 0.45, 0, Math.PI, Math.PI * 2);
      ctx.fill();
      ctx.fillRect(-r * 0.05, -r * 0.6, r * 0.98, r * 0.11);
      ctx.fillStyle = color;
      ctx.fillRect(-r * 0.4, -r * 0.82, r * 0.3, r * 0.08);
      break;
    case 6: // 贝雷帽
      ctx.fillStyle = '#7a1f2b';
      ctx.beginPath();
      ctx.ellipse(r * 0.12, -r * 0.72, r * 0.82, r * 0.28, -0.22, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillRect(r * 0.02, -r * 1.06, r * 0.08, r * 0.14);
      break;
    case 7: { // 护目镜
      ctx.fillStyle = '#1d2028';
      ctx.fillRect(-r * 0.92, -r * 0.6, r * 1.84, r * 0.14);
      for (const sx of [-1, 1]) {
        ctx.fillStyle = '#9aa3b2';
        ctx.beginPath();
        ctx.arc(sx * r * 0.3, -r * 0.55, r * 0.24, 0, Math.PI * 2);
        ctx.fill();
        const g = ctx.createRadialGradient(sx * r * 0.36, -r * 0.62, r * 0.02, sx * r * 0.3, -r * 0.55, r * 0.19);
        g.addColorStop(0, '#ffe2a0');
        g.addColorStop(1, '#ff8a00');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(sx * r * 0.3, -r * 0.55, r * 0.18, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
    case 8: // 头巾
      ctx.fillStyle = '#2f6fd6';
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.42, r * 0.92, r * 0.62, 0, Math.PI, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#f4f6fb';
      for (const [x, y] of [[-0.5, -0.6], [-0.1, -0.85], [0.3, -0.7], [0.6, -0.5], [-0.25, -0.55], [0.1, -0.5]]) {
        ctx.beginPath();
        ctx.arc(x * r, y * r, r * 0.05, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = '#2f6fd6';
      ctx.beginPath();
      ctx.moveTo(r * 0.85, -r * 0.45);
      ctx.lineTo(r * 1.2, -r * 0.2);
      ctx.lineTo(r * 1.05, -r * 0.05);
      ctx.closePath();
      ctx.fill();
      break;
    case 9: // 牛仔帽
      ctx.fillStyle = '#8a5a2b';
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.7, r * 1.15, r * 0.18, 0, 0, Math.PI * 2);
      ctx.fill();
      roundRect(ctx, -r * 0.45, -r * 1.15, r * 0.9, r * 0.5, r * 0.15);
      ctx.fill();
      ctx.fillStyle = '#2a1a10';
      ctx.fillRect(-r * 0.46, -r * 0.82, r * 0.92, r * 0.1);
      break;
    case 10: { // 骑士盔
      const g = ctx.createLinearGradient(0, -r * 1.05, 0, -r * 0.3);
      g.addColorStop(0, '#eef2f8');
      g.addColorStop(1, '#7d8695');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.3, r * 0.98, r * 0.78, 0, Math.PI, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#d0303a';
      ctx.beginPath();
      ctx.moveTo(-r * 0.08, -r * 1.02);
      ctx.quadraticCurveTo(r * 0.5, -r * 1.5, r * 0.75, -r * 1.05);
      ctx.quadraticCurveTo(r * 0.35, -r * 1.12, r * 0.1, -r * 0.98);
      ctx.closePath();
      ctx.fill();
      break;
    }
    case 11: // 光环
      ctx.strokeStyle = '#ffd36f';
      ctx.shadowColor = '#ffc94a';
      ctx.shadowBlur = r * 0.4;
      ctx.lineWidth = r * 0.1;
      ctx.beginPath();
      ctx.ellipse(0, -r * 1.12, r * 0.55, r * 0.15, 0, 0, Math.PI * 2);
      ctx.stroke();
      break;
    case 12: // 礼帽
      ctx.save();
      ctx.rotate(-0.1);
      ctx.fillStyle = '#15161b';
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.72, r * 0.78, r * 0.12, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillRect(-r * 0.45, -r * 1.42, r * 0.9, r * 0.72);
      ctx.fillStyle = '#9c1d2a';
      ctx.fillRect(-r * 0.45, -r * 0.92, r * 0.9, r * 0.13);
      ctx.restore();
      break;
    case 13: // 巫师帽
      ctx.fillStyle = '#3b2a7a';
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.7, r * 1.0, r * 0.16, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(-r * 0.55, -r * 0.72);
      ctx.quadraticCurveTo(-r * 0.1, -r * 1.3, r * 0.35, -r * 1.75);
      ctx.lineTo(r * 0.55, -r * 0.72);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = '#ffe08a';
      for (const [x, y] of [[0.05, -0.95], [0.2, -1.25], [-0.15, -1.1]]) {
        ctx.beginPath();
        ctx.arc(x * r, y * r, r * 0.05, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    case 14: // 冰晶冠
      ctx.fillStyle = 'rgba(191,239,255,0.92)';
      ctx.shadowColor = '#5fd0ff';
      ctx.shadowBlur = r * 0.3;
      for (let k = -3; k <= 3; k++) {
        const h = k % 2 ? 0.35 : 0.55;
        ctx.beginPath();
        ctx.moveTo(k * r * 0.14 - r * 0.07, -r * 0.68);
        ctx.lineTo(k * r * 0.14, -r * (0.68 + h));
        ctx.lineTo(k * r * 0.14 + r * 0.07, -r * 0.68);
        ctx.closePath();
        ctx.fill();
      }
      break;
    case 15: { // 烈焰冠
      ctx.fillStyle = '#3a2a1a';
      ctx.fillRect(-r * 0.5, -r * 0.74, r * 1.0, r * 0.1);
      ctx.shadowColor = '#ff5a0a';
      ctx.shadowBlur = r * 0.4;
      for (let k = -2; k <= 2; k++) {
        const g = ctx.createLinearGradient(0, -r * 1.25, 0, -r * 0.7);
        g.addColorStop(0, '#ffe08a');
        g.addColorStop(1, '#ff5a0a');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.moveTo(k * r * 0.2 - r * 0.09, -r * 0.72);
        ctx.quadraticCurveTo(k * r * 0.2 - r * 0.1, -r * 1.0, k * r * 0.2, -r * (k % 2 ? 1.12 : 1.3));
        ctx.quadraticCurveTo(k * r * 0.2 + r * 0.1, -r * 1.0, k * r * 0.2 + r * 0.09, -r * 0.72);
        ctx.closePath();
        ctx.fill();
      }
      break;
    }
    case 16: // 龙角
      for (const sx of [-1, 1]) {
        ctx.fillStyle = '#2a1418';
        ctx.beginPath();
        ctx.moveTo(sx * r * 0.35, -r * 0.6);
        ctx.quadraticCurveTo(sx * r * 0.95, -r * 0.95, sx * r * 0.7, -r * 1.45);
        ctx.quadraticCurveTo(sx * r * 0.7, -r * 1.0, sx * r * 0.12, -r * 0.75);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = '#e8b34a';
        ctx.beginPath();
        ctx.arc(sx * r * 0.7, -r * 1.42, r * 0.06, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    case 17: // 星环
      ctx.strokeStyle = 'rgba(159,216,255,0.55)';
      ctx.lineWidth = r * 0.04;
      ctx.beginPath();
      ctx.ellipse(0, -r * 0.05, r * 1.25, r * 0.3, -0.2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#fff3c8';
      ctx.shadowColor = '#ffe08a';
      ctx.shadowBlur = r * 0.35;
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2 + 0.4;
        const x = Math.cos(a) * r * 1.25, y = -r * 0.05 + Math.sin(a) * r * 0.3;
        const xr = x * Math.cos(-0.2) - (y + r * 0.05) * Math.sin(-0.2), yr = x * Math.sin(-0.2) + (y + r * 0.05) * Math.cos(-0.2) - r * 0.05;
        ctx.beginPath();
        ctx.arc(xr, yr, r * 0.08, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    default:
      break;
  }
  ctx.restore();
}

export function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const f = (c) => Math.max(0, Math.min(255, Math.round(amt < 0 ? c * (1 + amt) : c + (255 - c) * amt)));
  r = f(r); g = f(g); b = f(b);
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
}

export { ICONS };
export function drawMapPreview(canvas, map) {
  const th = THEMES[map.theme] || THEMES.meadow;
  const rows = map.rows;
  const h = rows.length, w = rows[0].length;
  const ctx = canvas.getContext('2d');
  const s = Math.min(canvas.width / w, canvas.height / (h + 0.4));
  const ox = (canvas.width - s * w) / 2, oy = (canvas.height - s * (h + 0.4)) / 2 + s * 0.4;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#0d1017";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const box = (x, y, top, side, inset = 0, lift = 0.28) => {
    const px = ox + x * s + inset, py = oy + y * s + inset - s * lift, sz = s - inset * 2;
    ctx.fillStyle = side;
    ctx.fillRect(px, py + sz * 0.25, sz, sz);
    ctx.fillStyle = top;
    ctx.fillRect(px, py, sz, sz * 0.92);
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.fillRect(px, py, sz, Math.max(1, sz * 0.14));
  };
  // 地面
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const c = rows[y][x];
      let col = (x + y) % 2 ? th.floorA : th.floorB;
      if (c === 'i' || c === 'j') col = th.ice;
      if ('^v<>'.includes(c)) col = th.conveyor;
      ctx.fillStyle = col;
      ctx.fillRect(ox + x * s, oy + y * s, s + 0.5, s + 0.5);
      if (c === '~') {
        ctx.fillStyle = th.liquid;
        ctx.fillRect(ox + x * s, oy + y * s, s + 0.5, s + 0.5);
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.lineWidth = Math.max(1, s * 0.08);
        ctx.beginPath();
        ctx.moveTo(ox + x * s + s * 0.15, oy + y * s + s * 0.55);
        ctx.quadraticCurveTo(ox + x * s + s * 0.35, oy + y * s + s * 0.35, ox + x * s + s * 0.55, oy + y * s + s * 0.55);
        ctx.stroke();
      }
    }
  }
  // 立体物件（按行从上到下画，产生遮挡）
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const c = rows[y][x];
      const cx = ox + x * s + s / 2, cy = oy + y * s + s / 2;
      if (c === '#') {
        box(x, y, th.wallTop, th.wall);
      } else if (c === 'Y' || c === 'H') {
        box(x, y, c === 'H' ? th.wallTop : '#3f6a34', c === 'H' ? shade(th.wall, -0.2) : '#2a4a24', c === 'Y' ? s * 0.12 : 0, c === 'H' ? 0.45 : 0.3);
      } else if (c === 'm') {
        box(x, y, '#7d8590', '#3d434d', s * 0.08, 0.24);
      } else if (c === 'e') {
        ctx.fillStyle = '#7a1510';
        ctx.beginPath(); ctx.arc(cx, cy - s * 0.1, s * 0.4, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#d03026';
        ctx.beginPath(); ctx.arc(cx, cy - s * 0.18, s * 0.36, 0, Math.PI * 2); ctx.fill();
      } else if (c === 'x' || c === '*' || c === 'j') {
        box(x, y, th.crate, th.crateLine, s * 0.1, 0.22);
        ctx.strokeStyle = th.crateLine;
        ctx.lineWidth = Math.max(1, s * 0.09);
        const i = s * 0.22;
        ctx.beginPath();
        ctx.moveTo(ox + x * s + i, oy + y * s + i - s * 0.22);
        ctx.lineTo(ox + x * s + s - i, oy + y * s + s - i - s * 0.3);
        ctx.stroke();
      } else if (c === 'b') {
        ctx.fillStyle = shade(th.bush, -0.25);
        ctx.beginPath(); ctx.arc(cx, cy, s * 0.48, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = th.bush;
        ctx.beginPath(); ctx.arc(cx, cy - s * 0.12, s * 0.42, 0, Math.PI * 2); ctx.fill();
      } else if (c >= '1' && c <= '9') {
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, s * 0.55);
        g.addColorStop(0, '#ffffff');
        g.addColorStop(0.4, th.tele);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(cx - s, cy - s, s * 2, s * 2);
      } else if ('^v<>'.includes(c)) {
        ctx.fillStyle = 'rgba(255,255,255,0.6)';
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate({ '^': 0, '>': Math.PI / 2, v: Math.PI, '<': -Math.PI / 2 }[c]);
        ctx.beginPath(); ctx.moveTo(0, -s * 0.3); ctx.lineTo(s * 0.28, s * 0.15); ctx.lineTo(-s * 0.28, s * 0.15); ctx.fill();
        ctx.restore();
      }
    }
  }
  // 暗角
  const v = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, canvas.width * 0.3, canvas.width / 2, canvas.height / 2, canvas.width * 0.75);
  v.addColorStop(0, 'rgba(0,0,0,0)');
  v.addColorStop(1, "rgba(0,0,0,0.45)");
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}
