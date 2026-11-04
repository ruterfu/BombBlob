// 原创程序化音乐 + 音效（Web Audio，无需音频文件）
// 每首曲子由「和弦进行 + 随机种子 + 配器」生成固定旋律：同一首歌每次听都一样。
// 每张地图有自己的配器（主奏音色、低音型、琶音型、鼓组、环境声、音阶、速度、空间感），按地图风格与玩法设计。

const SCALES = {
  major: [0, 2, 4, 5, 7, 9, 11],
  minor: [0, 2, 3, 5, 7, 8, 10],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  mixo: [0, 2, 4, 5, 7, 9, 10],
  harm: [0, 2, 3, 5, 7, 8, 11],
  phryg: [0, 1, 3, 5, 7, 8, 10],
  lydian: [0, 2, 4, 6, 7, 9, 11],
  hijaz: [0, 1, 4, 5, 7, 8, 10], // 阿拉伯风（沙漠）
  pent: [0, 2, 4, 7, 9], // 大调五声
  minpent: [0, 3, 5, 7, 10], // 小调五声
  hira: [0, 2, 3, 7, 8], // 平调子（和风）
};

/*
 * 曲目参数
 *   lead   主奏：saw 锯齿 / square 芯片方波 / tri 三角 / pluck 拨弦 / koto 古筝 / flute 长笛（颤音） /
 *          bell 钟琴（FM） / glass 玻璃电钢 / brass 铜管 / sweep 扫频合成 / dist 失真
 *   bass   低音型：root / walk 行走 / octave 八度跳 / drone 持续 / pulse 八分脉冲 / pulse16 / march
 *   bassTone 低音音色：saw / sine / square
 *   arp    琶音：up / updown / broken / fast / none
 *   drums  鼓组：four / tribal / soft / taiko / industrial / breakbeat / march / shuffle / none
 *   tex    环境声：wind / water / crackle / ticks / shimmer / insects / crowd / ping（可多个）
 *   pad    铺底：warm / glass / choir / none
 *   density 旋律密度（1 = 正常），cutoff 音色明暗，delay [时间, 反馈, 湿声]
 */
export const TRACKS = {
  lobby: { title: 'Standby', bpm: 92, root: 57, scale: 'minor', prog: [0, 5, 2, 6], seed: 7, lead: 'tri', bass: 'root', bassTone: 'saw', arp: 'up', drums: 'soft', pad: 'warm', cutoff: 2600, delay: [0.32, 0.28, 0.22] },
  // 遗迹广场：林荫大道上的冒险进行曲（铜管 + 进行曲军鼓 + 行走低音）
  meadow: { title: 'Ruins Run', bpm: 118, root: 55, scale: 'dorian', prog: [0, 6, 5, 6, 0, 3, 4, 4], seed: 3, lead: 'brass', bass: 'walk', bassTone: 'saw', arp: 'broken', drums: 'march', pad: 'warm', cutoff: 3000, delay: [0.25, 0.22, 0.18] },
  // 冰霜湖：冷冽的钟琴、持续低音和风声，冰面打滑的轻盈感
  frost: { title: 'Cold Front', bpm: 100, root: 52, scale: 'minor', prog: [0, 5, 3, 4], seed: 21, lead: 'bell', bass: 'drone', bassTone: 'sine', arp: 'fast', drums: 'soft', pad: 'glass', tex: ['wind'], bell: true, density: 0.8, cutoff: 4200, delay: [0.42, 0.38, 0.3] },
  // 丛林秘境：马林巴、部落鼓、虫鸣，摇摆的节奏
  jungle: { title: 'Undergrowth', bpm: 112, root: 50, scale: 'minpent', prog: [0, 3, 0, 4], seed: 42, lead: 'pluck', bass: 'octave', bassTone: 'sine', arp: 'broken', drums: 'tribal', pad: 'none', tex: ['insects'], swing: 0.14, cutoff: 3200, delay: [0.28, 0.2, 0.16] },
  // 霓虹传送站：合成器波、八分脉冲低音、四拍舞曲
  neon: { title: 'Gridline', bpm: 128, root: 57, scale: 'minor', prog: [0, 5, 2, 6], seed: 99, lead: 'sweep', bass: 'pulse', bassTone: 'saw', arp: 'fast', drums: 'four', pad: 'warm', tex: ['ping'], cutoff: 5200, delay: [0.35, 0.35, 0.26] },
  // 熔铸工厂：工业金属打击、失真主奏、机器滴答
  foundry: { title: 'Molten Core', bpm: 132, root: 52, scale: 'phryg', prog: [0, 0, 1, 0], seed: 13, lead: 'dist', bass: 'pulse16', bassTone: 'square', arp: 'none', drums: 'industrial', pad: 'none', tex: ['ticks'], density: 0.8, cutoff: 2400, delay: [0.18, 0.15, 0.12] },
  // 沙暴峡谷：阿拉伯音阶长笛、持续低音、手鼓、风沙
  desert: { title: 'Dust Devil', bpm: 104, root: 50, scale: 'hijaz', prog: [0, 1, 0, 6], seed: 57, lead: 'flute', bass: 'drone', bassTone: 'saw', arp: 'none', drums: 'tribal', pad: 'choir', tex: ['wind'], swing: 0.08, cutoff: 2800, delay: [0.38, 0.3, 0.24] },
  // 午夜港口：黑色电影爵士，行走低音、刷鼓、玻璃电钢、水声
  harbor: { title: 'Night Shift', bpm: 92, root: 53, scale: 'dorian', prog: [0, 3, 1, 4], seed: 77, lead: 'glass', bass: 'walk', bassTone: 'sine', arp: 'none', drums: 'shuffle', pad: 'warm', tex: ['water'], swing: 0.2, density: 0.7, cutoff: 2200, delay: [0.3, 0.3, 0.22] },
  // 云顶神殿：利底亚音阶的钟琴与圣咏铺底，空灵开阔
  temple: { title: 'Skyward', bpm: 108, root: 57, scale: 'lydian', prog: [0, 1, 4, 0], seed: 31, lead: 'bell', bass: 'drone', bassTone: 'sine', arp: 'updown', drums: 'soft', pad: 'choir', tex: ['shimmer'], bell: true, cutoff: 4600, delay: [0.45, 0.4, 0.32] },
  // 樱花庭院：平调子古筝、轻太鼓、长回声，适合埋伏的从容
  sakura: { title: 'Petal Drift', bpm: 96, root: 57, scale: 'hira', prog: [0, 3, 1, 0], seed: 64, lead: 'koto', bass: 'root', bassTone: 'sine', arp: 'broken', drums: 'taiko', pad: 'glass', tex: ['shimmer'], density: 0.75, cutoff: 3600, delay: [0.4, 0.34, 0.28] },
  // 雷鸣矿坑：急促的芯片方波、碎拍、导火索嘶嘶声——连环爆破的紧张感
  mine: { title: 'Fuse Line', bpm: 142, root: 48, scale: 'minor', prog: [0, 0, 6, 4], seed: 88, lead: 'square', bass: 'octave', bassTone: 'square', arp: 'fast', drums: 'breakbeat', pad: 'none', tex: ['crackle'], cutoff: 3000, delay: [0.2, 0.18, 0.14] },
  // 极光冰川：缓慢的玻璃音色与长铺底，闸门升降般的呼吸感
  glacier: { title: 'Aurora', bpm: 84, root: 54, scale: 'lydian', prog: [0, 4, 5, 1], seed: 19, lead: 'glass', bass: 'drone', bassTone: 'sine', arp: 'up', drums: 'none', pad: 'choir', tex: ['wind', 'shimmer'], bell: true, density: 0.6, cutoff: 3800, delay: [0.55, 0.45, 0.35] },
  // 星际空港：扫频合成、16 分脉冲、雷达提示音
  starport: { title: 'Orbit', bpm: 124, root: 55, scale: 'dorian', prog: [0, 6, 5, 4], seed: 111, lead: 'sweep', bass: 'pulse16', bassTone: 'saw', arp: 'up', drums: 'four', pad: 'glass', tex: ['ping'], cutoff: 4800, delay: [0.375, 0.4, 0.28] },
  // 烈日斗兽场：太鼓、铜管号角、观众欢呼，正面对决
  arena: { title: 'Gladius', bpm: 120, root: 52, scale: 'harm', prog: [0, 5, 0, 4], seed: 45, lead: 'brass', bass: 'march', bassTone: 'saw', arp: 'none', drums: 'taiko', pad: 'warm', tex: ['crowd'], cutoff: 3200, delay: [0.25, 0.2, 0.16] },
  // 火山孤岛：失真主奏、工业鼓、熔岩噼啪，节奏最快
  volcano: { title: 'Eruption', bpm: 146, root: 50, scale: 'hijaz', prog: [0, 1, 5, 4], seed: 73, lead: 'dist', bass: 'pulse', bassTone: 'saw', arp: 'fast', drums: 'industrial', pad: 'none', tex: ['crackle'], cutoff: 2600, delay: [0.2, 0.2, 0.14] },
};
TRACKS.candy = TRACKS.foundry;
TRACKS.lava = TRACKS.foundry;

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const midiHz = (m) => 440 * Math.pow(2, (m - 69) / 12);

/** 每个鼓组在 16 步里的击打 */
function drumHits(kit, s, bar, rnd) {
  const h = {};
  switch (kit) {
    case 'four': h.kick = s % 4 === 0; h.snare = s === 4 || s === 12; h.hat = s % 2 === 1; h.clap = s === 12 && bar % 2 === 1; break;
    case 'tribal': h.kick = s === 0 || s === 6 || s === 10; h.tom = s === 3 || s === 11 || (s === 14 && bar % 2); h.snare = s === 4 || s === 12; h.shaker = s % 2 === 0; break;
    case 'soft': h.kick = s === 0 || s === 10; h.rim = s === 8; h.hat = s % 4 === 2; break;
    case 'taiko': h.taiko = s === 0 || s === 3 || s === 8 || (s === 11 && bar % 2 === 1); h.tom = s === 6 || s === 14; h.clap = s === 12; break;
    case 'industrial': h.kick = s === 0 || s === 8 || s === 10; h.metal = s === 4 || s === 12 || (s === 7 && rnd() < 0.5); h.shaker = true; break;
    case 'breakbeat': h.kick = s === 0 || s === 10 || (s === 3 && bar % 2 === 1); h.snare = s === 4 || s === 12; h.ghost = s === 7 || s === 15; h.hat = s % 2 === 0; break;
    case 'march': h.kick = s === 0 || s === 8; h.snare = [0, 3, 4, 6, 8, 10, 11, 12, 14].includes(s); h.ghost = s % 2 === 1; break;
    case 'shuffle': h.kick = s === 0 || s === 10; h.brush = s % 2 === 0; h.rim = s === 4 || s === 12; break;
    default: break;
  }
  return h;
}

/** 把曲子参数编排成 16 小节 × 16 步的音符表 */
function compose(def) {
  const rnd = mulberry32(def.seed);
  const sc = SCALES[def.scale];
  const n7 = sc.length;
  const third = n7 >= 7 ? 2 : 1, fifth = n7 >= 7 ? 4 : 2, sev = n7 >= 7 ? 6 : 4; // 五声音阶的和弦按级数折算
  const deg = (d, oct = 0) => {
    const o = Math.floor(d / n7);
    const k = ((d % n7) + n7) % n7;
    return def.root + sc[k] + 12 * (o + oct);
  };
  const dens = def.density ?? 1;
  // 旋律动机：A、B 两个两小节乐句，按 A A' B A 组织
  const motif = () => {
    const notes = [];
    let pos = 2 + Math.floor(rnd() * 3);
    for (let s = 0; s < 32; s++) {
      const strong = s % 4 === 0;
      if (rnd() < (strong ? 0.75 : 0.32) * dens) {
        pos += Math.round((rnd() - 0.5) * 4);
        pos = Math.max(-1, Math.min(9, pos));
        const len = rnd() < 0.3 / dens ? 2 + (dens < 0.8 ? 1 : 0) : 1;
        notes.push({ s, d: pos, len });
      }
    }
    return notes;
  };
  const A = motif(), B = motif();
  const vary = (m) => m.map((n) => ({ ...n, d: n.s >= 24 ? n.d + (rnd() < 0.5 ? 1 : -1) : n.d }));
  const form = [A, vary(A), B, A];
  const ARP = { up: [0, third, fifth, n7], updown: [0, third, fifth, third], broken: [0, fifth, third, fifth], fast: [0, third, fifth, n7, fifth, third] };
  const steps = [];
  for (let bar = 0; bar < 16; bar++) {
    const chord = def.prog[bar % def.prog.length];
    const next = def.prog[(bar + 1) % def.prog.length];
    const phrase = form[Math.floor(bar / 2) % 4];
    for (let s = 0; s < 16; s++) {
      const step = { lead: null, bass: null, arp: null, bell: null };
      const gs = (bar % 2) * 16 + s;
      const n = phrase.find((x) => x.s === gs);
      if (n) step.lead = { m: deg(chord + n.d, 1), len: n.len };
      // 低音
      const root = deg(chord, -1);
      switch (def.bass) {
        case 'walk': if (s % 4 === 0) step.bass = { m: s === 12 ? deg(next, -1) - 1 : deg(chord + [0, third, fifth, 0][s / 4], -1), len: 3.6 }; break;
        case 'octave': if (s % 2 === 0) step.bass = { m: root + (s % 4 === 2 ? 12 : 0), len: 1.6 }; break;
        case 'drone': if (s === 0 && bar % 2 === 0) step.bass = { m: root, len: 30 }; break;
        case 'pulse': if (s % 2 === 0) step.bass = { m: root, len: 1.4 }; break;
        case 'pulse16': step.bass = { m: root + (s === 14 ? 12 : 0), len: 0.8 }; break;
        case 'march': if (s % 4 === 0) step.bass = { m: s % 8 === 0 ? root : deg(chord + fifth, -1), len: 2.5 }; break;
        default: if (s === 0 || s === 8 || s === 11) step.bass = { m: root, len: 1.8 }; break;
      }
      // 琶音
      const pat = ARP[def.arp];
      if (pat) {
        const every = def.arp === 'fast' ? 1 : 2;
        if (s % every === 0) step.arp = deg(chord + pat[(s / every) % pat.length], 0);
      }
      step.drum = drumHits(def.drums, s, bar, rnd);
      if (def.bell && s === 0 && bar % 2 === 0) step.bell = deg(chord + fifth, 2);
      if (s === 0) step.chord = [deg(chord, 0), deg(chord + third, 0), deg(chord + fifth, 0), deg(chord + sev, -1)];
      step.r = rnd(); // 环境声用的确定性随机数
      steps.push(step);
    }
  }
  return steps;
}

class AudioEngine {
  constructor() {
    this.ctx = null;
    this.musicVol = Number(localStorage.getItem('bb_music') ?? 0.5);
    this.sfxVol = Number(localStorage.getItem('bb_sfx') ?? 0.7);
    this.track = null;
    this.steps = null;
    this.stepIdx = 0;
    this.nextTime = 0;
    this.timer = null;
    this.cache = {};
  }

  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.connect(this.ctx.destination);
      this.music = this.ctx.createGain();
      this.music.gain.value = this.musicVol * 0.35;
      // 音乐总线：低通滤波 + 延迟回声，让音色更柔和、有空间感
      this.musicFilter = this.ctx.createBiquadFilter();
      this.musicFilter.type = 'lowpass';
      this.musicFilter.frequency.value = 2600;
      this.musicFilter.Q.value = 0.6;
      this.musicIn = this.ctx.createGain();
      this.musicIn.connect(this.musicFilter);
      this.musicFilter.connect(this.music);
      const delay = (this.delay = this.ctx.createDelay(1));
      delay.delayTime.value = 0.32;
      const fb = (this.delayFb = this.ctx.createGain());
      fb.gain.value = 0.28;
      const wet = (this.delayWet = this.ctx.createGain());
      wet.gain.value = 0.22;
      this.musicFilter.connect(delay);
      delay.connect(fb).connect(delay);
      delay.connect(wet).connect(this.music);
      this.music.connect(this.master);
      this.sfx = this.ctx.createGain();
      this.sfx.gain.value = this.sfxVol;
      this.sfx.connect(this.master);
      const len = this.ctx.sampleRate;
      this.noiseBuf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
      const d = this.noiseBuf.getChannelData(0);
      for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    if (this.pending) {
      const p = this.pending;
      this.pending = null;
      this.play(p);
    }
  }

  setMusicVolume(v) {
    this.musicVol = v;
    localStorage.setItem('bb_music', v);
    if (this.music) this.music.gain.setTargetAtTime(v * 0.35, this.ctx.currentTime, 0.05);
  }

  setSfxVolume(v) {
    this.sfxVol = v;
    localStorage.setItem('bb_sfx', v);
    if (this.sfx) this.sfx.gain.setTargetAtTime(v, this.ctx.currentTime, 0.05);
  }

  play(name) {
    if (!this.ctx) { this.pending = name; return; }
    if (this.track === name) return;
    const def = TRACKS[name];
    if (!def) return;
    this.track = name;
    this.def = def;
    this.steps = this.cache[name] || (this.cache[name] = compose(def));
    // 每首曲子自己的音色明暗与空间感
    const now = this.ctx.currentTime;
    const [dt, dfb, dwet] = def.delay || [0.32, 0.28, 0.22];
    this.musicFilter.frequency.setTargetAtTime(def.cutoff || 2600, now, 0.2);
    this.delay.delayTime.setTargetAtTime(dt, now, 0.1);
    this.delayFb.gain.setTargetAtTime(dfb, now, 0.1);
    this.delayWet.gain.setTargetAtTime(dwet, now, 0.1);
    this.stepIdx = 0;
    this.nextTime = this.ctx.currentTime + 0.08;
    if (!this.timer) this.timer = setInterval(() => this.schedule(), 25);
  }

  stop() {
    this.track = null;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  schedule() {
    if (!this.ctx || !this.steps) return;
    const def = this.def;
    const stepDur = 60 / def.bpm / 4;
    while (this.nextTime < this.ctx.currentTime + 0.12) {
      const st = this.steps[this.stepIdx];
      let t = this.nextTime;
      if (def.swing && this.stepIdx % 2 === 1) t += stepDur * def.swing;
      const bus = this.musicIn;
      if (st.lead) this.voice(bus, midiHz(st.lead.m), t, stepDur * st.lead.len * 0.9, def.lead);
      if (st.bass) this.bassVoice(bus, st.bass.m, t, stepDur * st.bass.len, def.bassTone);
      if (st.arp) this.tone(bus, midiHz(st.arp + 12), t, stepDur * 0.4, def.lead === 'square' ? 'square' : 'triangle', def.lead === 'square' ? 0.02 : 0.035);
      if (st.chord && def.pad && def.pad !== 'none') this.pad(bus, st.chord, t, stepDur * 15, def.pad);
      if (st.bell) this.voice(bus, midiHz(st.bell), t, stepDur * 6, 'bell', 0.6);
      this.drums(st.drum, t);
      for (const tx of def.tex || []) this.texture(tx, st, t, stepDur, this.stepIdx);
      this.nextTime += stepDur;
      this.stepIdx = (this.stepIdx + 1) % this.steps.length;
    }
  }

  /** 主奏音色 */
  voice(dest, f, t, dur, preset, scale = 1) {
    const c = this.ctx;
    switch (preset) {
      case 'square': this.tone(dest, f, t, dur, 'square', 0.05 * scale, 0.003, 0.05); break;
      case 'tri': this.tone(dest, f, t, dur, 'triangle', 0.12 * scale, 0.01, 0.12); break;
      case 'pluck':
        this.tone(dest, f, t, 0.05, 'triangle', 0.16 * scale, 0.002, 0.28);
        this.tone(dest, f * 2, t, 0.03, 'sine', 0.06 * scale, 0.002, 0.15);
        break;
      case 'koto': {
        const o = this.tone(dest, f * 1.03, t, 0.06, 'triangle', 0.15 * scale, 0.002, 0.5);
        o.frequency.exponentialRampToValueAtTime(f, t + 0.05);
        this.tone(dest, f * 3, t, 0.02, 'sine', 0.04 * scale, 0.001, 0.2);
        break;
      }
      case 'flute': {
        const o = this.tone(dest, f, t, dur, 'sine', 0.14 * scale, 0.06, 0.12);
        const lfo = c.createOscillator(), lg = c.createGain();
        lfo.frequency.value = 5.2;
        lg.gain.setValueAtTime(0, t);
        lg.gain.linearRampToValueAtTime(f * 0.012, t + 0.25);
        lfo.connect(lg).connect(o.frequency);
        lfo.start(t);
        lfo.stop(t + dur + 0.2);
        this.noise(dest, t, 0.08, 3000, 0.02 * scale, 'bandpass'); // 气声
        break;
      }
      case 'bell': {
        // FM 钟琴：调制器比例 3.5，调制深度随时间衰减
        const car = c.createOscillator(), mod = c.createOscillator(), mg = c.createGain(), g = c.createGain();
        car.frequency.value = f;
        mod.frequency.value = f * 3.5;
        mg.gain.setValueAtTime(f * 2, t);
        mg.gain.exponentialRampToValueAtTime(f * 0.05, t + 1.2);
        g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(0.09 * scale, t + 0.004);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 1.2);
        mod.connect(mg).connect(car.frequency);
        car.connect(g).connect(dest);
        car.start(t); mod.start(t);
        car.stop(t + dur + 1.3); mod.stop(t + dur + 1.3);
        break;
      }
      case 'glass':
        this.tone(dest, f, t, dur, 'sine', 0.1 * scale, 0.005, 0.6);
        this.tone(dest, f * 2, t, dur * 0.5, 'triangle', 0.03 * scale, 0.005, 0.4);
        break;
      case 'brass':
      case 'sweep':
      case 'dist': {
        const o = c.createOscillator(), fl = c.createBiquadFilter(), g = c.createGain();
        o.type = 'sawtooth';
        o.frequency.value = f;
        fl.type = 'lowpass';
        fl.Q.value = preset === 'sweep' ? 8 : 2;
        const lo = preset === 'sweep' ? 300 : 700, hi = preset === 'sweep' ? 4200 : preset === 'dist' ? 3200 : 2600;
        fl.frequency.setValueAtTime(lo, t);
        fl.frequency.linearRampToValueAtTime(hi, t + (preset === 'sweep' ? dur * 0.8 : 0.06));
        fl.frequency.exponentialRampToValueAtTime(lo * 1.3, t + dur + 0.1);
        let out = fl;
        if (preset === 'dist') {
          const ws = c.createWaveShaper();
          ws.curve = this.distCurve || (this.distCurve = makeDist(6));
          fl.connect(ws);
          out = ws;
          const o2 = c.createOscillator();
          o2.type = 'square';
          o2.frequency.value = f * 1.007;
          o2.connect(fl);
          o2.start(t);
          o2.stop(t + dur + 0.15);
        }
        const v = (preset === 'dist' ? 0.035 : 0.075) * scale;
        g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(v, t + (preset === 'brass' ? 0.03 : 0.008));
        g.gain.setValueAtTime(v, t + Math.max(0.03, dur - 0.05));
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.12);
        o.connect(fl);
        out.connect(g).connect(dest);
        o.start(t);
        o.stop(t + dur + 0.15);
        break;
      }
      default: this.tone(dest, f, t, dur, 'sawtooth', 0.07 * scale, 0.01, 0.12);
    }
  }

  bassVoice(dest, m, t, dur, tone) {
    if (tone === 'sine') {
      this.tone(dest, midiHz(m), t, dur, 'sine', 0.32, 0.005, 0.12);
      this.tone(dest, midiHz(m + 12), t, dur * 0.6, 'triangle', 0.05, 0.005, 0.08);
    } else {
      this.tone(dest, midiHz(m), t, dur, tone === 'square' ? 'square' : 'sawtooth', tone === 'square' ? 0.06 : 0.11, 0.005, 0.1);
      this.tone(dest, midiHz(m - 12), t, dur, 'sine', 0.28, 0.005, 0.1);
    }
  }

  pad(dest, chord, t, dur, kind) {
    const type = kind === 'glass' ? 'sine' : kind === 'choir' ? 'triangle' : 'sawtooth';
    const vol = kind === 'warm' ? 0.025 : kind === 'choir' ? 0.045 : 0.04;
    for (const m of chord) {
      this.tone(dest, midiHz(m), t, dur, type, vol, kind === 'choir' ? 1.2 : 0.6, 1.2);
      if (kind === 'choir') this.tone(dest, midiHz(m) * 1.004, t, dur, 'triangle', vol * 0.6, 1.4, 1.2); // 轻微失谐，像合唱
    }
  }

  drums(h, t) {
    if (!h) return;
    const m = this.music;
    if (h.kick) this.kick(m, t, 0.6);
    if (h.snare) this.noise(m, t, 0.16, 1400, 0.16, 'bandpass');
    if (h.ghost) this.noise(m, t, 0.05, 1600, 0.05, 'bandpass');
    if (h.hat) this.noise(m, t, 0.025, 9000, 0.045, 'highpass');
    if (h.shaker) this.noise(m, t, 0.03, 7000, 0.025, 'highpass');
    if (h.brush) this.noise(m, t, 0.09, 5000, 0.03, 'bandpass');
    if (h.rim) this.tone(m, 1800, t, 0.015, 'triangle', 0.08, 0.001, 0.02);
    if (h.clap) for (let k = 0; k < 3; k++) this.noise(m, t + k * 0.012, 0.08, 1800, 0.09, 'bandpass');
    if (h.tom) this.drumTone(m, t, 200, 110, 0.25, 0.4);
    if (h.taiko) {
      this.drumTone(m, t, 120, 55, 0.5, 0.75);
      this.noise(m, t, 0.12, 400, 0.15, 'lowpass');
    }
    if (h.metal) {
      // 金属撞击：两个不和谐的方波 + 高频噪声
      this.tone(m, 540, t, 0.02, 'square', 0.04, 0.001, 0.12);
      this.tone(m, 803, t, 0.02, 'square', 0.03, 0.001, 0.1);
      this.noise(m, t, 0.12, 3500, 0.1, 'bandpass');
    }
  }

  drumTone(dest, t, f0, f1, dur, vol) {
    const o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(f1, t + dur * 0.6);
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  /** 环境声 */
  texture(kind, st, t, stepDur, idx) {
    const m = this.music, r = st.r;
    switch (kind) {
      case 'wind': if (idx % 32 === 0) this.swell(m, t, stepDur * 30, 600 + r * 500, 0.05, 1.5); break;
      case 'water':
        if (r < 0.1) { const o = this.tone(m, 1400 + r * 4000, t, 0.03, 'sine', 0.05, 0.001, 0.05); o.frequency.exponentialRampToValueAtTime(500, t + 0.06); }
        if (idx % 64 === 0) this.swell(m, t, stepDur * 60, 350, 0.03, 0.7);
        break;
      case 'crackle': if (r < 0.3) this.noise(m, t + r * stepDur, 0.015, 2500 + r * 5000, 0.05 + r * 0.08, 'highpass'); break;
      case 'ticks': if (idx % 2 === 0) this.tone(m, idx % 8 === 0 ? 2400 : 3200, t, 0.008, 'square', 0.012, 0.001, 0.01); break;
      case 'shimmer': if (r < 0.12 && st.arp != null) this.tone(m, midiHz(st.arp + 36), t, 0.1, 'sine', 0.025, 0.01, 0.5); break;
      case 'insects': if (r < 0.08) for (let k = 0; k < 3; k++) this.tone(m, 4200 + r * 1500, t + k * 0.035, 0.012, 'square', 0.008, 0.001, 0.01); break;
      case 'crowd': if (idx % 64 === 48) this.swell(m, t, stepDur * 14, 1100, 0.06, 0.6); break;
      case 'ping': if (idx % 32 === 16) this.tone(m, 1760, t, 0.05, 'sine', 0.05, 0.002, 0.4); break;
      default: break;
    }
  }

  /** 慢慢涌起又退去的过滤噪声（风 / 浪 / 人群） */
  swell(dest, t, dur, freq, vol, q) {
    const c = this.ctx, s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    s.buffer = this.noiseBuf;
    s.loop = true;
    f.type = 'bandpass';
    f.frequency.setValueAtTime(freq, t);
    f.frequency.linearRampToValueAtTime(freq * 1.6, t + dur / 2);
    f.frequency.linearRampToValueAtTime(freq, t + dur);
    f.Q.value = q;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t + dur / 2);
    g.gain.linearRampToValueAtTime(0.0001, t + dur);
    s.connect(f).connect(g).connect(dest);
    s.start(t, Math.random() * 0.5);
    s.stop(t + dur + 0.05);
  }

  tone(dest, freq, t, dur, type = 'square', vol = 0.2, attack = 0.005, release = 0.06) {
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + attack);
    g.gain.setValueAtTime(vol, t + Math.max(attack, dur - release));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur + release);
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + dur + release + 0.02);
    return o;
  }

  kick(dest, t, vol) {
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.frequency.setValueAtTime(150, t);
    o.frequency.exponentialRampToValueAtTime(40, t + 0.12);
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.18);
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + 0.2);
  }

  noise(dest, t, dur, freq, vol, ftype = 'lowpass') {
    const s = this.ctx.createBufferSource();
    s.buffer = this.noiseBuf;
    const f = this.ctx.createBiquadFilter();
    f.type = ftype;
    f.frequency.value = freq;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    s.connect(f).connect(g).connect(dest);
    s.start(t, Math.random() * 0.5);
    s.stop(t + dur + 0.02);
  }

  /** 放炸弹：每种炸弹特效有自己的声音 */
  placeFx(d, t, v, st) {
    switch (st) {
      case 'poison': // 冒泡：三个上升的气泡音 + 嘶嘶声
        [420, 560, 760].forEach((f, i) => { const o = this.tone(d, f, t + i * 0.045, 0.03, 'sine', 0.22 * v, 0.002, 0.04); o.frequency.exponentialRampToValueAtTime(f * 1.6, t + i * 0.045 + 0.05); });
        this.noise(d, t, 0.2, 5000, 0.05 * v, 'highpass');
        break;
      case 'water': { // 「咕咚」：快速下滑的水滴音
        const o = this.tone(d, 900, t, 0.08, 'sine', 0.32 * v, 0.002, 0.06);
        o.frequency.exponentialRampToValueAtTime(220, t + 0.1);
        this.noise(d, t + 0.02, 0.08, 1800, 0.06 * v, 'bandpass');
        break;
      }
      case 'gold': // 金币般清脆的金属叮声
        this.tone(d, midiHz(88), t, 0.05, 'triangle', 0.16 * v, 0.001, 0.3);
        this.tone(d, midiHz(95), t + 0.05, 0.08, 'sine', 0.13 * v, 0.001, 0.4);
        this.tone(d, 330, t, 0.04, 'sine', 0.2 * v);
        break;
      default: { // 普通：沉闷的「咚」
        const o = this.tone(d, 330, t, 0.06, 'sine', 0.35 * v);
        o.frequency.exponentialRampToValueAtTime(180, t + 0.08);
      }
    }
  }

  /** 爆炸：每种炸弹特效有自己的声音 */
  boomFx(d, t, v, st) {
    switch (st) {
      case 'poison': // 低沉的毒气喷涌 + 咕嘟咕嘟
        this.kick(d, t, 0.7 * v);
        this.swell(d, t, 0.9, 500, 0.35 * v, 0.8);
        for (let k = 0; k < 5; k++) {
          const f = 200 + Math.random() * 300, tt = t + 0.08 + k * 0.09;
          const o = this.tone(d, f, tt, 0.04, 'sine', 0.12 * v, 0.003, 0.05);
          o.frequency.exponentialRampToValueAtTime(f * 1.8, tt + 0.06);
        }
        break;
      case 'water': { // 「哗啦」：水花 + 下坠的低音
        this.kick(d, t, 0.6 * v);
        this.noise(d, t, 0.55, 2400, 0.4 * v, 'highpass');
        const o = this.tone(d, 420, t, 0.3, 'sine', 0.35 * v, 0.002, 0.15);
        o.frequency.exponentialRampToValueAtTime(70, t + 0.35);
        for (let k = 0; k < 4; k++) this.tone(d, 1200 + Math.random() * 1600, t + 0.15 + k * 0.07, 0.02, 'sine', 0.05 * v, 0.001, 0.05);
        break;
      }
      case 'gold': // 爆炸 + 一串金光闪闪的钟声
        this.noise(d, t, 0.4, 1200, 0.5 * v, 'lowpass');
        this.kick(d, t, 0.85 * v);
        [0, 4, 7, 12].forEach((s, i) => this.voice(d, midiHz(84 + s), t + 0.04 + i * 0.06, 0.15, 'bell', 1.6 * v));
        break;
      default:
        this.noise(d, t, 0.45, 900, 0.7 * v, 'lowpass');
        this.kick(d, t, 0.9 * v);
    }
  }

  /** 音效 */
  fx(name, opts = {}) {
    if (!this.ctx || this.ctx.state !== 'running') return;
    const t = this.ctx.currentTime + 0.005;
    const d = this.sfx;
    const v = opts.vol ?? 1;
    switch (name) {
      case 'place': this.placeFx(d, t, v, opts.st); break;
      case 'boom': this.boomFx(d, t, v, opts.st); break;
      case 'crate':
        this.noise(d, t, 0.12, 2500, 0.2 * v, 'bandpass');
        break;
      case 'pick':
        [0, 7, 12].forEach((s, i) => this.tone(d, midiHz(79 + s), t + i * 0.05, 0.12, 'triangle', 0.14 * v));
        break;
      case 'hit': {
        const o = this.tone(d, 520, t, 0.25, 'sawtooth', 0.18 * v);
        o.frequency.exponentialRampToValueAtTime(120, t + 0.25);
        break;
      }
      case 'die':
        [0, -5, -12].forEach((s, i) => this.tone(d, midiHz(55 + s), t + i * 0.1, 0.18, 'sawtooth', 0.08 * v));
        break;
      case 'shield':
        this.tone(d, 880, t, 0.15, 'triangle', 0.25 * v);
        this.tone(d, 1320, t + 0.06, 0.18, 'triangle', 0.2 * v);
        break;
      case 'tele': {
        const o = this.tone(d, 300, t, 0.3, 'sine', 0.25 * v);
        o.frequency.exponentialRampToValueAtTime(1600, t + 0.3);
        break;
      }
      case 'kick':
        this.noise(d, t, 0.06, 600, 0.4 * v, 'lowpass');
        break;
      case 'beep':
        this.tone(d, 880, t, 0.12, 'sine', 0.2 * v);
        break;
      case 'go':
        this.tone(d, 1320, t, 0.4, 'sine', 0.22 * v);
        this.tone(d, 660, t, 0.4, 'triangle', 0.15 * v);
        break;
      case 'wall':
        this.kick(d, t, 0.35 * v);
        break;
      case 'sd':
        [0, 1, 0, 1].forEach((s, i) => this.tone(d, midiHz(64 + s * 3), t + i * 0.22, 0.2, 'sawtooth', 0.07 * v));
        break;
      case 'win':
        [0, 7, 12, 16, 19].forEach((s, i) => this.tone(d, midiHz(64 + s), t + i * 0.09, 0.5, 'triangle', 0.12 * v, 0.01, 0.4));
        break;
      case 'lose':
        [7, 3, 0].forEach((s, i) => this.tone(d, midiHz(52 + s), t + i * 0.2, 0.4, 'triangle', 0.18 * v, 0.01, 0.3));
        break;
      case 'click': {
        const o = this.tone(d, 900, t, 0.04, 'sine', 0.08 * v);
        o.frequency.exponentialRampToValueAtTime(1400, t + 0.04);
        break;
      }
      case 'hover':
        this.tone(d, 1400, t, 0.025, 'triangle', 0.05 * v);
        break;
      case 'whoosh':
        this.noise(d, t, 0.35, 1200, 0.18 * v, 'bandpass');
        break;
      case 'coin':
        this.tone(d, midiHz(88), t, 0.06, 'triangle', 0.12 * v);
        this.tone(d, midiHz(95), t + 0.07, 0.25, 'sine', 0.12 * v);
        break;
      case 'chat':
        this.tone(d, 1000, t, 0.04, 'sine', 0.1 * v);
        break;
      default:
        break;
    }
  }
}

function makeDist(k) {
  const n = 1024, curve = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const x = (i * 2) / n - 1;
    curve[i] = ((1 + k) * x) / (1 + k * Math.abs(x));
  }
  return curve;
}

export const audio = new AudioEngine();
