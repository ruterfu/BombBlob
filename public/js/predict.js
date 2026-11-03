// 本地角色预测：与服务器 backend/game.py 的 _move_player 使用同一套自由移动（像素级 + 滑角）规则。
// 移动在客户端计算并上报，服务器校验速度与路径，不合理则拒绝（scene.js 收到拒绝后回滚到服务器位置）。

const DIRS = { up: [0, -1], right: [1, 0], down: [0, 1], left: [-1, 0] };
const CONVEYOR = { '^': 'up', v: 'down', '<': 'left', '>': 'right' };
const BLOCKING = new Set(['#', 'x', 'm', 'e', 'Y', 'H', '~']);
const FACING = { u: 'up', d: 'down', l: 'left', r: 'right' };
const rnd = (v) => Math.floor(v + 0.5);
const EPS = 1e-6;
const isInt = (v) => Math.abs(v - Math.round(v)) < EPS;
const idxOf = (x, y, W) => rnd(y) * W + rnd(x);

export class Predictor {
  constructor(info) {
    this.W = info.w;
    this.H = info.h;
    this.floor = info.floor;
    this.rules = info.rules;
    this.tele = new Map();
    const pos = {};
    for (let i = 0; i < this.floor.length; i++) {
      const c = this.floor[i];
      if (c >= '1' && c <= '9') (pos[c] = pos[c] || []).push(i);
    }
    for (const [a, b] of Object.values(pos)) {
      this.tele.set(a, b);
      this.tele.set(b, a);
    }
    this.ready = false;
    this.tapDir = null;
  }

  /** 用服务器状态硬同步 */
  sync(sp) {
    this.x = sp.x;
    this.y = sp.y;
    this.isMoving = !!sp.m;
    this.facing = FACING[sp.f] || 'down';
    this.teleLock = !!sp.tl;
    this.ready = true;
  }

  tap(dir) { this.tapDir = dir; }

  /**
   * 推进 dt 秒（与 game.py _move_player 相同的自由移动 + 滑角规则）。
   * world = { blocks: string, bombAt(x, y): bool, speedLv, trapped, dir }
   */
  step(dt, world) {
    if (!this.ready) return;
    const W = this.W;
    const idx = (x, y) => rnd(y) * W + rnd(x);
    const canEnter = (x, y) => {
      if (x < 0 || y < 0 || x >= W || y >= this.H) return false;
      if (BLOCKING.has(world.blocks[y * W + x])) return false;
      return !world.bombAt(x, y);
    };
    const assist = this.rules.cornerAssist ?? 0.6;
    let speed = this.rules.baseSpeed * (1 + this.rules.speedStep * world.speedLv);
    if (this.floor[idx(this.x, this.y)] === 'i') speed *= this.rules.iceMult;
    if (world.trapped) speed *= this.rules.trapSpeed;
    let dist = speed * dt;
    let tap = this.tapDir;
    this.tapDir = null;
    this.isMoving = false;
    for (let guard = 0; guard < 8 && dist > EPS; guard++) {
      const held = world.dir || tap;
      const d = held || CONVEYOR[this.floor[idx(this.x, this.y)]];
      if (!d) break;
      if (held) this.facing = held;
      const [dx, dy] = DIRS[d];
      const horiz = dx !== 0;
      const sgn = dx || dy;
      let m = horiz ? this.x : this.y;
      let q = horiz ? this.y : this.x;
      if (!isInt(m)) {
        const t = sgn > 0 ? Math.ceil(m) : Math.floor(m);
        const step = Math.min(dist, Math.abs(t - m));
        m = Math.abs(t - m) - step < EPS ? t : m + sgn * step;
        dist -= step;
      } else {
        m = Math.round(m);
        const nm = m + sgn;
        const lanes = isInt(q) ? [Math.round(q)] : [Math.floor(q), Math.ceil(q)];
        const cell = (L) => (horiz ? [nm, L] : [L, nm]);
        const free = lanes.filter((L) => canEnter(...cell(L)));
        if (free.length === lanes.length) {
          const step = Math.min(dist, 1);
          m = 1 - step < EPS ? nm : m + sgn * step;
          dist -= step;
        } else if (free.length) {
          const L = free[0];
          const gap = Math.abs(L - q);
          if (gap > assist) break;
          const step = Math.min(dist, gap);
          q = gap - step < EPS ? L : q + Math.sign(L - q) * step;
          dist -= step;
        } else {
          // 正前方是炸弹且有踢弹能力：请求服务器踢出（是否成立由服务器判定）
          if (lanes.length === 1 && held === d && world.kick && !world.trapped && world.realBombAt?.(...cell(lanes[0]))) {
            this.kickReq = cell(lanes[0]);
          }
          break;
        }
      }
      if (horiz) { this.x = m; this.y = q; } else { this.x = q; this.y = m; }
      this.isMoving = true;
      if (world.dir) tap = null;
    }
    this.checkTele(world);
  }

  checkTele(world) {
    const i = idxOf(this.x, this.y, this.W);
    const dest = this.tele.get(i);
    if (dest === undefined) {
      this.teleLock = false;
      return;
    }
    const cx = i % this.W, cy = Math.floor(i / this.W);
    const snap = this.rules.teleSnap ?? 0.2;
    if (this.teleLock || Math.abs(this.x - cx) > snap || Math.abs(this.y - cy) > snap) return;
    const dx = dest % this.W, dy = Math.floor(dest / this.W);
    if (world.bombAt(dx, dy)) return;
    this.x = dx;
    this.y = dy;
    this.teleLock = true;
    this.teleported = true;
  }

  get moving() { return this.isMoving; }
}
