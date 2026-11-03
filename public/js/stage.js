// 菜单 3D 场景：暗色"角色展示台"（登录 / 大厅 / 房间界面背后实时渲染）
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { getMsaa, applyMsaa } from './gfx.js';
import { buildBlob, buildBomb, textSprite, envMapFor, glowTexture, canvasTexture, animateHat } from './scene.js';

const AMBER = '#ffb547';
const CYAN = '#36d6ff';
const rand = (a, b) => a + Math.random() * (b - a);

const VIEWS = {
  login: { pos: [0, 2.6, 8.2], look: [0, 1.15, 0], shift: -0.2 },
  lobby: { pos: [0.6, 2.9, 9.2], look: [0.6, 0.55, 0], shift: -0.12 },
  room: { pos: [0, 3.8, 11.5], look: [0, 1.0, -1.4], shift: 0 },
};

function hexShape(r) {
  const s = new THREE.Shape();
  for (let k = 0; k < 6; k++) {
    const a = Math.PI / 6 + (k * Math.PI) / 3;
    const x = Math.cos(a) * r, y = Math.sin(a) * r;
    if (k === 0) s.moveTo(x, y); else s.lineTo(x, y);
  }
  s.closePath();
  return s;
}

/** 六边形展示台：金属底座 + 发光边 */
function makePodium(radius, accent) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.ExtrudeGeometry(hexShape(radius), { depth: 0.32, bevelEnabled: true, bevelSize: 0.04, bevelThickness: 0.04, bevelSegments: 2 }),
    new THREE.MeshStandardMaterial({ color: '#1a1e28', metalness: 0.7, roughness: 0.35 }),
  );
  body.rotation.x = -Math.PI / 2;
  body.castShadow = body.receiveShadow = true;
  g.add(body);
  const top = new THREE.Mesh(
    new THREE.ShapeGeometry(hexShape(radius * 0.86)),
    new THREE.MeshStandardMaterial({ color: '#2a2f3c', metalness: 0.5, roughness: 0.25 }),
  );
  top.rotation.x = -Math.PI / 2;
  top.position.y = 0.37;
  top.receiveShadow = true;
  g.add(top);
  const edgeMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(accent).multiplyScalar(1.6) });
  const pts = [];
  for (let k = 0; k <= 6; k++) {
    const a = Math.PI / 6 + (k * Math.PI) / 3;
    pts.push(new THREE.Vector3(Math.cos(a) * radius * 0.93, 0.375, -Math.sin(a) * radius * 0.93));
  }
  const edge = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0), 60, 0.018, 6, false), edgeMat);
  g.add(edge);
  const strip = new THREE.Mesh(new THREE.TorusGeometry(radius * 0.98, 0.012, 6, 6), edgeMat);
  strip.rotation.x = Math.PI / 2;
  strip.rotation.z = Math.PI / 6;
  strip.position.y = 0.12;
  g.add(strip);
  return g;
}

export class MenuStage {
  constructor(parent) {
    this.parent = parent;
    const r = (this.renderer = new THREE.WebGLRenderer({ antialias: true }));
    r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.0;
    parent.appendChild(r.domElement);

    const scene = (this.scene = new THREE.Scene());
    scene.environment = envMapFor(r);
    scene.environmentIntensity = 0.35;
    scene.fog = new THREE.Fog('#0b0e16', 14, 34);
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.1, 120);
    this.camPos = new THREE.Vector3(...VIEWS.login.pos);
    this.camLook = new THREE.Vector3(...VIEWS.login.look);
    this.shift = VIEWS.login.shift;

    this.buildWorld();
    this.actors = [];
    this.pedestals = [];
    this.mode = null;
    this.clockLast = performance.now();
    this.t = 0;

    // 后期处理（泛光）先渲染到离屏缓冲：渲染器自带的 antialias 对它不生效，缓冲本身要开多重采样（设置里可选，默认 4×）
    this.composer = new EffectComposer(r, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: getMsaa() }));
    this.composer.addPass(new RenderPass(scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.7, 0.55, 0.78);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(parent);
    this.resize();
  }

  buildWorld() {
    const scene = this.scene;
    const sky = new THREE.Mesh(
      new THREE.SphereGeometry(60, 32, 16),
      new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, fog: false,
        uniforms: { top: { value: new THREE.Color('#06080d') }, mid: { value: new THREE.Color('#141a28') }, glow: { value: new THREE.Color('#3a2a1a') } },
        vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
        fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 glow; varying vec3 vP;
          void main(){ vec3 n = normalize(vP); float h = clamp(n.y*1.5+0.2,0.0,1.0);
          vec3 c = mix(mid, top, h); c += glow * pow(max(0.0, 1.0 - abs(n.y*3.0)), 3.0) * 0.6;
          gl_FragColor = vec4(c,1.0); }`,
      }),
    );
    scene.add(sky);

    scene.add(new THREE.HemisphereLight('#9fb4d8', '#0b0d12', 0.35));
    const key = new THREE.SpotLight('#ffe2c0', 26, 22, Math.PI / 7, 0.6, 1.6);
    key.position.set(1.5, 8, 4);
    key.target.position.set(0, 0.6, 0);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.bias = -0.0005;
    scene.add(key, key.target);
    const rim = new THREE.DirectionalLight(CYAN, 2.2);
    rim.position.set(-6, 4, -6);
    scene.add(rim);
    const rim2 = new THREE.DirectionalLight(AMBER, 1.4);
    rim2.position.set(6, 3, -5);
    scene.add(rim2);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(30, 64),
      new THREE.MeshStandardMaterial({ color: '#0d1017', metalness: 0.65, roughness: 0.28 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);
    this.rings = [];
    for (const [rad, col, op] of [[3.2, CYAN, 0.55], [5.4, AMBER, 0.25], [8.5, CYAN, 0.15]]) {
      const ring = new THREE.Mesh(new THREE.RingGeometry(rad, rad + 0.025, 128), new THREE.MeshBasicMaterial({ color: new THREE.Color(col).multiplyScalar(1.5), transparent: true, opacity: op }));
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.005;
      scene.add(ring);
      this.rings.push(ring);
    }
    const grid = new THREE.GridHelper(40, 40, '#1d2433', '#141a26');
    grid.position.y = 0.002;
    grid.material.transparent = true;
    grid.material.opacity = 0.5;
    scene.add(grid);

    this.bars = [];
    for (let i = 0; i < 26; i++) {
      const a = -1.25 + (i / 25) * 2.5;
      const h = rand(2.5, 6.5);
      const col = i % 5 === 0 ? AMBER : CYAN;
      const bar = new THREE.Mesh(new THREE.BoxGeometry(0.06, h, 0.06), new THREE.MeshBasicMaterial({ color: new THREE.Color(col).multiplyScalar(1.4), transparent: true, opacity: 0.6 }));
      bar.position.set(Math.sin(a) * 14, h / 2, -Math.cos(a) * 14);
      bar.userData.phase = Math.random() * 6;
      scene.add(bar);
      this.bars.push(bar);
    }
    const structMat = new THREE.MeshStandardMaterial({ color: '#111520', metalness: 0.6, roughness: 0.5 });
    for (const [x, z, w, h] of [[-9, -10, 3, 7], [9, -10, 3, 8], [-4.5, -13, 2.2, 10], [4.5, -13, 2.2, 9]]) {
      const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, 1.5), structMat);
      b.position.set(x, h / 2, z);
      scene.add(b);
      const line = new THREE.Mesh(new THREE.BoxGeometry(w * 0.9, 0.04, 0.02), new THREE.MeshBasicMaterial({ color: new THREE.Color(CYAN).multiplyScalar(1.3) }));
      line.position.set(x, h * 0.75, z + 0.77);
      scene.add(line);
    }

    const crateTex = canvasTexture(256, 256, (ctx, w) => {
      ctx.fillStyle = '#6b4a2b'; ctx.fillRect(0, 0, w, w);
      for (let i = 0; i < 4; i++) { ctx.fillStyle = i % 2 ? '#7a5532' : '#704e2e'; ctx.fillRect(18, 18 + i * 55, w - 36, 51); }
      ctx.strokeStyle = '#2e2116'; ctx.lineWidth = 18; ctx.strokeRect(9, 9, w - 18, w - 18);
      ctx.lineWidth = 12; ctx.beginPath(); ctx.moveTo(24, 24); ctx.lineTo(w - 24, w - 24); ctx.stroke();
    });
    const crateMat = new THREE.MeshStandardMaterial({ map: crateTex, roughness: 0.75 });
    const crateGeo = new RoundedBoxGeometry(0.9, 0.9, 0.9, 2, 0.04);
    for (const [x, y, z, r] of [[-4.2, 0.45, -1.6, 0.3], [-4.9, 0.45, -0.7, -0.2], [-4.5, 1.35, -1.2, 0.5], [4.4, 0.45, -1.8, -0.4], [5.1, 0.45, -0.6, 0.1]]) {
      const c = new THREE.Mesh(crateGeo, crateMat);
      c.position.set(x, y, z);
      c.rotation.y = r;
      c.castShadow = c.receiveShadow = true;
      scene.add(c);
    }
    this.bombs = [];
    this.setBombStyle(null, '');

    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(2.2, 8, 48, 1, true),
      new THREE.ShaderMaterial({
        transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
        uniforms: { color: { value: new THREE.Color('#ffd9a8') } },
        vertexShader: 'varying float vY; varying vec3 vN; varying vec3 vV; void main(){ vY = position.y; vec4 mv = modelViewMatrix*vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
        fragmentShader: 'uniform vec3 color; varying float vY; varying vec3 vN; varying vec3 vV; void main(){ float f = smoothstep(4.0,-4.0,vY) * 0.05; float edge = pow(abs(dot(vN, vV)), 1.5); gl_FragColor = vec4(color, f*edge); }',
      }),
    );
    cone.position.set(0, 4, 0);
    scene.add(cone);
    this.cone = cone;

    const n = 220;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = rand(-9, 9);
      pos[i * 3 + 1] = rand(0, 7);
      pos[i * 3 + 2] = rand(-8, 5);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.dust = new THREE.Points(geo, new THREE.PointsMaterial({ color: '#ffe2b8', size: 0.05, map: glowTexture(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.7 }));
    scene.add(this.dust);
  }

  resize() {
    const w = this.parent.clientWidth || 1, h = this.parent.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.applyShift();
  }

  applyShift() {
    const w = this.parent.clientWidth || 1, h = this.parent.clientHeight || 1;
    const s = w < 900 ? 0 : this.shift;
    this.camera.setViewOffset(w, h, -s * w, 0, w, h);
    this.camera.updateProjectionMatrix();
  }

  setView(name) {
    this.view = VIEWS[name];
    this.shift = this.view.shift;
    this.applyShift();
  }

  clearActors() {
    for (const a of this.actors) this.scene.remove(a.root);
    for (const p of this.pedestals) this.scene.remove(p);
    this.actors = [];
    this.pedestals = [];
  }

  makeActor(skin, hat, scale, label, accent) {
    const blob = buildBlob(skin, hat);
    const root = new THREE.Group();
    blob.group.scale.setScalar(scale);
    root.add(blob.group);
    if (label) {
      const sp = textSprite(label, accent || AMBER);
      sp.material.color.setScalar(0.72); // 压暗到泛光阈值以下：名字清楚但不发光
      sp.position.y = 1.18 * scale;
      sp.scale.multiplyScalar(Math.max(0.9, scale * 0.6));
      root.add(sp);
    }
    this.scene.add(root);
    const a = { root, blob, scale, phase: Math.random() * 10, hop: 0 };
    this.actors.push(a);
    return a;
  }

  heroPodium() {
    const pod = makePodium(1.25, CYAN);
    this.scene.add(pod);
    this.pedestals.push(pod);
    return pod;
  }

  showLogin(skin, hat) {
    const key = `login:${skin}:${hat}`;
    if (this.mode === key) return;
    const first = !this.mode || !this.mode.startsWith('login');
    this.mode = key;
    this.clearActors();
    this.setView('login');
    this.heroPodium();
    const a = this.makeActor(skin, hat, 1.8);
    a.root.position.set(0, 0.37, 0);
    a.turntable = true;
    if (!first) a.hop = 1;
  }

  setMsaa(n) { applyMsaa(this.composer, n); }

  /** 两边的装饰炸弹：用当前角色的颜色和正在使用的炸弹特效（未登录时用默认样式） */
  setBombStyle(skin, style) {
    const key = `${skin}:${style || ''}`;
    if (this.bombKey === key) return;
    this.bombKey = key;
    for (const b of this.bombs) {
      this.scene.remove(b.group);
      b.group.traverse((c) => {
        c.geometry?.dispose();
        if (c.material && c.material.map !== glowTexture()) c.material.dispose();
      });
    }
    this.bombs = [];
    for (const [x, z] of [[3.6, 0.6], [-3.4, 0.9]]) {
      const b = buildBomb(skin ?? (x > 0 ? 3 : 1), style || '');
      b.group.position.set(x, 0, z);
      b.group.scale.setScalar(1.15);
      this.scene.add(b.group);
      this.bombs.push(b);
    }
  }

  showLobby(user) {
    const key = `lobby:${user.id}:${user.skin}:${user.hat}:${user.name}:${user.level}`;
    if (this.mode === key) return;
    this.mode = key;
    this.clearActors();
    this.setView('lobby');
    this.heroPodium();
    const a = this.makeActor(user.skin, user.hat, 1.8, `${user.name}   LV.${user.level}`, AMBER);
    a.root.position.set(0, 0.37, 0);
    a.turntable = true;
  }

  showRoom(room, myId) {
    const key = 'room:' + JSON.stringify(room.members.map((m) => [m.id, m.skin, m.hat, m.ready, m.team, m.name])) + room.hostId + room.settings.mode;
    if (this.mode === key) return;
    this.mode = key;
    this.clearActors();
    this.setView('room');
    const team = room.settings.mode === 'team';
    for (let i = 0; i < 6; i++) {
      const k = i - 2.5;
      const x = k * 1.42, z = -1.2 - k * k * 0.2;
      const m = room.members[i];
      const ready = m && (m.ready || m.isBot || m.id === room.hostId);
      const accent = !m ? '#2a3140' : team ? ['#ff5a5f', '#3d9bff'][m.team] : m.id === myId ? AMBER : ready ? CYAN : '#56607a';
      const pod = makePodium(0.72, accent);
      pod.position.set(x, 0, z);
      pod.rotation.y = -k * 0.08;
      this.scene.add(pod);
      this.pedestals.push(pod);
      if (!m) continue;
      const a = this.makeActor(m.skin, m.hat, 1.3, (m.id === room.hostId ? '★ ' : '') + m.name, accent);
      a.root.position.set(x, 0.37, z);
      a.root.rotation.y = -k * 0.12;
      a.ready = ready;
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.parent.classList.remove('hidden');
    this.clockLast = performance.now();
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
    this.parent.classList.add('hidden');
  }

  frame() {
    const now = performance.now();
    const dt = Math.min(0.05, (now - this.clockLast) / 1000);
    this.clockLast = now;
    const t = (this.t += dt);

    if (this.view) {
      const v = this.view;
      this.camPos.lerp(new THREE.Vector3(v.pos[0] + Math.sin(t * 0.2) * 0.35, v.pos[1] + Math.sin(t * 0.27) * 0.08, v.pos[2]), Math.min(1, dt * 2.2));
      this.camLook.lerp(new THREE.Vector3(...v.look), Math.min(1, dt * 2.2));
    }
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camLook);

    for (const b of this.bars) b.material.opacity = 0.35 + (Math.sin(t * 1.3 + b.userData.phase) * 0.5 + 0.5) * 0.5;
    this.rings[0].material.opacity = 0.4 + Math.sin(t * 2) * 0.15;

    const arr = this.dust.geometry.attributes.position.array;
    for (let i = 0; i < arr.length; i += 3) {
      arr[i + 1] += dt * 0.12;
      arr[i] += Math.sin(t * 0.5 + i) * dt * 0.05;
      if (arr[i + 1] > 7) arr[i + 1] = 0;
    }
    this.dust.geometry.attributes.position.needsUpdate = true;

    for (const b of this.bombs) {
      b.group.rotation.y += dt * 0.4;
      b.spark.scale.setScalar(0.22 + Math.random() * 0.12);
    }

    for (const a of this.actors) {
      a.phase += dt;
      animateHat(a.blob.inner, t);
      if (a.turntable) a.root.rotation.y = Math.sin(t * 0.45) * 0.55;
      if (a.ready && Math.random() < dt * 0.12) a.hop = 1;
      let hopY = 0;
      if (a.hop > 0) {
        a.hop = Math.max(0, a.hop - dt * 2.2);
        hopY = Math.sin((1 - a.hop) * Math.PI) * 0.25;
      }
      const sq = 1 + Math.sin(a.phase * 2.4) * 0.025;
      a.blob.group.position.y = hopY * a.scale * 0.5;
      a.blob.body.scale.set(1 / Math.sqrt(sq), 0.92 * sq, 1 / Math.sqrt(sq));
    }

    this.composer.render();
  }
}
