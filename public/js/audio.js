// 原创程序化芯片音乐 + 音效（Web Audio，无需音频文件）
// 每首曲子由「和弦进行 + 随机种子」生成固定旋律：同一首歌每次听都一样，但各地图风格不同。

const SCALES = {
  major: [0, 2, 4, 5, 7, 9, 11],
  minor: [0, 2, 3, 5, 7, 8, 10],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  mixo: [0, 2, 4, 5, 7, 9, 10],
  harm: [0, 2, 3, 5, 7, 8, 11],
};

// 和弦进行用音阶级数（0 = I 级）
export const TRACKS = {
  lobby: { title: 'Standby', bpm: 92, root: 57, scale: 'minor', prog: [0, 5, 2, 6], seed: 7, lead: 'triangle', swing: 0, drums: 'soft', pad: true },
  meadow: { title: 'Ruins Run', bpm: 118, root: 55, scale: 'dorian', prog: [0, 6, 5, 6, 0, 3, 4, 4], seed: 3, lead: 'sawtooth', swing: 0, drums: 'four', pad: true },
  frost: { title: 'Cold Front', bpm: 104, root: 52, scale: 'minor', prog: [0, 5, 3, 4], seed: 21, lead: 'triangle', swing: 0, drums: 'soft', bell: true, pad: true },
  jungle: { title: 'Undergrowth', bpm: 112, root: 50, scale: 'dorian', prog: [0, 6, 0, 4], seed: 42, lead: 'sawtooth', swing: 0.12, drums: 'tribal', pad: true },
  neon: { title: 'Gridline', bpm: 126, root: 57, scale: 'minor', prog: [0, 5, 2, 6], seed: 99, lead: 'sawtooth', swing: 0, drums: 'four', pad: true },
  foundry: { title: 'Molten Core', bpm: 132, root: 52, scale: 'harm', prog: [0, 0, 5, 4], seed: 13, lead: 'sawtooth', swing: 0, drums: 'four', pad: true },
  desert: { title: 'Dust Devil', bpm: 108, root: 50, scale: 'harm', prog: [0, 1, 0, 6], seed: 57, lead: 'sawtooth', swing: 0.08, drums: 'tribal', pad: true },
  harbor: { title: 'Night Shift', bpm: 98, root: 53, scale: 'minor', prog: [0, 3, 5, 4], seed: 77, lead: 'triangle', swing: 0, drums: 'four', pad: true },
  temple: { title: 'Skyward', bpm: 116, root: 57, scale: 'mixo', prog: [0, 6, 3, 4], seed: 31, lead: 'triangle', swing: 0, drums: 'soft', bell: true, pad: true },
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

/** 把曲子参数编排成 16 小节 × 16 步的音符表 */
function compose(def) {
  const rnd = mulberry32(def.seed);
  const sc = SCALES[def.scale];
  const deg = (d, oct = 0) => {
    const o = Math.floor(d / sc.length);
    const k = ((d % sc.length) + sc.length) % sc.length;
    return def.root + sc[k] + 12 * (o + oct);
  };
  // 旋律动机：A、B 两个两小节乐句，按 A A' B A 组织
  const motif = () => {
    const notes = [];
    let pos = 2 + Math.floor(rnd() * 3);
    for (let s = 0; s < 32; s++) {
      const strong = s % 4 === 0;
      if (rnd() < (strong ? 0.75 : 0.32)) {
        pos += Math.round((rnd() - 0.5) * 4);
        pos = Math.max(-1, Math.min(9, pos));
        const len = rnd() < 0.3 ? 2 : 1;
        notes.push({ s, d: pos, len });
      }
    }
    return notes;
  };
  const A = motif(), B = motif();
  const vary = (m) => m.map((n) => ({ ...n, d: n.s >= 24 ? n.d + (rnd() < 0.5 ? 1 : -1) : n.d }));
  const form = [A, vary(A), B, A];
  const bars = 16;
  const steps = [];
  for (let bar = 0; bar < bars; bar++) {
    const chord = def.prog[bar % def.prog.length];
    const phrase = form[Math.floor(bar / 2) % 4];
    for (let s = 0; s < 16; s++) {
      const step = { lead: null, bass: null, arp: null, kick: false, snare: false, hat: false, bell: null };
      const gs = (bar % 2) * 16 + s;
      const n = phrase.find((x) => x.s === gs);
      if (n) step.lead = { m: deg(chord + n.d - (n.d % 2 ? 0 : 0), 1), len: n.len };
      // 低音
      if (s === 0 || s === 8 || (def.drums === 'four' && s % 4 === 2) || (def.drums === 'tribal' && s === 11)) {
        step.bass = deg(chord, -1) + (s === 8 && def.drums === 'pop' ? 7 : 0);
      }
      // 琶音
      if (s % 2 === 0) step.arp = deg(chord + [0, 2, 4, 2][(s / 2) % 4], 0);
      // 鼓
      switch (def.drums) {
        case 'four': step.kick = s % 4 === 0; step.snare = s === 4 || s === 12; step.hat = s % 2 === 1; break;
        case 'tribal': step.kick = s === 0 || s === 6 || s === 10; step.snare = s === 4 || s === 12 || s === 14; step.hat = s % 2 === 0; break;
        case 'soft': step.kick = s === 0 || s === 10; step.snare = s === 8; step.hat = s % 4 === 2; break;
        default: step.kick = s === 0 || s === 8 || s === 11; step.snare = s === 4 || s === 12; step.hat = s % 2 === 0; break;
      }
      if (def.bell && s === 0 && bar % 2 === 0) step.bell = deg(chord + 4, 2);
      if (s === 0) step.chord = [deg(chord, 0), deg(chord + 2, 0), deg(chord + 4, 0), deg(chord + 6, -1)];
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
      const delay = this.ctx.createDelay(1);
      delay.delayTime.value = 0.32;
      const fb = this.ctx.createGain();
      fb.gain.value = 0.28;
      const wet = this.ctx.createGain();
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
      if (st.lead) this.tone(bus, midiHz(st.lead.m), t, stepDur * st.lead.len * 0.9, def.lead, def.lead === 'sawtooth' ? 0.07 : 0.12, 0.01, 0.12);
      if (st.bass) this.tone(bus, midiHz(st.bass), t, stepDur * 1.8, 'sawtooth', 0.12, 0.005, 0.1);
      if (st.bass) this.tone(bus, midiHz(st.bass - 12), t, stepDur * 1.8, 'sine', 0.3, 0.005, 0.1);
      if (st.arp) this.tone(bus, midiHz(st.arp + 12), t, stepDur * 0.4, 'triangle', 0.035);
      if (def.pad && this.stepIdx % 16 === 0) {
        for (const m of st.chord || []) this.tone(bus, midiHz(m), t, stepDur * 15, 'sawtooth', 0.025, 0.6, 1.2);
      }
      if (st.bell) this.tone(bus, midiHz(st.bell), t, stepDur * 6, 'sine', 0.08, 0.002, 0.9);
      if (st.kick) this.kick(this.music, t, 0.6);
      if (st.snare) this.noise(this.music, t, 0.16, 1400, 0.16, 'bandpass');
      if (st.hat) this.noise(this.music, t, 0.025, 9000, 0.045, 'highpass');
      this.nextTime += stepDur;
      this.stepIdx = (this.stepIdx + 1) % this.steps.length;
    }
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

  /** 音效 */
  fx(name, opts = {}) {
    if (!this.ctx || this.ctx.state !== 'running') return;
    const t = this.ctx.currentTime + 0.005;
    const d = this.sfx;
    const v = opts.vol ?? 1;
    switch (name) {
      case 'place': {
        const o = this.tone(d, 330, t, 0.06, 'sine', 0.35 * v);
        o.frequency.exponentialRampToValueAtTime(180, t + 0.08);
        break;
      }
      case 'boom':
        this.noise(d, t, 0.45, 900, 0.7 * v, 'lowpass');
        this.kick(d, t, 0.9 * v);
        break;
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

export const audio = new AudioEngine();
