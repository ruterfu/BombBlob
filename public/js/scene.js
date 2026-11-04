// three.js 3D 渲染：只负责把服务器下发的权威状态画出来（插值 + 特效），不做任何判定。
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { SKINS, THEMES, POWERUPS, TEAM_COLORS, BOMB_FX, shade } from './themes.js';
import { getMsaa, applyMsaa } from './gfx.js';
import { drawIcon } from './icons.js';
import { Predictor } from './predict.js';

/** 简单的帧计时器 */
class FrameClock {
  constructor() { this.last = performance.now(); this.elapsedTime = 0; }
  getDelta() {
    const now = performance.now();
    const dt = (now - this.last) / 1000;
    this.last = now;
    this.elapsedTime += dt;
    return dt;
  }
}

const FACING_ROT = { d: 0, r: Math.PI / 2, u: Math.PI, l: -Math.PI / 2 };
const MAX_PARTICLES = 600;
const HIT_RED = new THREE.Color(0.95, 0.05, 0.1);

// 每个主题的天空、周边环境与氛围粒子（偏电影感的配色）
const ENV = {
  meadow: { sky: ['#2f5f9a', '#e9c79a'], surround: 'sea', sea: '#2f6f8f', land: '#55703f', deco: 'tree', mote: '#ffe7b0', moteKind: 'dust', bloom: 0.35, sun: '#ffe2b8', dark: false },
  frost: { sky: ['#3d5f86', '#d9e6f2'], surround: 'snow', sea: '#c7d6e3', land: '#dfe8f0', deco: 'pine', mote: '#ffffff', moteKind: 'snow', bloom: 0.35, sun: '#e8f2ff', dark: false },
  jungle: { sky: ['#1f4a52', '#b9c99a'], surround: 'sea', sea: '#24636b', land: '#3f5f30', deco: 'palm', mote: '#d8ff7a', moteKind: 'firefly', bloom: 0.5, sun: '#fff0c8', dark: false },
  neon: { sky: ['#05030f', '#2a1150'], surround: 'grid', sea: '#08061a', land: '#141030', deco: 'crystal', mote: '#7dfcff', moteKind: 'spark', bloom: 0.95, sun: '#d8c8ff', dark: true },
  foundry: { sky: ['#0e0d12', '#4a2614'], surround: 'lava', sea: '#ff5a1f', land: '#25262b', deco: 'pipe', mote: '#ffb040', moteKind: 'ember', bloom: 0.85, sun: '#ffd2a8', dark: true },
  desert: { sky: ['#b45a32', '#f4d49c'], surround: 'snow', sea: '#d0ac74', land: '#c49c62', deco: 'palm', mote: '#ffe0a8', moteKind: 'dust', bloom: 0.35, sun: '#ffd6a0', dark: false },
  harbor: { sky: ['#050a14', '#1d3552'], surround: 'sea', sea: '#0f2a40', land: '#1f262e', deco: 'pipe', mote: '#9fd8ff', moteKind: 'spark', bloom: 0.75, sun: '#c4d8ff', dark: true },
  temple: { sky: ['#5f86d0', '#ffe4c8'], surround: 'sea', sea: '#e9eff8', land: '#d8ccb0', deco: 'crystal', mote: '#fff3c8', moteKind: 'dust', bloom: 0.4, sun: '#fff0d8', dark: false },
  sakura: { sky: ['#6a7fc8', '#ffd6e4'], surround: 'sea', sea: '#7fb8c8', land: '#7a9a5a', deco: 'sakura', mote: '#ffc2d8', moteKind: 'dust', bloom: 0.4, sun: '#ffe8f0', dark: false },
  mine: { sky: ['#07080c', '#2a2016'], surround: 'lava', sea: '#3a2a1a', land: '#2a2420', deco: 'rock', mote: '#ffcf6a', moteKind: 'ember', bloom: 0.7, sun: '#ffd8a0', dark: true },
  glacier: { sky: ['#061428', '#1f6a6a'], surround: 'snow', sea: '#b8d4e8', land: '#d4e4f0', deco: 'pine', mote: '#9affd8', moteKind: 'snow', bloom: 0.65, sun: '#c8f0ff', dark: true },
  starport: { sky: ['#02030a', '#1a2a5a'], surround: 'grid', sea: '#060a1a', land: '#10162a', deco: 'crystal', mote: '#9fd8ff', moteKind: 'spark', bloom: 0.9, sun: '#d0e0ff', dark: true },
  arena: { sky: ['#e07a3a', '#ffe6b0'], surround: 'snow', sea: '#d8b47a', land: '#c8a068', deco: 'palm', mote: '#fff0c0', moteKind: 'dust', bloom: 0.4, sun: '#fff0c8', dark: false },
  volcano: { sky: ['#120606', '#5a1a0a'], surround: 'lava', sea: '#ff4a10', land: '#2a1a16', deco: 'rock', mote: '#ff8a3a', moteKind: 'ember', bloom: 0.85, sun: '#ffb890', dark: true },
};
ENV.candy = ENV.foundry;
ENV.lava = ENV.foundry;

export const pbr = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.05, ...extra });
const toonMat = pbr; // 兼容旧调用

/** 环境反射贴图（让材质有质感） */
const envCache = new WeakMap();
export function envMapFor(renderer) {
  if (!envCache.has(renderer)) {
    const pm = new THREE.PMREMGenerator(renderer);
    envCache.set(renderer, pm.fromScene(new RoomEnvironment(), 0.04).texture);
    pm.dispose();
  }
  return envCache.get(renderer);
}

export function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  draw(c.getContext('2d'), w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** 名字标签：深色半透明底 + 细字 */
const q4 = (v) => Math.round(v * 1e4) / 1e4;

export function textSprite(text, color = '#ffffff', dot = null) {
  const tex = canvasTexture(320, 72, (ctx, w, h) => {
    ctx.font = '600 30px "PingFang SC","Microsoft YaHei",sans-serif';
    const dotW = dot ? 30 : 0;
    const tw = Math.min(w - 8, ctx.measureText(text).width + 34 + dotW);
    const x = (w - tw) / 2;
    ctx.fillStyle = 'rgba(10,12,20,0.72)';
    ctx.beginPath();
    ctx.roundRect(x, 12, tw, 46, 8);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.fillRect(x, 12, 4, 46);
    if (dot) {
      // 队伍圆点：带白边与光晕，远处也看得清
      ctx.save();
      ctx.shadowColor = dot;
      ctx.shadowBlur = 10;
      ctx.fillStyle = dot;
      ctx.beginPath();
      ctx.arc(x + 26, 35, 12, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();
    }
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#f4f6fb';
    ctx.fillText(text, w / 2 + 2 + dotW / 2, 36);
  });
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  sp.scale.set(2.1, 0.47, 1);
  sp.renderOrder = 10;
  return sp;
}

/** “这是我”的箭头：倒置的发光棱锥 + 白色描边，始终绘制在最上层 */
function buildMeArrow(color) {
  const g = new THREE.Group();
  const geo = new THREE.ConeGeometry(0.3, 0.52, 4);
  geo.rotateX(Math.PI);
  const core = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true }));
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: '#ffffff', depthTest: false, transparent: true }));
  core.renderOrder = edge.renderOrder = 12;
  g.add(core, edge);
  g.position.y = 1.9;
  return g;
}

/** 墙体纹理：侧面切割石块 + 顶面石板 */
function wallTextures(th) {
  const side = canvasTexture(256, 256, (ctx, w) => {
    ctx.fillStyle = shade(th.wall, -0.45);
    ctx.fillRect(0, 0, w, w);
    const rows = 4, bh = w / rows;
    for (let r = 0; r < rows; r++) {
      const off = r % 2 ? w / 4 : 0;
      for (let c = -1; c < 3; c++) {
        const x = c * (w / 2) + off;
        const k = ((r * 7 + c * 13 + 20) % 5) / 5;
        ctx.fillStyle = shade(th.wall, (k - 0.5) * 0.14);
        ctx.fillRect(x + 3, r * bh + 3, w / 2 - 6, bh - 6);
        ctx.fillStyle = 'rgba(255,255,255,0.07)';
        ctx.fillRect(x + 3, r * bh + 3, w / 2 - 6, 3);
        ctx.fillStyle = 'rgba(0,0,0,0.12)';
        ctx.fillRect(x + 3, r * bh + bh - 7, w / 2 - 6, 4);
      }
    }
    // 细微噪点
    for (let i = 0; i < 900; i++) {
      ctx.fillStyle = `rgba(${Math.random() < 0.5 ? '0,0,0' : '255,255,255'},${Math.random() * 0.06})`;
      ctx.fillRect(Math.random() * w, Math.random() * w, 2, 2);
    }
  });
  const top = canvasTexture(256, 256, (ctx, w) => {
    ctx.fillStyle = shade(th.wallTop, -0.25);
    ctx.fillRect(0, 0, w, w);
    ctx.fillStyle = th.wallTop;
    ctx.fillRect(10, 10, w - 20, w - 20);
    ctx.strokeStyle = 'rgba(0,0,0,0.18)';
    ctx.lineWidth = 3;
    ctx.strokeRect(26, 26, w - 52, w - 52);
    for (let i = 0; i < 1200; i++) {
      ctx.fillStyle = `rgba(${Math.random() < 0.5 ? '0,0,0' : '255,255,255'},${Math.random() * 0.07})`;
      ctx.fillRect(Math.random() * w, Math.random() * w, 2, 2);
    }
  });
  for (const t of [side, top]) t.anisotropy = 8;
  return { side, top };
}

/** 箱子纹理：木板 + 金属包角 */
function crateTexture(th) {
  return canvasTexture(256, 256, (ctx, w) => {
    ctx.fillStyle = shade(th.crate, -0.2);
    ctx.fillRect(0, 0, w, w);
    const planks = 4;
    for (let i = 0; i < planks; i++) {
      ctx.fillStyle = shade(th.crate, ((i * 37) % 5 - 2) * 0.05);
      ctx.fillRect(18, 18 + i * ((w - 36) / planks) + 2, w - 36, (w - 36) / planks - 4);
    }
    for (let i = 0; i < 40; i++) {
      ctx.strokeStyle = 'rgba(0,0,0,0.08)';
      ctx.beginPath();
      const y = Math.random() * w;
      ctx.moveTo(18, y);
      ctx.bezierCurveTo(w * 0.3, y + 4, w * 0.6, y - 4, w - 18, y);
      ctx.stroke();
    }
    ctx.strokeStyle = th.crateLine;
    ctx.lineWidth = 18;
    ctx.strokeRect(9, 9, w - 18, w - 18);
    ctx.lineWidth = 12;
    ctx.beginPath();
    ctx.moveTo(24, 24); ctx.lineTo(w - 24, w - 24);
    ctx.stroke();
    ctx.fillStyle = '#9aa0aa';
    for (const [x, y] of [[9, 9], [w - 9, 9], [9, w - 9], [w - 9, w - 9]]) {
      ctx.fillRect(x - 14, y - 14, 28, 28);
      ctx.fillStyle = '#5c616b';
      ctx.fillRect(x - 3, y - 3, 6, 6);
      ctx.fillStyle = '#9aa0aa';
    }
  });
}

function steelTexture() {
  return canvasTexture(256, 256, (ctx, w) => {
    const g = ctx.createLinearGradient(0, 0, w, w);
    g.addColorStop(0, '#6d7480');
    g.addColorStop(1, '#3d434d');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, w);
    ctx.strokeStyle = '#262a31';
    ctx.lineWidth = 14;
    ctx.strokeRect(7, 7, w - 14, w - 14);
    for (let i = 1; i < 4; i++) {
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.fillRect(20, i * 60, w - 40, 6);
      ctx.fillStyle = 'rgba(255,255,255,0.12)';
      ctx.fillRect(20, i * 60 + 6, w - 40, 2);
    }
    ctx.fillStyle = '#ffb547';
    for (let x = 30; x < w - 30; x += 32) {
      ctx.beginPath(); ctx.moveTo(x, w - 34); ctx.lineTo(x + 16, w - 34); ctx.lineTo(x + 8, w - 20); ctx.fill();
    }
    ctx.fillStyle = '#a7aeb9';
    for (const [x, y] of [[22, 22], [w - 22, 22], [22, w - 22], [w - 22, w - 22]]) {
      ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill();
    }
  });
}

function barrelTexture() {
  const tex = canvasTexture(256, 128, (ctx, w, h) => {
    ctx.fillStyle = '#b8261f';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#7a1510';
    ctx.fillRect(0, 14, w, 8);
    ctx.fillRect(0, h - 22, w, 8);
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, h / 2 - 16, w, 32);
    for (let x = -32; x < w; x += 32) {
      ctx.fillStyle = '#ffb547';
      ctx.beginPath();
      ctx.moveTo(x, h / 2 + 16); ctx.lineTo(x + 16, h / 2 + 16); ctx.lineTo(x + 32, h / 2 - 16); ctx.lineTo(x + 16, h / 2 - 16);
      ctx.fill();
    }
  });
  tex.wrapS = THREE.RepeatWrapping;
  return tex;
}

/** 被困倒计时徽章 */
function trapTexture(secs, frac) {
  return canvasTexture(128, 128, (ctx, w) => {
    const c = w / 2;
    ctx.fillStyle = 'rgba(10,12,20,0.75)';
    ctx.beginPath(); ctx.arc(c, c, 50, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.lineWidth = 8;
    ctx.beginPath(); ctx.arc(c, c, 46, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = frac > 0.3 ? '#36d6ff' : '#ff4d5e';
    ctx.beginPath(); ctx.arc(c, c, 46, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0, Math.min(1, frac))); ctx.stroke();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 56px "DIN Condensed","Bahnschrift",sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(secs), c, c + 4);
  });
}

function arrowTexture(color) {
  const tex = canvasTexture(64, 64, (ctx, w) => {
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, w, w);
    // 警示条纹边
    for (let i = -w; i < w * 2; i += 16) {
      ctx.fillStyle = '#d6a12a';
      ctx.beginPath();
      ctx.moveTo(i, 0); ctx.lineTo(i + 8, 0); ctx.lineTo(i + 8 - 6, 6); ctx.lineTo(i - 6, 6);
      ctx.fill();
    }
    ctx.strokeStyle = 'rgba(255,190,80,0.85)';
    ctx.lineWidth = 6;
    ctx.lineCap = 'square';
    for (const oy of [20, 46]) {
      ctx.beginPath();
      ctx.moveTo(16, oy + 8); ctx.lineTo(32, oy - 6); ctx.lineTo(48, oy + 8);
      ctx.stroke();
    }
  });
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

/** 道具徽章：深色六边形 + 彩色光圈 + 线性图标 */
const iconCache = {};
function powerupTexture(type) {
  if (iconCache[type]) return iconCache[type];
  const def = POWERUPS[type] || POWERUPS.bomb;
  iconCache[type] = canvasTexture(128, 128, (ctx, w) => {
    const c = w / 2;
    const hex = (r) => {
      ctx.beginPath();
      for (let k = 0; k < 6; k++) {
        const a = Math.PI / 6 + (k * Math.PI) / 3;
        ctx.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r);
      }
      ctx.closePath();
    };
    // 道具（放进道具栏的）用圆形徽章，普通加成用六边形
    const shape = def.item ? (r) => { ctx.beginPath(); ctx.arc(c, c, r * 0.95, 0, Math.PI * 2); } : hex;
    shape(58);
    ctx.fillStyle = def.color;
    ctx.fill();
    shape(52);
    const g = ctx.createLinearGradient(0, 0, 0, w);
    g.addColorStop(0, '#2a2f3d');
    g.addColorStop(1, '#10131b');
    ctx.fillStyle = g;
    ctx.fill();
    drawIcon(ctx, def.icon, c, c, 62, def.color, 2.4);
  });
  return iconCache[type];
}

let glowTex = null;
export function glowTexture() {
  if (!glowTex) {
    glowTex = canvasTexture(64, 64, (ctx, w) => {
      const g = ctx.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
      g.addColorStop(0, 'rgba(255,255,255,1)');
      g.addColorStop(0.3, 'rgba(255,220,160,0.8)');
      g.addColorStop(1, 'rgba(255,140,40,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, w);
    });
  }
  return glowTex;
}

// 兼容旧接口（已不使用卡通色阶与描边）
export function toonGradient() { return null; }
export function addOutline() { return null; }

/** 角色：高光胶质球体 + 胶囊眼 + 斜眉 */
export function buildBlob(skin, hat) {
  const color = new THREE.Color((SKINS[skin] || SKINS[0]).color);
  const g = new THREE.Group();
  const bodyMat = new THREE.MeshPhysicalMaterial({
    color, roughness: 0.38, metalness: 0.0, clearcoat: 0.6, clearcoatRoughness: 0.2,
    sheen: 0.1, sheenColor: color.clone(), emissive: new THREE.Color(0),
  });
  const body = new THREE.Mesh(new THREE.SphereGeometry(0.36, 40, 30), bodyMat);
  body.scale.set(1, 0.92, 1);
  body.position.y = 0.36;
  body.castShadow = true;
  g.add(body);

  const inner = new THREE.Group();
  body.add(inner);
  const white = new THREE.MeshStandardMaterial({ color: 0xf4f6fb, roughness: 0.25, emissive: 0x222630 });
  const black = new THREE.MeshStandardMaterial({ color: 0x0c0e14, roughness: 0.2 });
  const brow = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.35), roughness: 0.6 });
  const eyeGeo = new THREE.CapsuleGeometry(0.045, 0.07, 6, 12);
  const pupilGeo = new THREE.CapsuleGeometry(0.026, 0.04, 6, 10);
  for (const s of [-1, 1]) {
    const eye = new THREE.Mesh(eyeGeo, white);
    eye.position.set(s * 0.115, 0.05, 0.31);
    eye.scale.z = 0.6;
    inner.add(eye);
    const pupil = new THREE.Mesh(pupilGeo, black);
    pupil.position.set(s * 0.11, 0.035, 0.345);
    pupil.scale.z = 0.6;
    inner.add(pupil);
    const b = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.025, 0.04), brow);
    b.position.set(s * 0.12, 0.16, 0.3);
    b.rotation.z = s * 0.3;
    b.rotation.x = -0.25;
    inner.add(b);
  }
  const footMat = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.45), roughness: 0.5, metalness: 0.1 });
  const feet = [];
  for (const s of [-1, 1]) {
    const f = new THREE.Mesh(new THREE.SphereGeometry(0.11, 14, 10), footMat);
    f.scale.set(1, 0.5, 1.35);
    f.position.set(s * 0.15, 0.05, 0.04);
    f.castShadow = true;
    g.add(f);
    feet.push(f);
  }
  addHat(inner, hat, color);

  const shield = new THREE.Mesh(
    new THREE.SphereGeometry(0.55, 32, 20),
    new THREE.MeshPhysicalMaterial({ color: 0x7fd8ff, transparent: true, opacity: 0.22, roughness: 0.05, metalness: 0, clearcoat: 1, emissive: 0x2a8ad8, emissiveIntensity: 0.5, depthWrite: false }),
  );
  shield.position.y = 0.38;
  shield.visible = false;
  g.add(shield);

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.38, 0.44, 48),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, side: THREE.DoubleSide }),
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.015;
  ring.visible = false;
  g.add(ring);

  return { group: g, body, bodyMat, feet, shield, ring, inner };
}

function addHat(parent, hat, color) {
  const dark = new THREE.MeshStandardMaterial({ color: 0x1b1e26, roughness: 0.55, metalness: 0.2 });
  switch (hat) {
    case 1: { // 战术头带
      const band = new THREE.Mesh(new THREE.TorusGeometry(0.33, 0.035, 10, 40), dark);
      band.rotation.x = Math.PI / 2 - 0.15;
      band.position.y = 0.2;
      band.scale.set(1, 1, 0.9);
      const tag = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.05, 0.02), new THREE.MeshStandardMaterial({ color: 0xe5484d, roughness: 0.4 }));
      tag.position.set(0, 0.22, 0.33);
      const tail = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.03, 0.22), dark);
      tail.position.set(0.08, 0.17, -0.38);
      tail.rotation.y = 0.5;
      parent.add(band, tag, tail);
      break;
    }
    case 2: { // 金属王冠
      const gold = new THREE.MeshStandardMaterial({ color: 0xe8b34a, metalness: 1, roughness: 0.22 });
      const crown = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.14, 0.1, 10, 1, true), gold);
      crown.material.side = THREE.DoubleSide;
      crown.position.y = 0.36;
      parent.add(crown);
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2;
        const spike = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.08, 6), gold);
        spike.position.set(Math.sin(a) * 0.14, 0.45, Math.cos(a) * 0.14);
        parent.add(spike);
      }
      break;
    }
    case 3: { // 耳机
      const arc = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.025, 8, 40, Math.PI), dark);
      arc.position.y = 0.05;
      parent.add(arc);
      for (const s of [-1, 1]) {
        const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.07, 20), dark);
        cup.rotation.z = Math.PI / 2;
        cup.position.set(s * 0.34, 0.03, 0);
        const led = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.075, 16), new THREE.MeshStandardMaterial({ color: 0x3df2ff, emissive: 0x3df2ff, emissiveIntensity: 1.2 }));
        led.rotation.z = Math.PI / 2;
        led.position.set(s * 0.345, 0.03, 0);
        parent.add(cup, led);
      }
      break;
    }
    case 4: { // 犄角
      const bone = new THREE.MeshStandardMaterial({ color: 0xe6dccb, roughness: 0.45 });
      for (const s of [-1, 1]) {
        const horn = new THREE.Mesh(new THREE.ConeGeometry(0.045, 0.2, 12), bone);
        horn.position.set(s * 0.17, 0.33, 0.02);
        horn.rotation.z = -s * 0.5;
        horn.rotation.x = -0.2;
        parent.add(horn);
      }
      break;
    }
    case 5: { // 鸭舌帽
      const cap = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), dark);
      cap.position.y = 0.12;
      cap.scale.set(1.06, 0.78, 1.06);
      const brim = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.02, 20, 1, false, -Math.PI / 2, Math.PI), dark);
      brim.position.set(0, 0.14, 0.27);
      const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.012, 0.012), new THREE.MeshStandardMaterial({ color, roughness: 0.4 }));
      stripe.position.set(0, 0.32, 0.12);
      stripe.rotation.x = -0.6;
      parent.add(cap, brim, stripe);
      break;
    }
    case 6: { // 贝雷帽
      const m = new THREE.MeshStandardMaterial({ color: 0x7a1f2b, roughness: 0.85 });
      const top = new THREE.Mesh(new THREE.SphereGeometry(0.3, 28, 14), m);
      top.scale.set(1.05, 0.32, 1.05);
      top.position.set(0.05, 0.33, -0.02);
      top.rotation.z = -0.25;
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.02, 0.05, 8), m);
      stem.position.set(0.02, 0.43, 0);
      parent.add(top, stem);
      break;
    }
    case 7: { // 护目镜
      const band = new THREE.Mesh(new THREE.TorusGeometry(0.335, 0.03, 10, 40), dark);
      band.rotation.x = Math.PI / 2 - 0.35;
      band.position.y = 0.2;
      parent.add(band);
      const glass = new THREE.MeshPhysicalMaterial({ color: 0xffa630, emissive: 0xff8a00, emissiveIntensity: 0.6, roughness: 0.05, metalness: 0.2, clearcoat: 1 });
      const rim = new THREE.MeshStandardMaterial({ color: 0x9aa3b2, metalness: 0.9, roughness: 0.3 });
      for (const sx of [-1, 1]) {
        const r = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.05, 20), rim);
        r.rotation.x = Math.PI / 2 - 0.55;
        r.position.set(sx * 0.1, 0.28, 0.22);
        const l = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.055, 20), glass);
        l.rotation.copy(r.rotation);
        l.position.copy(r.position);
        parent.add(r, l);
      }
      break;
    }
    case 8: { // 头巾
      const m = new THREE.MeshStandardMaterial({ color: 0x2f6fd6, roughness: 0.7 });
      const cap = new THREE.Mesh(new THREE.SphereGeometry(0.335, 28, 12, 0, Math.PI * 2, 0, Math.PI / 2.3), m);
      cap.position.y = 0.06;
      parent.add(cap);
      const dots = new THREE.MeshStandardMaterial({ color: 0xf4f6fb, roughness: 0.6 });
      for (let k = 0; k < 7; k++) {
        const a = k * 0.9;
        const d = new THREE.Mesh(new THREE.SphereGeometry(0.018, 8, 6), dots);
        d.position.set(Math.sin(a) * 0.22, 0.32, Math.cos(a) * 0.22);
        parent.add(d);
      }
      for (const sx of [-1, 1]) {
        const tail = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.02, 0.2), m);
        tail.position.set(sx * 0.05, 0.12, -0.4);
        tail.rotation.set(0.5, sx * 0.4, 0);
        parent.add(tail);
      }
      break;
    }
    case 9: { // 牛仔帽
      const m = new THREE.MeshStandardMaterial({ color: 0x8a5a2b, roughness: 0.75 });
      const brim = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.025, 36), m);
      brim.position.y = 0.3;
      brim.scale.z = 0.82;
      const crown = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.2, 0.18, 24), m);
      crown.position.y = 0.4;
      const band = new THREE.Mesh(new THREE.CylinderGeometry(0.202, 0.202, 0.035, 24), new THREE.MeshStandardMaterial({ color: 0x2a1a10, roughness: 0.5 }));
      band.position.y = 0.335;
      parent.add(brim, crown, band);
      break;
    }
    case 10: { // 骑士盔
      const steel = new THREE.MeshStandardMaterial({ color: 0xb8c0cc, metalness: 0.95, roughness: 0.25 });
      const helm = new THREE.Mesh(new THREE.SphereGeometry(0.35, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2.2), steel);
      helm.position.y = 0.05;
      const ridge = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.05, 0.5), steel);
      ridge.position.y = 0.38;
      const plume = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.32, 10), new THREE.MeshStandardMaterial({ color: 0xd0303a, roughness: 0.6 }));
      plume.position.set(0, 0.5, -0.12);
      plume.rotation.x = -0.9;
      parent.add(helm, ridge, plume);
      break;
    }
    case 11: { // 光环
      const halo = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.025, 12, 48), new THREE.MeshStandardMaterial({ color: 0xffe08a, emissive: 0xffc94a, emissiveIntensity: 1.6, metalness: 0.6, roughness: 0.2 }));
      halo.rotation.x = Math.PI / 2 - 0.2;
      halo.position.y = 0.6;
      halo.userData.float = 0.6;
      parent.add(halo);
      break;
    }
    case 12: { // 礼帽
      const m = new THREE.MeshStandardMaterial({ color: 0x15161b, roughness: 0.45, metalness: 0.1 });
      const brim = new THREE.Mesh(new THREE.CylinderGeometry(0.27, 0.27, 0.02, 32), m);
      brim.position.y = 0.32;
      const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.16, 0.3, 28), m);
      tube.position.y = 0.48;
      const band = new THREE.Mesh(new THREE.CylinderGeometry(0.163, 0.163, 0.05, 28), new THREE.MeshStandardMaterial({ color: 0x9c1d2a, roughness: 0.5 }));
      band.position.y = 0.36;
      const g = new THREE.Group();
      g.add(brim, tube, band);
      g.rotation.z = -0.12;
      parent.add(g);
      break;
    }
    case 13: { // 巫师帽
      const m = new THREE.MeshStandardMaterial({ color: 0x3b2a7a, roughness: 0.7 });
      const brim = new THREE.Mesh(new THREE.CylinderGeometry(0.36, 0.36, 0.02, 32), m);
      brim.position.y = 0.3;
      const cone = new THREE.Mesh(new THREE.ConeGeometry(0.2, 0.5, 24), m);
      cone.position.set(0, 0.55, -0.03);
      cone.rotation.x = -0.25;
      parent.add(brim, cone);
      const star = new THREE.MeshStandardMaterial({ color: 0xffe08a, emissive: 0xffd24a, emissiveIntensity: 1.4 });
      for (const [x, y, z] of [[0.08, 0.45, 0.15], [-0.07, 0.56, 0.08], [0.04, 0.66, 0.01]]) {
        const st = new THREE.Mesh(new THREE.OctahedronGeometry(0.025), star);
        st.position.set(x, y, z);
        parent.add(st);
      }
      break;
    }
    case 14: { // 冰晶冠
      const ice = new THREE.MeshPhysicalMaterial({ color: 0xbfefff, emissive: 0x5fd0ff, emissiveIntensity: 0.7, roughness: 0.05, transmission: 0.3, transparent: true, opacity: 0.9, clearcoat: 1 });
      for (let k = 0; k < 7; k++) {
        const a = (k / 7) * Math.PI * 2;
        const h = k % 2 ? 0.14 : 0.22;
        const c = new THREE.Mesh(new THREE.ConeGeometry(0.035, h, 5), ice);
        c.position.set(Math.sin(a) * 0.17, 0.33 + h / 2, Math.cos(a) * 0.17);
        c.rotation.set(Math.cos(a) * 0.25, 0, -Math.sin(a) * 0.25);
        parent.add(c);
      }
      const base = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.025, 8, 36), ice);
      base.rotation.x = Math.PI / 2;
      base.position.y = 0.33;
      parent.add(base);
      break;
    }
    case 15: { // 烈焰冠
      const gold = new THREE.MeshStandardMaterial({ color: 0x3a2a1a, metalness: 0.9, roughness: 0.3 });
      const base = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.03, 8, 36), gold);
      base.rotation.x = Math.PI / 2;
      base.position.y = 0.33;
      parent.add(base);
      const fire = new THREE.MeshStandardMaterial({ color: 0xff7a1f, emissive: 0xff5a0a, emissiveIntensity: 1.8, transparent: true, opacity: 0.95 });
      const core = new THREE.MeshStandardMaterial({ color: 0xffe08a, emissive: 0xffd27a, emissiveIntensity: 1.6 });
      const flames = new THREE.Group();
      for (let k = 0; k < 6; k++) {
        const a = (k / 6) * Math.PI * 2;
        const f = new THREE.Mesh(new THREE.ConeGeometry(0.045, 0.2, 8), fire);
        f.position.set(Math.sin(a) * 0.17, 0.44, Math.cos(a) * 0.17);
        const c = new THREE.Mesh(new THREE.ConeGeometry(0.022, 0.11, 8), core);
        c.position.set(Math.sin(a) * 0.17, 0.41, Math.cos(a) * 0.17);
        flames.add(f, c);
      }
      flames.userData.flicker = true;
      parent.add(flames);
      break;
    }
    case 16: { // 龙角
      const horn = new THREE.MeshStandardMaterial({ color: 0x2a1418, roughness: 0.4, metalness: 0.3 });
      const tip = new THREE.MeshStandardMaterial({ color: 0xe8b34a, metalness: 1, roughness: 0.25 });
      for (const sx of [-1, 1]) {
        const curve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(sx * 0.16, 0.26, 0.02),
          new THREE.Vector3(sx * 0.3, 0.42, -0.08),
          new THREE.Vector3(sx * 0.32, 0.58, -0.24),
          new THREE.Vector3(sx * 0.24, 0.66, -0.36),
        ]);
        const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.035, 10), horn);
        // 角根粗、角尖细
        const pos = tube.geometry.attributes.position;
        tube.geometry.computeBoundingBox();
        const t = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.09, 10), tip);
        t.position.set(sx * 0.22, 0.68, -0.4);
        t.rotation.set(-1.2, 0, sx * 0.3);
        parent.add(tube, t);
        void pos;
      }
      break;
    }
    case 17: { // 星环
      const ring = new THREE.Group();
      const track = new THREE.Mesh(new THREE.TorusGeometry(0.46, 0.008, 6, 64), new THREE.MeshBasicMaterial({ color: 0x9fd8ff, transparent: true, opacity: 0.45 }));
      track.rotation.x = Math.PI / 2;
      ring.add(track);
      const star = new THREE.MeshStandardMaterial({ color: 0xfff3c8, emissive: 0xffe08a, emissiveIntensity: 2 });
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2;
        const st = new THREE.Mesh(new THREE.OctahedronGeometry(0.045), star);
        st.position.set(Math.cos(a) * 0.46, 0, Math.sin(a) * 0.46);
        ring.add(st);
      }
      ring.position.y = 0.12;
      ring.rotation.z = 0.25;
      ring.userData.spin = 1.4;
      parent.add(ring);
      break;
    }
    default:
      break;
  }
}

/** 头饰动画（光环浮动、星环旋转、火焰跳动） */
export function animateHat(inner, t) {
  for (const o of inner.children) {
    if (o.userData.spin) o.rotation.y = t * o.userData.spin;
    if (o.userData.float) o.position.y = o.userData.float + Math.sin(t * 2.4) * 0.025;
    if (o.userData.flicker) o.scale.y = 1 + Math.sin(t * 17) * 0.08 + Math.sin(t * 29) * 0.05;
  }
}

/** 炸弹：哑光金属球 + 发光能量环 */
/** 腾飞之翼：一对白色发光的翅膀（挂在角色身上，扇动由每帧动画控制） */
function buildWings(parent) {
  const g = new THREE.Group();
  const shape = new THREE.Shape();
  shape.moveTo(0, 0);
  shape.bezierCurveTo(0.15, 0.25, 0.45, 0.32, 0.55, 0.2);
  shape.bezierCurveTo(0.45, 0.12, 0.42, 0.04, 0.48, -0.04);
  shape.bezierCurveTo(0.3, 0.0, 0.15, -0.02, 0, 0);
  const geo = new THREE.ShapeGeometry(shape);
  const mat = new THREE.MeshStandardMaterial({ color: '#ffffff', emissive: '#bff7e6', emissiveIntensity: 0.8, side: THREE.DoubleSide, transparent: true, opacity: 0.92 });
  for (const s of [1, -1]) {
    const w = new THREE.Mesh(geo, mat);
    w.scale.set(s * 1.7, 1.7, 1);
    w.position.set(s * 0.2, 0.45, -0.22);
    g.add(w);
  }
  parent.add(g);
  return g;
}

/** 整个角色的透明度（透明人：自己 / 队友看到半透明） */
function setAlpha(o, a) {
  if (o.alpha === a) return;
  o.alpha = a;
  o.group.traverse((c) => {
    const m = c.material;
    if (!m || c.isSprite || c.userData.outline) return;
    if (m.userData.baseOp === undefined) { m.userData.baseOp = m.opacity; m.userData.baseTr = m.transparent; }
    m.transparent = a < 1 || m.userData.baseTr;
    m.opacity = m.userData.baseOp * a;
    m.needsUpdate = true;
  });
}

export function buildBomb(skin, style = '') {
  const g = new THREE.Group();
  const c = (SKINS[skin] || SKINS[0]).color;
  const fx = BOMB_FX[style];
  const body = new THREE.Mesh(
    new THREE.SphereGeometry(0.3, 32, 24),
    fx
      ? new THREE.MeshStandardMaterial({ color: fx.body, roughness: fx.rough, metalness: fx.metal, emissive: new THREE.Color(fx.glow), emissiveIntensity: fx.base })
      : new THREE.MeshStandardMaterial({ color: 0x1a1d26, roughness: 0.32, metalness: 0.75, emissive: new THREE.Color(0xff2200), emissiveIntensity: 0 }),
  );
  body.position.y = 0.3;
  body.castShadow = true;
  g.add(body);
  const band = new THREE.Mesh(
    new THREE.TorusGeometry(0.295, 0.03, 10, 40),
    new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 1.4, roughness: 0.3 }),
  );
  band.rotation.x = Math.PI / 2;
  band.position.y = 0.3;
  g.add(band);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.09, 0.09, 12), new THREE.MeshStandardMaterial({ color: 0x8a909c, metalness: 1, roughness: 0.25 }));
  cap.position.y = 0.6;
  g.add(cap);
  const fuse = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.14), new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 0.8 }));
  fuse.position.set(0.03, 0.69, 0);
  fuse.rotation.z = -0.4;
  g.add(fuse);
  const spark = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  spark.position.set(0.07, 0.77, 0);
  spark.scale.setScalar(0.3);
  if (fx) spark.material.color.set(fx.glow);
  g.add(spark);
  if (fx) {
    // 特效炸弹：身上一圈柔光
    const aura = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: fx.glow, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.55 }));
    aura.position.y = 0.3;
    aura.scale.setScalar(1.1);
    g.add(aura);
  }
  return { group: g, body, spark, baseGlow: fx ? fx.base : 0, style };
}

export class GameScene {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.9;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.environment = envMapFor(this.renderer);
    this.scene.environmentIntensity = 0.3;
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.1, 200);
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x445566, 1.4);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xffffff, 2.0);
    this.sun.position.set(-11, 11, 7);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    const sc = this.sun.shadow.camera;
    sc.left = -11; sc.right = 11; sc.top = 11; sc.bottom = -11; sc.near = 1; sc.far = 40;
    this.sun.shadow.bias = -0.0008;
    this.scene.add(this.sun);

    this.board = null;
    this.running = false;
    this.clock = new FrameClock();
    this.shake = 0;
    this.prev = null;
    this.cur = null;
    this.curT = 0;
    this.tickMs = 1000 / 30;
    this.players = new Map();
    this.bombs = new Map();
    this.snaps = [];
    this.latSamples = [];
    this.lat = null;
    this.rtt = 0;
    this.localDir = null;
    this.ghosts = [];
    this.history = [];
    this.renderOffset = { x: 0, y: 0 };
    this.metrics = { fps: 0, corrections: 0, frames: 0, fpsT: performance.now() };
    this.powerupSprites = new Map();
    this.fallingWalls = new Map();
    this.flashes = [];

    // 后期处理（泛光）先渲染到离屏缓冲：渲染器自带的 antialias 对它不生效，缓冲本身要开多重采样（设置里可选，默认 4×）
    this.composer = new EffectComposer(this.renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: getMsaa() }));
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.5, 0.45, 0.82);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.initParticles();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  resize() {
    const w = this.container.clientWidth || 1, h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.composer?.setSize(w, h);
    this.camera.aspect = w / h;
    this.fitCamera();
  }

  /** 让整个棋盘（含外墙）尽可能大地铺满屏幕：对角点投影后二分求最近的相机距离 */
  fitCamera() {
    const W = this.W || 15, H = this.H || 13;
    const tilt = THREE.MathUtils.degToRad(this.camera.aspect < 1 ? 70 : 60);
    const hx = W / 2 + 0.1, hz = H / 2 + 0.1;
    const pts = [];
    for (const x of [-hx, hx]) for (const z of [-hz, hz]) for (const y of [0, 0.9]) pts.push(new THREE.Vector3(x, y, z));
    const v = new THREE.Vector3();
    const cam = this.camera;
    const place = (dist, tz) => {
      cam.position.set(0, Math.sin(tilt) * dist, Math.cos(tilt) * dist + tz);
      cam.lookAt(0, 0, tz);
      cam.updateProjectionMatrix();
      cam.updateMatrixWorld();
    };
    const fits = (dist, tz) => {
      place(dist, tz);
      let ymin = 9, ymax = -9;
      for (const p of pts) {
        v.copy(p).project(cam);
        if (Math.abs(v.x) > 0.985) return null;
        ymin = Math.min(ymin, v.y);
        ymax = Math.max(ymax, v.y);
      }
      if (ymin < -0.985 || ymax > 0.94) return null; // 顶部给计时器留一点空间
      return true;
    };
    let best = { dist: 1e9, tz: 0 };
    for (let tz = -1.5; tz <= 1.5; tz += 0.1) {
      let lo = 3, hi = 120;
      if (!fits(hi, tz)) continue;
      for (let k = 0; k < 28; k++) {
        const mid = (lo + hi) / 2;
        if (fits(mid, tz)) hi = mid; else lo = mid;
      }
      if (hi < best.dist) best = { dist: hi, tz };
    }
    place(best.dist, best.tz);
    this.camBase = cam.position.clone();
    this.camTarget = new THREE.Vector3(0, 0, best.tz);
  }

  initParticles() {
    this.pGeo = new THREE.BoxGeometry(1, 1, 1);
    this.pMesh = new THREE.InstancedMesh(this.pGeo, new THREE.MeshStandardMaterial({ roughness: 0.6 }), MAX_PARTICLES);
    this.pMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.pMesh.count = 0;
    this.pMesh.frustumCulled = false;
    this.pMesh.setColorAt(0, new THREE.Color());
    this.scene.add(this.pMesh);
    this.particles = [];
  }

  setMsaa(n) { applyMsaa(this.composer, n); }

  tx(x) { return x - this.W / 2 + 0.5; }
  tz(y) { return y - this.H / 2 + 0.5; }

  /** 根据 start 消息搭建场景 */
  load(info, myId) {
    this.clearBoard();
    this.info = info;
    this.myId = myId;
    this.W = info.w;
    this.H = info.h;
    this.netRate = info.netRate || 30; // 服务器广播频率（同步 Hz，服务器 SYNC_HZ 配置）
    this.pred = new Predictor(info);
    this.snaps = [];
    this.latSamples = [];
    this.lat = null;
    this.ghosts = [];
    this.history = [];
    this.renderOffset = { x: 0, y: 0 };
    this.mismatch = 0;
    this.meSnap = null;
    this.statics = null;
    const half = Math.max(info.w, info.h) / 2 + 3;
    Object.assign(this.sun.shadow.camera, { left: -half, right: half, top: half, bottom: -half });
    this.sun.shadow.camera.updateProjectionMatrix();
    this.fitCamera();
    const th = (this.th = THEMES[info.theme] || THEMES.meadow);
    const env = (this.env = ENV[info.theme] || ENV.meadow);
    this.scene.background = null;
    this.scene.fog = new THREE.Fog(env.sky[1], 26, 70);
    const dark = env.dark;
    this.hemi.intensity = dark ? 0.55 : 0.5;
    this.hemi.color.set(dark ? '#b9a6ff' : '#ffffff');
    this.hemi.groundColor.set(dark ? '#2a1640' : '#7a8fb8');
    this.sun.intensity = dark ? 1.3 : 2.6;
    this.sun.color.set(env.sun);
    this.bloom.strength = env.bloom;
    this.bloom.threshold = dark ? 0.72 : 0.97;
    this.bloom.radius = dark ? 0.5 : 0.35;
    this.introT = 0;

    const board = (this.board = new THREE.Group());
    this.scene.add(board);
    const W = this.W, H = this.H, N = W * H;
    const dummy = new THREE.Object3D();
    const col = new THREE.Color();

    this.buildEnvironment(board, th, env);

    // 地板
    const floorGeo = new RoundedBoxGeometry(0.97, 0.2, 0.97, 2, 0.035);
    const floor = new THREE.InstancedMesh(floorGeo, pbr('#ffffff', { roughness: 0.85 }), N);
    const ice = new THREE.InstancedMesh(floorGeo, new THREE.MeshStandardMaterial({ color: th.ice, roughness: 0.05, metalness: 0.25, emissive: th.ice, emissiveIntensity: 0.15 }), N);
    let nf = 0, ni = 0;
    this.conveyors = [];
    this.teleporters = [];
    this.pads = [];
    this.vents = [];
    this.warns = [];
    const arrowTex = arrowTexture(th.conveyor);
    this.arrowTex = arrowTex;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const c = info.floor[y * W + x];
        dummy.position.set(this.tx(x), -0.1, this.tz(y));
        dummy.rotation.set(0, 0, 0);
        dummy.scale.set(1, 1, 1);
        dummy.updateMatrix();
        if (info.water && info.water[y * W + x] === '~') {
          // 水 / 熔岩格子不铺地板，下陷一点
          dummy.position.y = -0.3;
          dummy.updateMatrix();
          floor.setMatrixAt(nf, dummy.matrix);
          floor.setColorAt(nf++, col.set(th.liquid).multiplyScalar(0.5));
        } else if (c === 'i') {
          ice.setMatrixAt(ni++, dummy.matrix);
        } else {
          floor.setMatrixAt(nf, dummy.matrix);
          floor.setColorAt(nf++, col.set((x + y) % 2 ? th.floorA : th.floorB));
        }
        if ('^v<>'.includes(c)) {
          const p = new THREE.Mesh(new THREE.PlaneGeometry(0.96, 0.96), new THREE.MeshStandardMaterial({ map: arrowTex, roughness: 0.6 }));
          p.rotation.x = -Math.PI / 2;
          p.rotation.z = { '^': 0, v: Math.PI, '<': Math.PI / 2, '>': -Math.PI / 2 }[c];
          p.position.set(this.tx(x), 0.005, this.tz(y));
          p.receiveShadow = true;
          board.add(p);
        }
        if (c >= '1' && c <= '9') {
          const tg = new THREE.Group();
          const disc = new THREE.Mesh(
            new THREE.CircleGeometry(0.4, 32),
            new THREE.MeshBasicMaterial({ color: th.tele, transparent: true, opacity: 0.55 }),
          );
          disc.rotation.x = -Math.PI / 2;
          disc.position.y = 0.01;
          const ring = new THREE.Mesh(
            new THREE.TorusGeometry(0.4, 0.05, 8, 32),
            new THREE.MeshStandardMaterial({ color: th.tele, emissive: th.tele, emissiveIntensity: 0.8 }),
          );
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = 0.05;
          const ring2 = ring.clone();
          ring2.scale.setScalar(0.6);
          tg.add(disc, ring, ring2);
          tg.position.set(this.tx(x), 0, this.tz(y));
          board.add(tg);
          this.teleporters.push({ ring, ring2, disc });
        }
        if (c === 's') {
          // 补给台：发光底座 + 旋转的光环
          const g = new THREE.Group();
          const base = new THREE.Mesh(new THREE.CylinderGeometry(0.44, 0.48, 0.08, 6), pbr('#2a3550', { metalness: 0.7, roughness: 0.35 }));
          base.position.y = 0.04;
          const ring = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.035, 6, 6), new THREE.MeshStandardMaterial({ color: '#7dffb0', emissive: '#3dff8a', emissiveIntensity: 1.2 }));
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = 0.1;
          g.add(base, ring);
          g.position.set(this.tx(x), 0, this.tz(y));
          board.add(g);
          this.pads.push(ring);
        } else if (c === 'f') {
          // 火焰喷口：铁栅格 + 暗红光
          const g = new THREE.Group();
          const grate = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.42, 0.06, 16), pbr('#2b2522', { metalness: 0.8, roughness: 0.5 }));
          grate.position.y = 0.03;
          const glow = new THREE.Mesh(new THREE.CircleGeometry(0.26, 16), new THREE.MeshBasicMaterial({ color: '#ff5a1f', transparent: true, opacity: 0.6 }));
          glow.rotation.x = -Math.PI / 2;
          glow.position.y = 0.065;
          for (let k = 0; k < 3; k++) {
            const bar = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.03, 0.05), pbr('#1a1514', { metalness: 0.8 }));
            bar.position.set(0, 0.08, (k - 1) * 0.16);
            g.add(bar);
          }
          g.add(grate, glow);
          g.position.set(this.tx(x), 0, this.tz(y));
          board.add(g);
          this.vents.push(glow);
        } else if (c === 'w' || c === 'u') {
          // 冰墙闸门的地槽
          const slot = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ color: '#8fe8ff', transparent: true, opacity: 0.22 }));
          slot.rotation.x = -Math.PI / 2;
          slot.position.set(this.tx(x), 0.004, this.tz(y));
          board.add(slot);
        }
      }
    }
    floor.count = nf;
    ice.count = ni;
    floor.receiveShadow = ice.receiveShadow = true;
    floor.instanceColor.needsUpdate = true;
    board.add(floor, ice);

    // 方块（墙、箱子、水、草丛），数量会变化
    const wallGeo = new RoundedBoxGeometry(1, 0.9, 1, 3, 0.06);
    const wt = wallTextures(th);
    const sideMat = new THREE.MeshStandardMaterial({ map: wt.side, roughness: 0.82, metalness: 0.05, emissive: th.wallEmissive || 0x000000 });
    const topMat = new THREE.MeshStandardMaterial({ map: wt.top, roughness: 0.7, metalness: 0.08, emissive: th.wallEmissive || 0x000000 });
    if (info.theme === 'neon') {
      topMat.emissive.set(th.wallTop);
      topMat.emissiveIntensity = 0.45;
    }
    this.walls = new THREE.InstancedMesh(wallGeo, [sideMat, sideMat, topMat, sideMat, sideMat, sideMat], N);
    const crateGeo = new RoundedBoxGeometry(0.84, 0.8, 0.84, 2, 0.04);
    this.crates = new THREE.InstancedMesh(
      crateGeo,
      new THREE.MeshStandardMaterial({ map: crateTexture(th), roughness: 0.72, metalness: info.theme === 'foundry' ? 0.5 : 0.05, emissive: th.crateEmissive || 0x000000 }),
      N,
    );
    // 卡通描边（背面放大）
    const edge = new THREE.MeshBasicMaterial({ color: '#241a33', side: THREE.BackSide });
    this.wallEdges = new THREE.InstancedMesh(wallGeo, edge, N);
    this.crateEdges = new THREE.InstancedMesh(crateGeo, edge, N);
    for (const m of [this.wallEdges, this.crateEdges]) { m.count = 0; m.visible = false; board.add(m); }
    // 钢制货箱、爆炸油桶
    this.steels = new THREE.InstancedMesh(
      new RoundedBoxGeometry(0.86, 0.82, 0.86, 2, 0.05),
      new THREE.MeshStandardMaterial({ map: steelTexture(), metalness: 0.85, roughness: 0.38 }),
      N,
    );
    this.barrels = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(0.3, 0.3, 0.78, 20),
      new THREE.MeshStandardMaterial({ map: barrelTexture(), metalness: 0.45, roughness: 0.45, emissive: '#3a0800', emissiveIntensity: 0.4 }),
      N,
    );
    // 金色宝箱、冰墙闸门
    this.chests = new THREE.InstancedMesh(
      new RoundedBoxGeometry(0.8, 0.74, 0.8, 2, 0.08),
      new THREE.MeshStandardMaterial({ color: '#e8b230', metalness: 0.75, roughness: 0.3, emissive: '#6a4000', emissiveIntensity: 0.5 }),
      N,
    );
    this.gateMesh = new THREE.InstancedMesh(
      new RoundedBoxGeometry(0.96, 0.9, 0.96, 2, 0.06),
      new THREE.MeshStandardMaterial({ color: '#a8e8ff', metalness: 0.1, roughness: 0.08, transparent: true, opacity: 0.78, emissive: '#3ab8e0', emissiveIntensity: 0.35 }),
      N,
    );
    for (const m of [this.steels, this.barrels, this.chests, this.gateMesh]) { m.count = 0; m.castShadow = m.receiveShadow = true; board.add(m); }
    this.liquid = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 0.12, 1),
      new THREE.MeshStandardMaterial({
        color: th.liquid, roughness: 0.15, metalness: 0.1, transparent: true, opacity: 0.88,
        emissive: th.liquidEmissive, emissiveIntensity: info.theme === 'lava' || info.theme === 'volcano' ? 0.9 : info.theme === 'frost' ? 0.35 : 0,
      }),
      N,
    );
    this.bushes = new THREE.InstancedMesh(
      new THREE.IcosahedronGeometry(0.5, 1),
      toonMat(th.bush, { flatShading: true }),
      N,
    );
    for (const m of [this.walls, this.crates, this.bushes]) {
      m.castShadow = true;
      m.receiveShadow = true;
      m.count = 0;
      board.add(m);
    }
    this.liquid.receiveShadow = true;
    this.liquid.count = 0;
    board.add(this.liquid);
    this.blockStr = null;

    // 火焰
    const flameGeo = new THREE.IcosahedronGeometry(0.5, 2);
    this.flameOuter = new THREE.InstancedMesh(flameGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(th.flameOuter).multiplyScalar(1.05), transparent: true, opacity: 0.95 }), N * 5);
    this.flameInner = new THREE.InstancedMesh(flameGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(th.flameInner).multiplyScalar(1.05) }), N * 5);
    for (const m of [this.flameOuter, this.flameInner]) {
      m.count = 0;
      m.frustumCulled = false;
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      board.add(m);
    }
    this.flameGeo = flameGeo;
    this.flameMax = N * 5;
    this.flameSets = { '': { outer: this.flameOuter, inner: this.flameInner, n: 0 } };
    this.flameCells = new Set();
    this.fx = [];
    this.flameLight = new THREE.PointLight(th.flameOuter, 0, 8, 1.5);
    this.flameLight.position.y = 1.2;
    board.add(this.flameLight);

    // 玩家
    this.players.clear();
    for (const p of info.players) {
      const blob = buildBlob(p.skin, p.hat);
      const team = info.mode === 'team';
      const isMe = p.id === myId;
      const labelColor = team ? TEAM_COLORS[p.team] : (isMe ? '#ffe45c' : '#ffffff');
      // 组队模式：其他玩家名字前放队伍色圆点；自己用头顶箭头标识
      const label = textSprite((p.level ? `Lv${p.level} ` : '') + p.name, labelColor, team && !isMe ? TEAM_COLORS[p.team] : null);
      label.position.y = 1.15;
      blob.group.add(label);
      let arrow = null;
      if (isMe) {
        arrow = buildMeArrow(team ? TEAM_COLORS[p.team] : (SKINS[p.skin] || SKINS[0]).color);
        blob.group.add(arrow);
      }
      if (info.mode === 'team') {
        blob.ring.visible = true;
        blob.ring.material.color.set(TEAM_COLORS[p.team]);
      } else if (p.id === myId) {
        blob.ring.visible = true;
        blob.ring.material.color.set('#ffe45c');
      }
      // 被困泡泡 + 倒计时
      const bubble = new THREE.Mesh(
        new THREE.SphereGeometry(0.58, 32, 20),
        new THREE.MeshPhysicalMaterial({ color: '#bfeaff', transparent: true, opacity: 0.32, roughness: 0.05, clearcoat: 1, emissive: '#2a7ab8', emissiveIntensity: 0.35, depthWrite: false }),
      );
      bubble.position.y = 0.42;
      bubble.visible = false;
      blob.group.add(bubble);
      const trapLabel = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, depthTest: false }));
      trapLabel.scale.set(0.55, 0.55, 1);
      trapLabel.position.y = 1.6;
      trapLabel.renderOrder = 11;
      trapLabel.visible = false;
      blob.group.add(trapLabel);
      board.add(blob.group);
      // 暗色主题里让角色带一点自发光，保证可读性
      const baseEmissive = dark ? new THREE.Color((SKINS[p.skin] || SKINS[0]).color).multiplyScalar(0.28) : new THREE.Color(0);
      this.players.set(p.id, { ...blob, label, arrow, info: p, dieT: null, x: 0, y: 0, hitT: -10, bob: Math.random() * 10, baseEmissive, bubble, trapLabel, trapShown: -1 });
    }
    this.bombs.clear();
    this.powerupSprites.clear();
    this.fallingWalls.clear();
    this.cur = null;
    this.particles.length = 0;
    this.pMesh.count = 0;
    this.start();
  }

  clearBoard() {
    if (!this.board) return;
    this.scene.remove(this.board);
    this.board.traverse((o) => {
      if (o.userData.outline) return;
      if (o.geometry) o.geometry.dispose();
      const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
      for (const m of mats) {
        if (m.map && !Object.values(iconCache).includes(m.map) && m.map !== glowTex) m.map.dispose();
        m.dispose();
      }
    });
    this.board = null;
  }

  start() {
    if (this.running) return;
    this.running = true;
    let last = 0;
    const loop = (ts) => {
      if (!this.running) return;
      this.raf = requestAnimationFrame(loop);
      if (ts - last < 1000 / 60 - 1.5) return; // 锁定 60fps
      last = ts;
      this.frame();
    };
    loop();
  }

  stop() {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  /** 收到服务器快照 */
  /** 收到服务器快照 */
  pushState(s) {
    const now = performance.now();
    // 估计服务器时钟：取最近 3 秒内"本地时间 - 服务器时间"的最小值（即延迟最低的样本）
    this.latSamples.push([now, now - s.st]);
    while (this.latSamples.length > 1 && now - this.latSamples[0][0] > 3000) this.latSamples.shift();
    let lat = Infinity;
    for (const [, v] of this.latSamples) lat = Math.min(lat, v);
    this.lat = lat;
    this.snaps.push(s);
    if (this.snaps.length > 40) this.snaps.shift();
    this.cur = s;
    if (s.k !== undefined && s.k !== this.blockStr) this.rebuildBlocks(s.k);
    this.syncPowerups(s.u);
    for (const e of s.e) this.onEvent(e);
    this.reconcile(s, now);
    // 真实炸弹出现后移除对应的预放置虚影
    for (const g of [...this.ghosts]) {
      if (s.b.some((bb) => Math.round(bb[1]) === g.x && Math.round(bb[2]) === g.y) || now - g.t > this.rtt + 300) this.removeGhost(g);
    }
  }

  /** 移动以客户端为准；只有服务器拒绝了某次移动（fx 计数变化）才回到服务器位置 */
  reconcile(s, now) {
    const me = s.p.find((p) => p.id === this.myId);
    if (!me) return;
    this.meSnap = me;
    if (!me.a || s.ph !== 'play' || !this.pred.ready || this.forceSync) {
      this.pred.sync(me);
      this.forceSync = false;
      this.fixSeen = me.fx;
      this.sentMove = null;
      return;
    }
    if (this.fixSeen === undefined) this.fixSeen = me.fx;
    if (me.fx !== this.fixSeen) {
      this.fixSeen = me.fx;
      const ox = this.pred.x, oy = this.pred.y;
      this.pred.sync(me);
      if (Math.abs(ox - me.x) + Math.abs(oy - me.y) < 3) {
        this.renderOffset.x += ox - me.x;
        this.renderOffset.y += oy - me.y;
      }
      this.sentMove = null;
      this.metrics.corrections++;
    }
  }

  /** 本地输入（来自 main.js），立即作用于预测 */
  /** 移动在客户端计算，约 30Hz 把位置上报给服务器校验 */
  reportMove(now) {
    const p = this.pred;
    const kick = p.kickReq;
    p.kickReq = null;
    const x = q4(p.x), y = q4(p.y);
    const last = this.sentMove;
    const changed = !last || last.x !== x || last.y !== y || last.m !== p.moving || last.f !== p.facing;
    if (!kick && (!changed || (last && now - last.t < 1000 / 30))) return;
    this.sentMove = { x, y, m: p.moving, f: p.facing, t: now };
    this.onMove?.({ x, y, f: p.facing, m: p.moving ? 1 : 0, e: this.fixSeen ?? 0, p: Math.round(this.rtt || 0), ...(kick ? { k: kick } : {}) });
  }

  setLocalDir(dir) { this.localDir = dir; }
  localTap(dir) { this.pred?.tap(dir); }
  /** 本地立即显示炸弹（爆炸与判定仍由服务器负责）；返回放置时的位置，随放炸弹消息一起上报 */
  localBomb() {
    const me = this.meSnap, s = this.cur;
    if (!me || !me.a || !s || s.ph !== 'play' || !this.pred?.ready) return null;
    const pos = { x: q4(this.pred.x), y: q4(this.pred.y), e: this.fixSeen ?? 0 };
    if (me.tr) return pos;
    const x = Math.round(this.pred.x), y = Math.round(this.pred.y);
    const mine = s.b.filter((b) => b[5] === this.myId).length + this.ghosts.length;
    if (mine >= me.mb || this.bombBlocked(x, y)) return pos;
    const blk = this.blockStr?.[y * this.W + x];
    if (blk !== '.' && blk !== 'b') return pos;
    const meInfo = this.info.players.find((p) => p.id === this.myId);
    const o = buildBomb(meInfo?.skin || 0, meInfo?.bomb || '');
    o.group.position.set(this.tx(x), 0, this.tz(y));
    this.board.add(o.group);
    this.ghosts.push({ x, y, t: performance.now(), o });
    return pos;
  }
  removeGhost(g) {
    this.board?.remove(g.o.group);
    this.ghosts = this.ghosts.filter((x) => x !== g);
  }
  bombBlocked(x, y) {
    if (this.cur) for (const b of this.cur.b) if (Math.round(b[1]) === x && Math.round(b[2]) === y) return true;
    return this.ghosts.some((g) => g.x === x && g.y === y);
  }

  rebuildBlocks(k) {
    this.blockStr = k;
    const dummy = new THREE.Object3D();
    let nw = 0, nc = 0, nl = 0, nb = 0, ns = 0, ne = 0, ng = 0, nq = 0;
    if (!this.statics) this.buildStatics(k);
    this.wallSlots = new Map();
    this.bushSlots = new Map();
    for (let i = 0; i < k.length; i++) {
      const c = k[i];
      if (c === '.') continue;
      const x = i % this.W, y = Math.floor(i / this.W);
      dummy.position.set(this.tx(x), 0, this.tz(y));
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(1, 1, 1);
      if (c === '#') {
        const border = x === 0 || y === 0 || x === this.W - 1 || y === this.H - 1;
        // 外圈墙压低，避免挡住靠边的角色
        dummy.scale.set(1, border ? 0.45 : 1, 1);
        dummy.position.y = border ? 0.2 : 0.45;
        dummy.updateMatrix();
        this.wallSlots.set(i, nw);
        this.walls.setMatrixAt(nw, dummy.matrix);
        dummy.scale.multiplyScalar(1.05);
        dummy.updateMatrix();
        this.wallEdges.setMatrixAt(nw++, dummy.matrix);
      } else if (c === 'x') {
        dummy.position.y = 0.4;
        dummy.rotation.y = ((x * 7 + y * 13) % 5 - 2) * 0.03;
        dummy.updateMatrix();
        this.crates.setMatrixAt(nc, dummy.matrix);
        dummy.scale.setScalar(1.06);
        dummy.updateMatrix();
        this.crateEdges.setMatrixAt(nc++, dummy.matrix);
      } else if (c === 'm') {
        dummy.position.y = 0.41;
        dummy.updateMatrix();
        this.steels.setMatrixAt(ns++, dummy.matrix);
      } else if (c === 'g') {
        dummy.position.y = 0.37;
        dummy.updateMatrix();
        this.chests.setMatrixAt(nq++, dummy.matrix);
      } else if (c === 'w') {
        dummy.position.y = 0.45;
        dummy.updateMatrix();
        this.gateMesh.setMatrixAt(ng++, dummy.matrix);
      } else if (c === 'e') {
        dummy.position.y = 0.39;
        dummy.rotation.y = (x * 5 + y * 3) % 6;
        dummy.updateMatrix();
        this.barrels.setMatrixAt(ne++, dummy.matrix);
      } else if (c === '~') {
        dummy.position.y = -0.03;
        dummy.updateMatrix();
        this.liquid.setMatrixAt(nl++, dummy.matrix);
      } else if (c === 'b') {
        dummy.position.y = 0.36;
        dummy.rotation.y = (x * 3 + y * 5) % 7;
        dummy.scale.set(1, 0.85, 1);
        dummy.updateMatrix();
        this.bushSlots.set(i, nb);
        this.bushes.setMatrixAt(nb++, dummy.matrix);
      }
    }
    this.walls.count = this.wallEdges.count = nw;
    this.crates.count = this.crateEdges.count = nc;
    this.liquid.count = nl;
    this.bushes.count = nb;
    this.steels.count = ns;
    this.barrels.count = ne;
    this.chests.count = nq;
    this.gateMesh.count = ng;
    for (const m of [this.walls, this.crates, this.liquid, this.bushes, this.wallEdges, this.crateEdges, this.steels, this.barrels, this.chests, this.gateMesh]) {
      m.instanceMatrix.needsUpdate = true;
      m.computeBoundingSphere();
    }
    this.myBushSlot = -1;
  }

  /** 不可破坏的建筑（树木 / 装饰、塔楼）只在开局搭建一次 */
  buildStatics(k) {
    this.statics = new THREE.Group();
    const th = this.th, env = this.env;
    const wt = wallTextures(th);
    const towerSide = new THREE.MeshStandardMaterial({ map: wt.side, roughness: 0.8, emissive: th.wallEmissive || 0x000000 });
    const towerTop = pbr(shade(th.wallTop, -0.1), { roughness: 0.6, metalness: 0.2 });
    const glow = new THREE.MeshStandardMaterial({ color: th.tele, emissive: th.tele, emissiveIntensity: env.dark ? 1.6 : 0.8 });
    const rng = mulberry(k.length + 7);
    for (let i = 0; i < k.length; i++) {
      const c = k[i];
      if (c !== 'Y' && c !== 'H') continue;
      const x = this.tx(i % this.W), z = this.tz(Math.floor(i / this.W));
      if (c === 'Y') {
        const d = makeDeco(env.deco, rng);
        d.scale.multiplyScalar(0.62);
        d.position.set(x, 0, z);
        d.rotation.y = rng() * Math.PI * 2;
        this.statics.add(d);
      } else {
        const tower = new THREE.Group();
        const base = new THREE.Mesh(new RoundedBoxGeometry(0.96, 1.5, 0.96, 3, 0.06), towerSide);
        base.position.y = 0.75;
        const cap = new THREE.Mesh(new THREE.ConeGeometry(0.72, 0.5, 4), towerTop);
        cap.position.y = 1.75;
        cap.rotation.y = Math.PI / 4;
        const band = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.07, 0.98), glow);
        band.position.y = 1.2;
        for (const m of [base, cap]) { m.castShadow = m.receiveShadow = true; }
        tower.add(base, cap, band);
        tower.position.set(x, 0, z);
        this.statics.add(tower);
      }
    }
    this.board.add(this.statics);
  }

  syncPowerups(list) {
    const seen = new Set();
    for (const [i, type] of list) {
      const key = i + ':' + type;
      seen.add(key);
      if (!this.powerupSprites.has(key)) {
        const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: powerupTexture(type), transparent: true }));
        sp.scale.setScalar(0.01);
        sp.position.set(this.tx(i % this.W), 0.5, this.tz(Math.floor(i / this.W)));
        sp.userData = { born: this.clock.elapsedTime, phase: i };
        const shadow = new THREE.Mesh(
          new THREE.CircleGeometry(0.22, 16),
          new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.25, depthWrite: false }),
        );
        shadow.rotation.x = -Math.PI / 2;
        shadow.position.set(sp.position.x, 0.01, sp.position.z);
        const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: POWERUPS[type]?.color || '#ffffff', blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, opacity: 0.8 }));
        halo.scale.setScalar(1.1);
        sp.add(halo);
        halo.position.z = -0.01;
        this.board.add(sp, shadow);
        this.powerupSprites.set(key, { sp, shadow });
      }
    }
    for (const [key, o] of this.powerupSprites) {
      if (!seen.has(key)) {
        this.board.remove(o.sp, o.shadow);
        o.sp.material.dispose();
        o.shadow.geometry.dispose();
        o.shadow.material.dispose();
        this.powerupSprites.delete(key);
      }
    }
  }

  onEvent(e) {
    const th = this.th;
    switch (e.k) {
      case 'boom':
        this.shake = Math.min(0.35, this.shake + 0.12 + e.r * 0.01);
        if (!this.boomFx(e)) this.burst(e.x, e.y, 0.4, 16, [th.flameOuter, th.flameInner], 4, 0.12);
        this.flameFlash = 1;
        break;
      case 'crate':
        this.burst(e.x, e.y, 0.4, 10, [th.crate, th.crateLine], 3.2, 0.13);
        break;
      case 'bush':
        this.burst(e.x, e.y, 0.4, 8, [th.bush, '#2a5a20'], 2.5, 0.1);
        break;
      case 'burn':
        this.burst(e.x, e.y, 0.5, 6, ['#555555', '#999999'], 2, 0.08);
        break;
      case 'pick':
        this.burst(e.x, e.y, 0.6, 12, [POWERUPS[e.type]?.color || '#ffffff', '#ffffff'], 3, 0.07);
        break;
      case 'hit': {
        const p = this.players.get(e.id);
        if (p) p.hitT = this.clock.elapsedTime;
        this.burst(e.x, e.y, 0.5, 10, ['#ffffff', '#ff4060'], 3, 0.08);
        break;
      }
      case 'shield':
        this.burst(e.x, e.y, 0.5, 14, ['#7fd8ff', '#ffffff'], 3.5, 0.07);
        break;
      case 'die': {
        const p = this.players.get(e.id);
        if (p) {
          p.dieT = this.clock.elapsedTime;
          this.burst(e.x, e.y, 0.4, 24, [(SKINS[p.info.skin] || SKINS[0]).color, '#ffffff'], 4.5, 0.12);
        }
        break;
      }
      case 'trap': {
        const p = this.players.get(e.id);
        if (p) p.hitT = this.clock.elapsedTime;
        this.burst(e.x, e.y, 0.5, 14, ['#bfeaff', '#ffffff'], 3, 0.08);
        break;
      }
      case 'rescue':
        this.burst(e.x, e.y, 0.6, 22, ['#3ee08f', '#ffffff', '#36d6ff'], 3.5, 0.08);
        break;
      case 'respawn': {
        // 复活赛：恢复死亡动画改过的透明度
        const p = this.players.get(e.id);
        if (p) {
          p.dieT = null;
          p.bodyMat.opacity = 1;
          p.bodyMat.transparent = false;
          p.bodyMat.needsUpdate = true;
        }
        this.burst(e.x, e.y, 0.5, 20, ['#ffffff', '#ffd24a', '#36d6ff'], 3.5, 0.08);
        break;
      }
      case 'pop':
        this.shake = Math.min(0.3, this.shake + 0.12);
        this.burst(e.x, e.y, 0.6, 26, ['#bfeaff', '#ffffff', '#ff4d5e'], 4.5, 0.09);
        break;
      case 'steel':
        this.burst(e.x, e.y, 0.5, 12, ['#9aa0aa', '#d6dbe3', '#ffb547'], 3.5, 0.07);
        break;
      case 'chest':
        this.burst(e.x, e.y, 0.5, 22, ['#ffd24a', '#fff2b0', '#e8a020'], 4, 0.08);
        break;
      case 'grow':
        this.burst(e.x, e.y, 0.3, 8, ['#ffc2d8', th.bush], 1.8, 0.07);
        break;
      case 'gate':
        this.burst(e.x, e.y, 0.4, e.up ? 12 : 8, ['#bff2ff', '#ffffff'], e.up ? 3 : 2, 0.07);
        break;
      case 'supply':
        this.burst(e.x, e.y, 0.9, 16, ['#7dffb0', '#ffffff'], 3, 0.07);
        break;
      case 'warn': {
        // 机关预警：在即将喷火 / 落下陨石 / 升起冰墙的格子上闪烁
        const mat = new THREE.MeshBasicMaterial({ color: e.g ? '#8fe8ff' : '#ff3b2f', transparent: true, opacity: 0.5, depthWrite: false });
        const geo = new THREE.PlaneGeometry(0.92, 0.92);
        const grp = new THREE.Group();
        for (const i of e.c) {
          const m = new THREE.Mesh(geo, mat);
          m.rotation.x = -Math.PI / 2;
          m.position.set(this.tx(i % this.W), 0.02, this.tz(Math.floor(i / this.W)));
          grp.add(m);
        }
        this.board?.add(grp);
        this.warns.push({ grp, mat, geo, t0: this.clock.elapsedTime, dur: e.t });
        break;
      }
      case 'barrel':
        this.shake = Math.min(0.45, this.shake + 0.2);
        this.burst(e.x, e.y, 0.5, 26, ['#ff5a1f', '#ffd27a', '#3a3a3a'], 5, 0.12);
        break;
      case 'tele':
        this.burst(e.x, e.y, 0.3, 10, [th.tele, '#ffffff'], 2.5, 0.07);
        this.burst(e.x2, e.y2, 0.3, 10, [th.tele, '#ffffff'], 2.5, 0.07);
        break;
      case 'wall':
        this.fallingWalls.set(e.y * this.W + e.x, this.clock.elapsedTime);
        break;
      default:
        break;
    }
  }

  burst(x, y, h, n, colors, speed, size) {
    for (let k = 0; k < n && this.particles.length < MAX_PARTICLES; k++) {
      const a = Math.random() * Math.PI * 2;
      const v = speed * (0.4 + Math.random() * 0.8);
      this.particles.push({
        x: this.tx(x), y: h, z: this.tz(y),
        vx: Math.cos(a) * v, vy: 2 + Math.random() * 3, vz: Math.sin(a) * v,
        life: 0.5 + Math.random() * 0.5, max: 1,
        size: size * (0.6 + Math.random() * 0.8),
        color: new THREE.Color(colors[k % colors.length]),
        rot: Math.random() * 6,
      });
    }
  }

  /** 某种炸弹特效的火焰（InstancedMesh 一对：外焰 + 内焰） */
  flameSet(style) {
    if (!BOMB_FX[style]) style = '';
    let set = this.flameSets[style];
    if (!set) {
      const fx = BOMB_FX[style];
      const outer = new THREE.InstancedMesh(this.flameGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(fx.outer), transparent: true, opacity: 0.92 }), this.flameMax);
      const inner = new THREE.InstancedMesh(this.flameGeo, new THREE.MeshBasicMaterial({ color: new THREE.Color(fx.inner) }), this.flameMax);
      for (const m of [outer, inner]) {
        m.count = 0;
        m.frustumCulled = false;
        m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.board.add(m);
      }
      set = this.flameSets[style] = { outer, inner, n: 0 };
    }
    return set;
  }

  /** 柔光精灵 / 平面圆环等一次性特效 */
  spawnFx(obj, o) {
    if (this.fx.length > 240) return;
    obj.renderOrder = 3;
    this.board.add(obj);
    this.fx.push({ obj, life: o.life, max: o.life, vx: o.vx || 0, vy: o.vy || 0, vz: o.vz || 0, drag: o.drag || 0, s0: o.s0, s1: o.s1, sy: o.sy, op: o.op ?? 1 });
  }
  glowSprite(color, x, y, h) {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
    sp.position.set(this.tx(x), h, this.tz(y));
    return sp;
  }
  ring(color, x, y) {
    if (!this.ringGeo) this.ringGeo = new THREE.RingGeometry(0.42, 0.5, 48);
    const m = new THREE.Mesh(this.ringGeo, new THREE.MeshBasicMaterial({ color, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    m.rotation.x = -Math.PI / 2;
    m.position.set(this.tx(x), 0.06, this.tz(y));
    return m;
  }
  /** 新出现的一格火焰：按特效加一点粒子 */
  flameCellFx(i, style) {
    const fx = BOMB_FX[style];
    if (!fx) return;
    const x = i % this.W, y = Math.floor(i / this.W);
    const r = () => Math.random() - 0.5;
    if (style === 'poison') {
      // 紫色毒气：缓慢上升、扩散、停留更久
      for (let k = 0; k < 2; k++) {
        this.spawnFx(this.glowSprite(fx.parts[k % 3], x + r() * 0.5, y + r() * 0.5, 0.3), { life: 1.6 + Math.random() * 0.8, vx: r() * 0.5, vy: 0.35 + Math.random() * 0.3, vz: r() * 0.5, drag: 1.2, s0: 0.7, s1: 2.1, op: 0.75 });
      }
    } else if (style === 'water') {
      // 水波：每格一圈小涟漪 + 水花
      this.spawnFx(this.ring(fx.parts[1], x, y), { life: 0.7, s0: 0.5, s1: 1.5, op: 0.8 });
      this.burst(x, y, 0.3, 3, fx.parts, 2.2, 0.07);
    } else if (style === 'gold') {
      // 金光：闪烁的金色光点
      this.spawnFx(this.glowSprite(fx.parts[0], x + r() * 0.4, y + r() * 0.4, 0.5), { life: 0.6, vy: 1.2, s0: 0.9, s1: 0.2, op: 1 });
      this.burst(x, y, 0.5, 2, fx.parts, 1.6, 0.06);
    }
  }
  /** 特效炸弹在中心爆开时的大特效 */
  boomFx(e) {
    const fx = BOMB_FX[e.st];
    if (!fx) return false;
    const { x, y } = e;
    const r = () => Math.random() - 0.5;
    if (e.st === 'poison') {
      for (let k = 0; k < 9; k++) {
        this.spawnFx(this.glowSprite(fx.parts[k % fx.parts.length], x + r() * 0.6, y + r() * 0.6, 0.35), { life: 2 + Math.random(), vx: r() * 1.4, vy: 0.4 + Math.random() * 0.5, vz: r() * 1.4, drag: 1.1, s0: 0.9, s1: 3.2, op: 0.7 });
      }
      this.burst(x, y, 0.4, 10, fx.parts, 3, 0.1);
    } else if (e.st === 'water') {
      for (let k = 0; k < 3; k++) {
        this.spawnFx(this.ring(k ? fx.parts[0] : fx.parts[1], x, y), { life: 0.9 + k * 0.25, s0: 0.4 + k * 0.2, s1: 3.2 + k * 1.2, op: 0.9 - k * 0.2 });
      }
      this.burst(x, y, 0.4, 18, fx.parts, 4.5, 0.09);
    } else if (e.st === 'gold') {
      // 金色光柱 + 光晕 + 金粉
      if (!this.pillarGeo) this.pillarGeo = new THREE.CylinderGeometry(0.3, 0.45, 3.2, 24, 1, true);
      const pillar = new THREE.Mesh(this.pillarGeo, new THREE.MeshBasicMaterial({ color: fx.parts[2], transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
      pillar.position.set(this.tx(x), 1.6, this.tz(y));
      this.spawnFx(pillar, { life: 0.7, s0: 1, s1: 1.8, sy: 1, op: 0.5 });
      this.spawnFx(this.glowSprite(fx.parts[0], x, y, 0.6), { life: 0.6, s0: 1.5, s1: 4, op: 0.75 });
      this.spawnFx(this.ring(fx.parts[0], x, y), { life: 0.6, s0: 0.4, s1: 2.6, op: 0.9 });
      this.burst(x, y, 0.5, 18, fx.parts, 3.5, 0.08);
    }
    this.burst(x, y, 0.4, 6, [fx.outer, fx.inner], 4, 0.12);
    return true;
  }
  updateFx(dt) {
    for (let k = this.fx.length - 1; k >= 0; k--) {
      const f = this.fx[k];
      f.life -= dt;
      if (f.life <= 0) {
        this.board.remove(f.obj);
        f.obj.material.dispose();
        this.fx.splice(k, 1);
        continue;
      }
      const a = 1 - f.life / f.max;
      if (f.drag) {
        const d = Math.exp(-f.drag * dt);
        f.vx *= d; f.vy *= d; f.vz *= d;
      }
      f.obj.position.x += f.vx * dt;
      f.obj.position.y += f.vy * dt;
      f.obj.position.z += f.vz * dt;
      const sc = f.s0 + (f.s1 - f.s0) * (1 - (1 - a) * (1 - a));
      if (f.sy != null) f.obj.scale.set(sc, f.sy, sc);
      else f.obj.scale.setScalar(sc);
      f.obj.material.opacity = f.op * Math.min(1, (1 - a) * 1.6);
    }
  }

  frame() {
    const dt = Math.min(0.05, this.clock.getDelta());
    const t = this.clock.elapsedTime;
    if (!this.board) {
      this.renderer.render(this.scene, this.camera);
      return;
    }
    const s = this.cur;
    const now = performance.now();
    // FPS
    this.metrics.frames++;
    if (now - this.metrics.fpsT >= 500) {
      this.metrics.fps = Math.round((this.metrics.frames * 1000) / (now - this.metrics.fpsT));
      this.metrics.frames = 0;
      this.metrics.fpsT = now;
    }
    // 其他实体：按服务器时间戳插值（落后约 1.5 个 tick）
    let A = s, B = s, alpha = 1;
    if (s && this.lat != null && this.snaps.length > 1) {
      const rt = now - this.lat - (1000 / this.netRate) * 1.25 - 6;
      for (let i = this.snaps.length - 1; i >= 0; i--) {
        if (this.snaps[i].st <= rt) {
          A = this.snaps[i];
          B = this.snaps[i + 1] || A;
          break;
        }
        if (i === 0) A = B = this.snaps[0];
      }
      const span = B.st - A.st;
      alpha = span > 0 ? Math.min(1, Math.max(0, (rt - A.st) / span)) : 1;
    }
    // 自己：本地预测
    const meSnap = this.meSnap;
    const predicting = s && meSnap && meSnap.a && s.ph === 'play' && this.pred?.ready && !this.frozen;
    if (predicting) {
      this.pred.step(dt, { blocks: this.blockStr || '', bombAt: meSnap.wg ? () => false : (x, y) => this.bombBlocked(x, y), realBombAt: (x, y) => this.cur.b.some((b) => Math.round(b[1]) === x && Math.round(b[2]) === y), kick: !!meSnap.k, speedLv: meSnap.s, trapped: meSnap.tr > 0, dir: this.localDir });
      this.reportMove(now);
    }
    const decay = Math.exp(-dt / 0.07);
    this.renderOffset.x *= decay;
    this.renderOffset.y *= decay;

    // 玩家
    if (s) {
      const aMap = new Map(A.p.map((p) => [p.id, p]));
      const bMap = new Map(B.p.map((p) => [p.id, p]));
      const me = s.p.find((p) => p.id === this.myId);
      let myTile = -1;
      if (me && me.a) myTile = predicting ? Math.round(this.pred.y) * this.W + Math.round(this.pred.x) : Math.round(me.y) * this.W + Math.round(me.x);
      for (const sp of s.p) {
        const o = this.players.get(sp.id);
        if (!o) continue;
        let x = sp.x, y = sp.y, facing = sp.f, moving = sp.m;
        if (sp.id === this.myId && predicting) {
          x = this.pred.x + this.renderOffset.x;
          y = this.pred.y + this.renderOffset.y;
          facing = this.pred.facing[0];
          moving = this.pred.moving;
        } else {
          const pa = aMap.get(sp.id), pb = bMap.get(sp.id);
          if (pa && pb && Math.abs(pb.x - pa.x) + Math.abs(pb.y - pa.y) < 1.5) {
            x = pa.x + (pb.x - pa.x) * alpha;
            y = pa.y + (pb.y - pa.y) * alpha;
            facing = (alpha < 0.5 ? pa : pb).f;
            moving = pb.m;
          } else if (pb) {
            x = pb.x;
            y = pb.y;
          }
        }
        o.group.position.set(this.tx(x), 0, this.tz(y));
        const targetRot = FACING_ROT[facing] ?? 0;
        let dr = targetRot - o.group.rotation.y;
        dr = Math.atan2(Math.sin(dr), Math.cos(dr));
        o.group.rotation.y += dr * Math.min(1, dt * 14);
        o.label.material.rotation = 0;

        if (!sp.a) {
          const k = o.dieT == null ? 1 : Math.min(1, (t - o.dieT) / 0.9);
          o.group.visible = k < 1;
          o.body.position.y = 0.36 + k * 1.6;
          o.body.scale.set(1 - k * 0.8, (1 - k * 0.8) * 0.92, 1 - k * 0.8);
          o.bodyMat.transparent = true;
          o.bodyMat.opacity = 1 - k;
          o.group.rotation.y += dt * 12;
          continue;
        }
        o.group.visible = true;
        // 被困泡泡与倒计时
        const trapped = sp.tr > 0;
        o.bubble.visible = trapped;
        o.trapLabel.visible = trapped;
        if (trapped) {
          o.bubble.scale.setScalar(1 + Math.sin(t * 4) * 0.04);
          o.bubble.rotation.y += dt * 0.8;
          const secs = Math.ceil(sp.tr);
          if (secs !== o.trapShown) {
            o.trapShown = secs;
            o.trapLabel.material.map?.dispose();
            o.trapLabel.material.map = trapTexture(secs, sp.tr / 10);
            o.trapLabel.material.needsUpdate = true;
          }
        }
        // 自己头顶的箭头：上下浮动，被困时抬高避开倒计时
        if (o.arrow) {
          o.arrow.position.y = (trapped ? 2.3 : 1.9) + Math.sin(t * 4) * 0.1;
          o.arrow.rotation.y = t * 1.6;
        }
        animateHat(o.inner, t);
        // 弹跳与挤压
        o.bob += dt * (moving ? (trapped ? 5 : 15) : 3.5);
        const bounce = trapped ? 0.18 + Math.sin(o.bob) * 0.04 : moving ? Math.abs(Math.sin(o.bob)) * 0.1 : Math.sin(o.bob) * 0.015;
        const squash = moving ? 1 + Math.sin(o.bob * 2) * 0.06 : 1 + Math.sin(o.bob) * 0.03;
        o.body.position.y = 0.36 + bounce;
        o.body.scale.set(1 / Math.sqrt(squash), 0.92 * squash, 1 / Math.sqrt(squash));
        o.feet[0].position.z = 0.04 + (moving ? Math.sin(o.bob) * 0.08 : 0);
        o.feet[1].position.z = 0.04 - (moving ? Math.sin(o.bob) * 0.08 : 0);
        // 无敌闪烁、受击变红
        o.body.visible = !sp.iv || Math.floor(t * 12) % 2 === 0;
        const hitK = Math.max(0, 1 - (t - o.hitT) / 0.4);
        o.bodyMat.emissive.copy(o.baseEmissive).lerp(HIT_RED, hitK);
        // 护盾（蓝）/ 无敌盾牌（金色光罩，更亮、更大）
        o.shield.visible = !!sp.sh || !!sp.ish;
        if (o.shield.visible) {
          const gold = !!sp.ish;
          if (o.shield.userData.gold !== gold) {
            o.shield.userData.gold = gold;
            o.shield.material.color.set(gold ? '#ffd23f' : '#7fd8ff');
            o.shield.material.emissive.set(gold ? '#ff9d00' : '#2a8ad8');
            o.shield.material.opacity = gold ? 0.32 : 0.22;
          }
          o.shield.scale.setScalar((gold ? 1.12 : 1) + Math.sin(t * (gold ? 9 : 5)) * 0.04);
        }
        // 腾飞之翼：浮起来 + 一对扇动的翅膀
        if (sp.wg && !o.wings) o.wings = buildWings(o.group);
        if (o.wings) o.wings.visible = !!sp.wg;
        o.group.position.y = sp.wg ? 0.22 + Math.sin(t * 6) * 0.04 : 0;
        if (sp.wg) {
          const flap = Math.sin(t * 14) * 0.45;
          o.wings.children[0].rotation.z = 0.35 + flap;
          o.wings.children[1].rotation.z = -0.35 - flap;
        }
        // 超级跑鞋：脚下拖出青色光尘
        if (sp.bt && moving && Math.random() < dt * 40) this.burst(x, y, 0.08, 1, ['#36d6ff', '#bff4ff'], 0.6, 0.05);
        // 草丛：敌人躲在草丛里看不到（自己所在的草丛会变矮）
        const tile = Math.round(sp.y) * this.W + Math.round(sp.x);
        const inBush = this.blockStr && this.blockStr[tile] === 'b';
        if (inBush && sp.id !== this.myId && tile !== myTile) {
          const sameTeam = this.info.mode === 'team' && me && this.teamOf(sp.id) === this.teamOf(this.myId);
          o.group.visible = sameTeam;
        }
        // 透明人：自己和队友看到半透明；敌人只看到地上淡淡的水波纹
        const ghost = !!sp.gh;
        const friendly = sp.id === this.myId || (this.info.mode === 'team' && this.teamOf(sp.id) === this.teamOf(this.myId));
        setAlpha(o, ghost && friendly ? 0.35 : 1);
        if (ghost && !friendly) {
          o.group.visible = false;
          o.rippleT = (o.rippleT ?? 0) - dt;
          if (o.rippleT <= 0) {
            o.rippleT = moving ? 0.45 : 0.9;
            this.spawnFx(this.ring('#d6f0ff', x, y), { life: 0.9, s0: 0.35, s1: 1.1, op: moving ? 0.22 : 0.12 });
          }
        }
      }
      // 自己所在的草丛变矮变透明
      if (this.bushSlots) {
        const slot = this.bushSlots.get(myTile);
        if (slot !== this.myBushSlot) {
          const dummy = new THREE.Object3D();
          const setBush = (i, sl, sc) => {
            if (sl === undefined || sl < 0) return;
            const x = i % this.W, y = Math.floor(i / this.W);
            dummy.position.set(this.tx(x), 0.36 * sc, this.tz(y));
            dummy.rotation.set(0, (x * 3 + y * 5) % 7, 0);
            dummy.scale.set(sc, 0.85 * sc, sc);
            dummy.updateMatrix();
            this.bushes.setMatrixAt(sl, dummy.matrix);
          };
          if (this.myBushSlot >= 0) setBush(this.myBushTile, this.myBushSlot, 1);
          if (slot !== undefined) setBush(myTile, slot, 0.45);
          this.myBushSlot = slot ?? -1;
          this.myBushTile = myTile;
          this.bushes.instanceMatrix.needsUpdate = true;
        }
      }
    }

    // 炸弹
    if (s) {
      const aB = new Map(A.b.map((b) => [b[0], b]));
      const bB = new Map(B.b.map((b) => [b[0], b]));
      const seen = new Set();
      for (const b of s.b) {
        const [id, bx, by, fuse, skin, , style] = b;
        seen.add(id);
        let o = this.bombs.get(id);
        if (!o) {
          o = buildBomb(skin, style || '');
          o.born = t;
          this.board.add(o.group);
          this.bombs.set(id, o);
        }
        const ba = aB.get(id), bb2 = bB.get(id);
        let x = bx, y = by;
        if (ba && bb2) {
          x = ba[1] + (bb2[1] - ba[1]) * alpha;
          y = ba[2] + (bb2[2] - ba[2]) * alpha;
        }
        o.group.position.set(this.tx(x), 0, this.tz(y));
        const urgency = 1 - fuse;
        const pulse = 1 + Math.sin(t * (6 + urgency * 26)) * (0.05 + urgency * 0.07);
        const appear = Math.min(1, (t - o.born) / 0.15);
        o.group.scale.set(pulse * appear, (2 - pulse) * appear, pulse * appear);
        o.body.material.emissiveIntensity = o.baseGlow * (0.8 + Math.sin(t * 5) * 0.2) + (urgency > 0.6 ? (Math.sin(t * 30) * 0.5 + 0.5) * (urgency - 0.6) * 2 : 0);
        o.spark.scale.setScalar(0.22 + Math.random() * 0.15);
      }
      for (const [id, o] of this.bombs) {
        if (!seen.has(id)) {
          this.board.remove(o.group);
          o.group.traverse((c) => {
            if (c.userData.outline) return;
            c.geometry?.dispose();
            if (c.material && c.material.map !== glowTex) c.material.dispose();
          });
          this.bombs.delete(id);
        }
      }
    }

    // 火焰
    if (s) {
      const dummy = new THREE.Object3D();
      const wob = 1 + Math.sin(t * 40) * 0.06;
      const sets = this.flameSets;
      for (const k in sets) sets[k].n = 0;
      const nowCells = new Set();
      let lightStyle = '';
      for (const [i, mask, style = ''] of s.f) {
        const set = this.flameSet(style);
        nowCells.add(i);
        if (!this.flameCells.has(i)) this.flameCellFx(i, style); // 新出现的火焰格：特效粒子
        if (style) lightStyle = style;
        const cx = this.tx(i % this.W), cz = this.tz(Math.floor(i / this.W));
        const put = (mesh, idx, x, z, sx, sy, sz, y) => {
          dummy.position.set(x, y, z);
          dummy.rotation.set(0, 0, 0);
          dummy.scale.set(sx, sy, sz);
          dummy.updateMatrix();
          mesh.setMatrixAt(idx, dummy.matrix);
        };
        const w2 = 1 + Math.sin(t * 30 + i * 1.7) * 0.08;
        const thick = 0.7 * w2, inner = 0.36 * w2;
        const center = mask & 16;
        put(set.outer, set.n, cx, cz, thick + (center ? 0.2 : 0), (center ? 0.8 : 0.6) * w2, thick + (center ? 0.2 : 0), 0.32);
        put(set.inner, set.n++, cx, cz, inner + (center ? 0.12 : 0), (center ? 0.95 : 0.72) * w2, inner + (center ? 0.12 : 0), 0.34);
        const arms = [[1, 0, -1], [2, 1, 0], [4, 0, 1], [8, -1, 0]];
        for (const [bit, dx, dz] of arms) {
          if (!(mask & bit)) continue;
          const ox = cx + dx * 0.3, oz = cz + dz * 0.3;
          put(set.outer, set.n, ox, oz, dx ? 0.78 : thick * 0.92, 0.55 * w2, dz ? 0.78 : thick * 0.92, 0.3);
          put(set.inner, set.n++, ox, oz, dx ? 0.7 : inner, 0.66 * w2, dz ? 0.7 : inner, 0.32);
        }
      }
      for (const k in sets) {
        const st = sets[k];
        st.outer.count = st.inner.count = st.n;
        st.outer.instanceMatrix.needsUpdate = st.inner.instanceMatrix.needsUpdate = true;
      }
      this.flameCells = nowCells;
      this.flameLight.color.set(BOMB_FX[lightStyle]?.light || this.th.flameOuter);
      this.flameLight.intensity = s.f.length ? 6 : Math.max(0, this.flameLight.intensity - dt * 30);
      if (s.f.length) {
        const [i] = s.f[Math.floor(s.f.length / 2)];
        this.flameLight.position.set(this.tx(i % this.W), 1.2, this.tz(Math.floor(i / this.W)));
      }
    }

    // 道具漂浮
    for (const { sp } of this.powerupSprites.values()) {
      const age = t - sp.userData.born;
      const sc = Math.min(1, age / 0.25) * 0.62;
      sp.scale.setScalar(sc);
      sp.position.y = 0.48 + Math.sin(t * 3 + sp.userData.phase) * 0.08;
    }

    // 传送门、传送带、液体
    for (const tp of this.teleporters) {
      tp.ring.rotation.z = t * 2;
      tp.ring2.rotation.z = -t * 3;
      tp.ring2.position.y = 0.05 + (Math.sin(t * 3) * 0.5 + 0.5) * 0.25;
      tp.disc.material.opacity = 0.4 + Math.sin(t * 4) * 0.15;
    }
    for (const r of this.pads || []) r.rotation.z = t * 1.5;
    for (const v of this.vents || []) v.material.opacity = 0.45 + Math.sin(t * 2.5) * 0.2;
    if (this.warns?.length) {
      this.warns = this.warns.filter((w) => {
        const k = (t - w.t0) / w.dur;
        if (k >= 1 || !this.board) {
          this.board?.remove(w.grp);
          w.geo.dispose();
          w.mat.dispose();
          return false;
        }
        w.mat.opacity = 0.2 + 0.45 * (0.5 + 0.5 * Math.sin(t * (8 + k * 14)));
        return true;
      });
    }
    if (this.arrowTex) this.arrowTex.offset.y = (t * 1.2) % 1;
    if (this.liquid) this.liquid.position.y = Math.sin(t * 1.6) * 0.03;

    // 缩圈落下的墙
    if (this.fallingWalls.size && this.wallSlots) {
      const dummy = new THREE.Object3D();
      for (const [i, t0] of this.fallingWalls) {
        const slot = this.wallSlots.get(i);
        const k = Math.min(1, (t - t0) / 0.35);
        if (slot !== undefined) {
          dummy.position.set(this.tx(i % this.W), 0.45 + (1 - k * k) * 6, this.tz(Math.floor(i / this.W)));
          dummy.rotation.set(0, 0, 0);
          dummy.scale.set(1, 1, 1);
          dummy.updateMatrix();
          this.walls.setMatrixAt(slot, dummy.matrix);
          dummy.scale.setScalar(1.05);
          dummy.updateMatrix();
          this.wallEdges.setMatrixAt(slot, dummy.matrix);
          this.walls.instanceMatrix.needsUpdate = true;
          this.wallEdges.instanceMatrix.needsUpdate = true;
        }
        if (k >= 1) {
          this.fallingWalls.delete(i);
          this.shake = Math.min(0.3, this.shake + 0.05);
          this.burst(i % this.W, Math.floor(i / this.W), 0.1, 6, [this.th.wall, this.th.wallTop], 2, 0.1);
        }
      }
    }

    // 粒子
    const dummy = this.pDummy || (this.pDummy = new THREE.Object3D());
    let n = 0;
    for (let k = this.particles.length - 1; k >= 0; k--) {
      const p = this.particles[k];
      p.life -= dt;
      if (p.life <= 0) {
        this.particles.splice(k, 1);
        continue;
      }
      p.vy -= 12 * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.z += p.vz * dt;
      if (p.y < 0.03) { p.y = 0.03; p.vy *= -0.3; p.vx *= 0.7; p.vz *= 0.7; }
      p.rot += dt * 8;
      dummy.position.set(p.x, p.y, p.z);
      dummy.rotation.set(p.rot, p.rot * 0.7, 0);
      dummy.scale.setScalar(p.size * Math.min(1, p.life * 2.5));
      dummy.updateMatrix();
      this.pMesh.setMatrixAt(n, dummy.matrix);
      this.pMesh.setColorAt(n, p.color);
      n++;
    }
    this.pMesh.count = n;
    this.pMesh.instanceMatrix.needsUpdate = true;
    if (this.pMesh.instanceColor) this.pMesh.instanceColor.needsUpdate = true;

    if (this.fx) this.updateFx(dt);
    this.animateEnvironment(dt, t);

    // 开场镜头：从高空旋转俯冲到战场
    this.introT = Math.min(1, (this.introT ?? 1) + dt / 2.6);
    const e = 1 - Math.pow(1 - this.introT, 3);
    const camPos = this.camBase.clone();
    if (e < 1) {
      const ang = (1 - e) * 1.1;
      const off = camPos.clone().sub(this.camTarget);
      off.applyAxisAngle(new THREE.Vector3(0, 1, 0), ang);
      off.multiplyScalar(1 + (1 - e) * 1.4);
      off.y += (1 - e) * 10;
      camPos.copy(this.camTarget).add(off);
    }
    // 镜头震动
    this.shake = Math.max(0, this.shake - dt * 1.2);
    const sk = this.shake * this.shake * 2;
    this.camera.position.set(
      camPos.x + (Math.random() - 0.5) * sk,
      camPos.y + (Math.random() - 0.5) * sk,
      camPos.z + (Math.random() - 0.5) * sk,
    );
    this.camera.lookAt(this.camTarget);
    this.composer.render();
  }

  /** 搭建棋盘周围的世界：天空、地台、海面 / 雪原 / 霓虹网格、主题装饰、氛围粒子 */
  buildEnvironment(board, th, env) {
    const W = this.W, H = this.H;
    // 渐变天空
    const sky = new THREE.Mesh(
      new THREE.SphereGeometry(95, 32, 16),
      new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, fog: false,
        uniforms: { top: { value: new THREE.Color(env.sky[0]) }, bottom: { value: new THREE.Color(env.sky[1]) } },
        vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
        fragmentShader: 'uniform vec3 top; uniform vec3 bottom; varying vec3 vP; void main(){ float h = clamp(normalize(vP).y*1.4+0.3,0.0,1.0); gl_FragColor = vec4(mix(bottom, top, h),1.0); }',
      }),
    );
    board.add(sky);

    // 棋盘底座（泥土侧面 + 草地包边）
    const baseMat = [toonMat(shade(th.wall, -0.35)), toonMat(shade(th.wall, -0.35)), toonMat(shade(th.wall, -0.1)), toonMat(shade(th.wall, -0.35)), toonMat(shade(th.wall, -0.35)), toonMat(shade(th.wall, -0.35))];
    const base = new THREE.Mesh(new THREE.BoxGeometry(W + 0.6, 1.4, H + 0.6), baseMat);
    base.position.y = -0.9;
    base.receiveShadow = true;
    board.add(base);

    // 周边陆地平台
    const land = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 6), toonMat(env.land));
    land.scale.set(W * 1.15, 0.9, H * 1.35);
    land.rotation.y = Math.PI / 6;
    land.position.y = -0.95;
    land.receiveShadow = true;
    board.add(land);
    const rim = new THREE.Mesh(new THREE.CylinderGeometry(1, 1.08, 1, 6), toonMat(shade(env.land, -0.35)));
    rim.scale.set(W * 1.15, 1.2, H * 1.35);
    rim.rotation.y = Math.PI / 6;
    rim.position.y = -1.55;
    board.add(rim);

    // 远处的海 / 雪 / 网格 / 熔岩
    const seaGeo = new THREE.PlaneGeometry(160, 160, 64, 64);
    seaGeo.rotateX(-Math.PI / 2);
    const seaMat = env.surround === 'lava'
      ? new THREE.MeshBasicMaterial({ color: new THREE.Color(env.sea).multiplyScalar(1.2) })
      : toonMat(env.sea, { transparent: env.surround === 'sea', opacity: 0.95 });
    this.sea = new THREE.Mesh(seaGeo, seaMat);
    this.sea.position.y = env.surround === 'snow' ? -1.3 : -1.7;
    this.sea.receiveShadow = true;
    this.seaBase = seaGeo.attributes.position.array.slice();
    this.seaWaves = env.surround === 'sea' || env.surround === 'lava';
    board.add(this.sea);
    if (env.surround === 'grid') {
      const grid = new THREE.GridHelper(160, 80, '#ff3fa4', '#5a2bd6');
      grid.position.y = -1.6;
      grid.material.transparent = true;
      grid.material.opacity = 0.7;
      board.add(grid);
      this.neonGrid = grid;
    }

    // 主题装饰：只摆在棋盘左右两侧和后方
    const rng = mulberry(W * 31 + H * 7 + th.wall.length);
    const spots = [];
    for (let k = 0; k < 80 && spots.length < 26; k++) {
      const side = rng() < 0.5 ? -1 : 1;
      const x = side * (W / 2 + 1.2 + rng() * (W * 0.45));
      const z = (rng() - 0.6) * H * 1.2;
      if (Math.abs(x) < W / 2 + 0.9) continue;
      const inside = (x / (W * 1.0)) ** 2 + (z / (H * 1.2)) ** 2 < 1;
      if (!inside) continue;
      if (spots.some((p) => Math.hypot(p[0] - x, p[1] - z) < 1.4)) continue;
      spots.push([x, z]);
    }
    for (const [x, z] of spots) {
      const o = makeDeco(env.deco, rng);
      o.position.set(x, -0.45, z);
      o.rotation.y = rng() * Math.PI * 2;
      board.add(o);
    }

    // 氛围粒子
    const n = env.moteKind === 'snow' ? 260 : 120;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * W * 2;
      pos[i * 3 + 1] = Math.random() * 9;
      pos[i * 3 + 2] = (Math.random() - 0.5) * H * 2;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const glow = env.moteKind === 'firefly' || env.moteKind === 'spark' || env.moteKind === 'ember';
    this.motes = new THREE.Points(geo, new THREE.PointsMaterial({
      color: new THREE.Color(env.mote).multiplyScalar(glow ? 2 : 1),
      size: env.moteKind === 'snow' ? 0.12 : 0.1,
      map: glowTexture(), transparent: true, depthWrite: false,
      blending: glow ? THREE.AdditiveBlending : THREE.NormalBlending, opacity: 0.9,
    }));
    this.motes.userData.kind = env.moteKind;
    board.add(this.motes);
  }

  animateEnvironment(dt, t) {
    if (this.sea && this.seaWaves) {
      const pos = this.sea.geometry.attributes.position;
      const arr = pos.array, base = this.seaBase;
      for (let i = 0; i < arr.length; i += 3) {
        arr[i + 1] = Math.sin(base[i] * 0.3 + t * 1.1) * 0.14 + Math.cos(base[i + 2] * 0.25 + t * 0.8) * 0.14;
      }
      pos.needsUpdate = true;
    }
    if (this.neonGrid) this.neonGrid.material.opacity = 0.55 + Math.sin(t * 2) * 0.2;
    if (this.motes) {
      const kind = this.motes.userData.kind;
      const arr = this.motes.geometry.attributes.position.array;
      for (let i = 0; i < arr.length; i += 3) {
        if (kind === 'snow' || kind === 'petal') {
          arr[i + 1] -= dt * (kind === 'snow' ? 0.9 : 0.5);
          arr[i] += Math.sin(t + i) * dt * 0.4;
          if (arr[i + 1] < -0.5) arr[i + 1] = 9;
        } else {
          arr[i + 1] += dt * (kind === 'ember' ? 1.2 : 0.3);
          arr[i] += Math.sin(t * 1.5 + i) * dt * 0.3;
          arr[i + 2] += Math.cos(t * 1.3 + i) * dt * 0.3;
          if (arr[i + 1] > 9) arr[i + 1] = -0.3;
        }
      }
      this.motes.geometry.attributes.position.needsUpdate = true;
      this.motes.material.opacity = kind === 'firefly' ? 0.6 + Math.sin(t * 3) * 0.3 : 0.9;
    }
  }

  teamOf(id) {
    return this.info.players.find((p) => p.id === id)?.team;
  }
}

function mulberry(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 主题装饰物（低多边形写实风） */
function makeDeco(kind, rng) {
  const g = new THREE.Group();
  const add = (geo, color, x, y, z, extra) => {
    const m = new THREE.Mesh(geo, pbr(color, extra));
    m.position.set(x, y, z);
    m.castShadow = true;
    m.receiveShadow = true;
    g.add(m);
    return m;
  };
  const s = 0.8 + rng() * 0.6;
  switch (kind) {
    case 'pine':
      add(new THREE.CylinderGeometry(0.1, 0.14, 0.6, 6), '#4a3626', 0, 0.3, 0);
      add(new THREE.ConeGeometry(0.75, 1.2, 7), '#2b5a46', 0, 1.0, 0, { flatShading: true, roughness: 0.9 });
      add(new THREE.ConeGeometry(0.55, 1.0, 7), '#33664f', 0, 1.65, 0, { flatShading: true, roughness: 0.9 });
      add(new THREE.ConeGeometry(0.34, 0.45, 7), '#eef3f8', 0, 2.1, 0, { flatShading: true, roughness: 0.6 });
      break;
    case 'palm':
      add(new THREE.CylinderGeometry(0.08, 0.14, 1.9, 6), '#5d4630', 0, 0.95, 0).rotation.z = 0.12;
      for (let k = 0; k < 6; k++) {
        const leaf = add(new THREE.ConeGeometry(0.16, 1.1, 4), '#2f5a2a', Math.cos(k * 1.05) * 0.45 + 0.12, 1.85, Math.sin(k * 1.05) * 0.45, { flatShading: true, roughness: 0.85 });
        leaf.rotation.z = Math.PI / 2 - 0.4;
        leaf.rotation.y = -k * 1.05;
      }
      break;
    case 'crystal': {
      const cols = ['#5ff2ff', '#ff3d9a', '#8b6bff'];
      for (let k = 0; k < 3; k++) {
        const c = cols[k];
        const m = add(new THREE.OctahedronGeometry(0.3 + rng() * 0.25), c, (rng() - 0.5) * 0.8, 0.5 + rng() * 0.4, (rng() - 0.5) * 0.8, { emissive: c, emissiveIntensity: 1.1, flatShading: true, metalness: 0.3, roughness: 0.2 });
        m.scale.y = 2;
      }
      break;
    }
    case 'pipe': {
      // 工业烟囱 / 管道
      const metal = '#4a4e57';
      add(new THREE.CylinderGeometry(0.32, 0.38, 2.2, 14), metal, 0, 1.1, 0, { metalness: 0.8, roughness: 0.45 });
      add(new THREE.CylinderGeometry(0.36, 0.36, 0.12, 14), '#d08f2a', 0, 1.6, 0, { metalness: 0.6, roughness: 0.4 });
      add(new THREE.CylinderGeometry(0.22, 0.22, 0.1, 14), '#ff6a1f', 0, 2.22, 0, { emissive: '#ff4a0a', emissiveIntensity: 1.6 });
      const side = add(new THREE.CylinderGeometry(0.12, 0.12, 1.2, 10), metal, 0.55, 0.5, 0, { metalness: 0.8, roughness: 0.45 });
      side.rotation.z = Math.PI / 2;
      break;
    }
    case 'sakura':
      add(new THREE.CylinderGeometry(0.1, 0.16, 1.1, 7), '#5a3a2e', 0, 0.55, 0, { roughness: 0.9 });
      add(new THREE.IcosahedronGeometry(0.72, 0), '#f4a6c4', 0, 1.4, 0, { flatShading: true, roughness: 0.8 });
      add(new THREE.IcosahedronGeometry(0.5, 0), '#ffc8dc', 0.3, 1.85, 0.1, { flatShading: true, roughness: 0.8 });
      add(new THREE.IcosahedronGeometry(0.42, 0), '#e88ab0', -0.32, 1.7, -0.12, { flatShading: true, roughness: 0.8 });
      break;
    case 'rock':
      for (let k = 0; k < 3; k++) {
        const m = add(new THREE.DodecahedronGeometry(0.4 + rng() * 0.3), '#3a3532', (rng() - 0.5) * 0.9, 0.25, (rng() - 0.5) * 0.9, { flatShading: true, roughness: 0.95 });
        m.scale.y = 0.7 + rng() * 0.8;
      }
      break;
    default: // tree
      add(new THREE.CylinderGeometry(0.1, 0.16, 1.1, 7), '#4f3a28', 0, 0.55, 0, { roughness: 0.9 });
      add(new THREE.IcosahedronGeometry(0.72, 0), '#3d5f2f', 0, 1.4, 0, { flatShading: true, roughness: 0.9 });
      add(new THREE.IcosahedronGeometry(0.5, 0), '#4a6f37', 0.28, 1.9, 0.1, { flatShading: true, roughness: 0.9 });
  }
  g.scale.setScalar(s);
  return g;
}
