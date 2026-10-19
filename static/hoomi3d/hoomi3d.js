// Hoomi: an interactive 3D robotic cat built from primitives with Three.js (no images, no 2D art, no network).
// Query: ?mode=hero (Welcome page, full cat) or ?mode=fab (floating bottom-right bust). Clicking asks the parent Streamlit page to open Ask Hoomi.
// Fur is "polished stylized": stacked noise-textured shells that read as soft fluff, not simulated hair.
import * as THREE from './three.module.min.js';

const MODE = new URLSearchParams(location.search).get('mode') === 'fab' ? 'fab' : 'hero';
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const stage = document.getElementById('stage');
const probe = window.__hoomi = { mode: MODE, ready: false, webgl: true, frames: 0, blinks: 0, clicks: 0, yaw: 0, pitch: 0, hover: false, opened: 0, reduced: REDUCED, tailAngle: 0 };

function openChat() {                                           // navigation only: ask the parent page to open Ask Hoomi
  probe.opened++;
  try { window.parent.postMessage({ type: 'hoomi-open-chat' }, '*'); } catch (e) {}
  try {                                                         // same-origin iframe: press the hidden Streamlit button directly
    const b = window.parent.document.querySelector('.st-key-hoomi_open_chat button');
    if (b) b.click();
  } catch (e) {}
}

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
} catch (e) { renderer = null; }
if (!renderer) {
  probe.webgl = false;
  document.getElementById('fallback').style.display = 'flex';
  stage.addEventListener('click', openChat);
  stage.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') openChat(); });
  throw new Error('WebGL unavailable: showing the plain fallback');
}

renderer.setPixelRatio(Math.min(devicePixelRatio || 1, MODE === 'fab' ? 2 : 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.setClearColor(0x000000, 0);
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
const FRAMING = MODE === 'fab' ? { y: 1.35, z: 6.1, look: 1.3 } : { y: 0.55, z: 9.6, look: 0.3 };

// ---------------------------------------------------------------- light
scene.add(new THREE.HemisphereLight(0xffffff, 0xf3c9dc, 1.15));
const key = new THREE.DirectionalLight(0xfff4ee, 2.1); key.position.set(3, 5, 6); scene.add(key);
const rim = new THREE.DirectionalLight(0x58b8ff, 2.4); rim.position.set(-5, 2.5, -4); scene.add(rim);
const fill = new THREE.PointLight(0xffb3d1, 14, 14); fill.position.set(2.5, -0.5, 4); scene.add(fill);

// ---------------------------------------------------------------- materials and helpers
const WHITE = new THREE.Color(0xfbf8fc), BLUSH = new THREE.Color(0xffc9dd), ROSE = new THREE.Color(0xf4a9c4);
const noise = (() => {                                          // soft elongated specks: the alpha mask that makes each shell look like tufts
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, 256, 256);
  let s = 7; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 2600; i++) {
    const x = rnd() * 256, y = rnd() * 256, r = 1.2 + rnd() * 2.6, a = 0.35 + rnd() * 0.65;
    const grad = g.createRadialGradient(x, y, 0, x, y, r); grad.addColorStop(0, `rgba(255,255,255,${a})`); grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad; g.beginPath(); g.ellipse(x, y, r, r * 1.7, 0, 0, 6.283); g.fill();
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(5, 3); return t;
})();
const sphereGeo = new THREE.SphereGeometry(1, 40, 28);

/** A fluffy ellipsoid: a solid core plus stacked shells. `tip` is the colour the fur fades to at its tips. */
function fluffy(rx, ry, rz, base = WHITE, tip = null, shells = 9, reach = 0.07, geo = sphereGeo) {
  const g = new THREE.Group();
  const core = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: base, roughness: 0.95, metalness: 0 }));
  core.scale.set(rx, ry, rz); g.add(core);
  for (let i = 1; i <= shells; i++) {
    const t = i / shells, m = new THREE.MeshStandardMaterial({
      color: base.clone().lerp(tip || base, t * 0.8), roughness: 1, metalness: 0, alphaMap: noise, alphaTest: 0.12 + t * 0.62, side: THREE.FrontSide });
    const s = new THREE.Mesh(geo, m); s.scale.set(rx * (1 + reach * t), ry * (1 + reach * t), rz * (1 + reach * t)); g.add(s);
  }
  return g;
}
// a rounded teardrop (lathe), flattened front to back: a soft rounded cat ear rather than a long bunny ear
const earGeo = new THREE.LatheGeometry(Array.from({ length: 25 }, (_, i) => { const y = (i / 24) * 0.74; return new THREE.Vector2(0.46 * Math.pow(Math.max(0, 1 - Math.pow(y / 0.74, 1.9)), 0.55), y); }), 36);
const metal = (color = 0xe3e9f7, rough = 0.28) => new THREE.MeshStandardMaterial({ color, metalness: 0.85, roughness: rough });
const glow = (color = 0x59c6ff) => new THREE.MeshBasicMaterial({ color, toneMapped: false });
const haloTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); gr.addColorStop(0, 'rgba(120,205,255,0.95)'); gr.addColorStop(0.35, 'rgba(70,160,255,0.35)'); gr.addColorStop(1, 'rgba(70,160,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c);
})();
const halo = (size, color = 0xffffff) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTex, color, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, toneMapped: false })); s.scale.set(size, size, 1); return s; };
const at = (obj, x, y, z) => { obj.position.set(x, y, z); return obj; };
const sized = (obj, x, y, z) => { obj.scale.set(x, y, z); return obj; };   // (Object3D.add returns the parent, so scale before adding)

// ---------------------------------------------------------------- the cat
const cat = new THREE.Group(); scene.add(cat);
const body = new THREE.Group(); cat.add(body);
body.add(at(fluffy(0.86, 0.98, 0.8), 0, -0.45, 0));
body.add(at(fluffy(0.5, 0.58, 0.3, BLUSH, ROSE, 7, 0.09), 0, -0.3, 0.62));             // blush chest
const core = at(new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.035, 12, 36), metal(0xf6b8cf, 0.3)), 0, -0.28, 0.93); body.add(core);
body.add(sized(at(new THREE.Mesh(sphereGeo, glow()), 0, -0.28, 0.93), 0.11, 0.11, 0.05));
const chestHalo = at(halo(0.7), 0, -0.28, 1.0); body.add(chestHalo);
for (const sx of [-1, 1]) {                                                              // paws and feet
  body.add(at(fluffy(0.27, 0.3, 0.27, WHITE, BLUSH, 6), sx * 0.5, -0.95, 0.5));
  body.add(sized(at(new THREE.Mesh(sphereGeo, new THREE.MeshStandardMaterial({ color: 0xff9fc0, roughness: 0.6 })), sx * 0.5, -1.1, 0.7), 0.1, 0.07, 0.06));
  body.add(at(fluffy(0.34, 0.22, 0.46, WHITE, BLUSH, 6), sx * 0.45, -1.38, 0.3));
}
const shoulder = (sx) => at(new THREE.Mesh(new THREE.SphereGeometry(0.1, 18, 14), metal()), sx * 0.8, -0.1, 0.1);
body.add(shoulder(-1), shoulder(1));

const tail = new THREE.Group(); tail.position.set(0.55, -1.05, -0.3); tail.rotation.set(-0.3, 0, -1.0); body.add(tail);
const tailSegs = []; {
  let parent = tail;
  for (let i = 0; i < 9; i++) {
    const seg = new THREE.Group(); seg.position.y = i === 0 ? 0 : 0.27; parent.add(seg);
    const r = 0.19 - i * 0.012;
    seg.add(at(i % 2 ? fluffy(r, r * 1.1, r, WHITE, BLUSH, 5, 0.1) : fluffy(r * 1.02, r * 1.1, r * 1.02, BLUSH, ROSE, 5, 0.1), 0, 0.13, 0));
    if (i % 3 === 2) { const ring = new THREE.Mesh(new THREE.TorusGeometry(r * 0.95, 0.025, 8, 24), metal(0xf6b8cf)); ring.rotation.x = Math.PI / 2; ring.position.y = 0.01; seg.add(ring); }
    tailSegs.push(seg); parent = seg;
  }
  const tip = new THREE.Mesh(sphereGeo, glow(0x7cd4ff)); tip.scale.setScalar(0.09); tip.position.y = 0.3; parent.add(tip);
  const th = halo(0.6); th.position.y = 0.3; parent.add(th);
}

const neck = new THREE.Group(); neck.position.set(0, 0.62, 0); cat.add(neck);
const collar = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.075, 14, 48), metal(0xf6b8cf, 0.3)); collar.rotation.x = Math.PI / 2; collar.position.set(0, 0.0, 0.02); neck.add(collar);
const pendant = at(new THREE.Mesh(new THREE.OctahedronGeometry(0.1), glow()), 0, -0.02, 0.76); pendant.scale.set(1, 1.3, 0.8); neck.add(pendant);
neck.add(at(halo(0.5), 0, -0.02, 0.8));

const head = new THREE.Group(); head.position.set(0, 1.05, 0); neck.add(head);        // rotates to follow the pointer
head.add(fluffy(1.24, 0.98, 1.04, WHITE, BLUSH, 11, 0.06));
for (const sx of [-1, 1]) head.add(at(fluffy(0.4, 0.34, 0.4, WHITE, BLUSH, 7, 0.1), sx * 0.92, -0.34, 0.34));   // cheek fluff

const ears = [];
for (const sx of [-1, 1]) {                                                              // rounded ears with blush insides and a glowing stud
  const ear = new THREE.Group(); ear.position.set(sx * 0.8, 0.66, -0.02); ear.rotation.z = -sx * 0.5; head.add(ear);
  ear.add(fluffy(1, 1, 0.5, WHITE, BLUSH, 8, 0.07, earGeo));
  const inner = new THREE.Mesh(earGeo, new THREE.MeshStandardMaterial({ color: 0xffb3cf, roughness: 0.85 })); inner.scale.set(0.62, 0.7, 0.3); inner.position.set(0, 0.03, 0.15); ear.add(inner);
  ear.add(at(new THREE.Mesh(new THREE.SphereGeometry(0.045, 14, 12), glow()), sx * 0.02, 0.1, 0.2));
  ears.push(ear);
}
const visor = at(new THREE.Mesh(sphereGeo, new THREE.MeshPhysicalMaterial({ color: 0x0a1233, metalness: 0.35, roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.05 })), 0, 0.0, 0.87);
visor.scale.set(0.86, 0.6, 0.3); head.add(visor);
const rimRing = at(new THREE.Mesh(new THREE.TorusGeometry(1, 0.045, 12, 64), metal(0xf6b8cf, 0.3)), 0, 0.0, 0.91); rimRing.scale.set(0.87, 0.61, 0.9); head.add(rimRing);
head.add(at(new THREE.Mesh(new THREE.OctahedronGeometry(0.075), glow()), 0, 0.76, 0.8));    // forehead gem

const eyes = []; const eyeRig = new THREE.Group(); head.add(eyeRig);
for (const sx of [-1, 1]) {
  const eye = new THREE.Group(); eye.position.set(sx * 0.32, 0.07, 1.13); eyeRig.add(eye);
  const outer = new THREE.Mesh(sphereGeo, glow(0x4db9ff)); outer.scale.set(0.19, 0.23, 0.045); eye.add(outer);
  const inner = at(new THREE.Mesh(sphereGeo, glow(0xd8f5ff)), 0, 0, 0.02); inner.scale.set(0.1, 0.13, 0.04); eye.add(inner);
  const spark = at(new THREE.Mesh(sphereGeo, glow(0xffffff)), -0.05, 0.08, 0.05); spark.scale.setScalar(0.034); eye.add(spark);
  eye.add(at(halo(0.95), 0, 0, 0.08));
  eyes.push(eye);
}
head.add(sized(at(new THREE.Mesh(sphereGeo, new THREE.MeshStandardMaterial({ color: 0xff8fb8, roughness: 0.4 })), 0, -0.13, 1.17), 0.075, 0.055, 0.05));   // nose
const mouthCurve = new THREE.CatmullRomCurve3([[-0.17, -0.2, 1.13], [-0.085, -0.285, 1.16], [0, -0.21, 1.165], [0.085, -0.285, 1.16], [0.17, -0.2, 1.13]].map((p) => new THREE.Vector3(...p)));
head.add(new THREE.Mesh(new THREE.TubeGeometry(mouthCurve, 24, 0.014, 8), glow(0x8fdcff)));

const phones = [];
for (const sx of [-1, 1]) {                                                              // side sensor discs
  const disc = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.14, 32), metal()); disc.rotation.z = Math.PI / 2; disc.position.set(sx * 1.27, -0.02, 0.0); head.add(disc);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.022, 10, 36), glow()); ring.rotation.y = Math.PI / 2; ring.position.set(sx * 1.355, -0.02, 0); head.add(ring);
  phones.push(ring);
}
const whiskers = [];
for (const sx of [-1, 1]) for (let i = 0; i < 3; i++) {
  const w = new THREE.Group(); w.position.set(sx * 0.98, -0.2 - i * 0.09, 0.62); head.add(w);
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.008, 0.68, 6), metal(0xf2f5ff, 0.2)); rod.rotation.z = Math.PI / 2; rod.position.x = sx * 0.34; w.add(rod);
  const tip = at(new THREE.Mesh(sphereGeo, glow(0xff9cc6)), sx * 0.68, 0, 0); tip.scale.setScalar(0.022); w.add(tip);
  w.userData = { base: sx * (0.28 - i * 0.2) * -1 * -1, sx, i }; w.rotation.z = w.userData.base * 1; whiskers.push(w);
}

const shadow = new THREE.Mesh(new THREE.CircleGeometry(1, 32), new THREE.MeshBasicMaterial({ map: haloTex, color: 0x6b7fd6, transparent: true, opacity: 0.22, depthWrite: false, toneMapped: false }));
shadow.rotation.x = -Math.PI / 2; shadow.position.set(0, -1.7, 0.2); shadow.scale.set(1.5, 1.1, 1); scene.add(shadow);
cat.position.y = -0.2;

// ---------------------------------------------------------------- interaction
const ptr = { x: 0, y: 0, down: false, startX: 0, startY: 0, moved: false, drag: 0 };
let hover = false, happyUntil = 0, jumpAt = -9, earTwitchAt = 3 + Math.random() * 3, nextBlink = 1.6 + Math.random() * 2, blinkPhase = -1, doubleBlink = false;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
function setPointer(e, doc) {                                   // normalised -1..1 in the window of the document that received the event
  const w = doc === 'parent' ? window.parent.innerWidth : innerWidth, h = doc === 'parent' ? window.parent.innerHeight : innerHeight;
  if (doc === 'parent') {                                       // convert the parent-window point to this iframe's centre-relative coordinates
    const r = window.frameElement ? window.frameElement.getBoundingClientRect() : { left: 0, top: 0, width: w, height: h };
    ptr.x = clamp((e.clientX - (r.left + r.width / 2)) / (w * 0.5), -1, 1);
    ptr.y = clamp((e.clientY - (r.top + r.height / 2)) / (h * 0.5), -1, 1);
  } else { ptr.x = clamp((e.clientX / w) * 2 - 1, -1, 1); ptr.y = clamp((e.clientY / h) * 2 - 1, -1, 1); }
}
addEventListener('pointermove', (e) => { setPointer(e); if (ptr.down) { const dx = e.clientX - ptr.startX; if (Math.abs(dx) > 4 || Math.abs(e.clientY - ptr.startY) > 4) ptr.moved = true; ptr.drag = clamp(dx / 160, -1, 1) * 0.9; } });
try { window.parent.document.addEventListener('pointermove', (e) => { if (!hover && !ptr.down) setPointer(e, 'parent'); }, { passive: true }); } catch (e) {}   // follow the cursor over the whole page
stage.addEventListener('pointerenter', () => { hover = probe.hover = true; });
stage.addEventListener('pointerleave', () => { hover = probe.hover = false; ptr.x = ptr.y = 0; });
stage.addEventListener('pointerdown', (e) => { ptr.down = true; ptr.moved = false; ptr.startX = e.clientX; ptr.startY = e.clientY; stage.setPointerCapture?.(e.pointerId); });
function react() { probe.clicks++; happyUntil = clock.elapsedTime + 1.4; jumpAt = clock.elapsedTime; }
stage.addEventListener('pointerup', (e) => {
  const wasClick = ptr.down && !ptr.moved; ptr.down = false; ptr.drag = 0; stage.releasePointerCapture?.(e.pointerId);
  if (wasClick) { react(); setTimeout(openChat, REDUCED ? 0 : 380); }
});
stage.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); react(); setTimeout(openChat, REDUCED ? 0 : 380); } });

// ---------------------------------------------------------------- loop
const clock = new THREE.Clock();
let yaw = 0, pitch = 0, bodyYaw = 0, visible = true;
document.addEventListener('visibilitychange', () => { visible = !document.hidden; });
function resize() {
  const w = stage.clientWidth || 300, h = stage.clientHeight || 300;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  const portrait = w / h < 0.8; camera.fov = MODE === 'fab' ? 30 : (portrait ? 38 : 30);
  camera.position.set(0, FRAMING.y, FRAMING.z); camera.lookAt(0, FRAMING.look, 0); camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage); resize();

function frame() {
  requestAnimationFrame(frame);
  if (!visible) return;
  const dt = Math.min(clock.getDelta() || 0.016, 0.05), t = clock.elapsedTime, amp = REDUCED ? 0.25 : 1;
  const happy = t < happyUntil, k = 1 - Math.pow(0.0015, dt);
  // look at the pointer (head) with a little idle wander when the pointer is still
  const idleX = Math.sin(t * 0.55) * 0.18 * amp, idleY = Math.sin(t * 0.8 + 1) * 0.07 * amp;
  const wantYaw = clamp(ptr.x, -1, 1) * 0.62 + idleX, wantPitch = clamp(ptr.y, -1, 1) * 0.36 + idleY;
  yaw += (wantYaw - yaw) * k; pitch += (wantPitch - pitch) * k;
  head.rotation.y = yaw; head.rotation.x = pitch; head.rotation.z = Math.sin(t * 0.9) * 0.025 * amp + (happy ? Math.sin(t * 14) * 0.06 : 0);
  eyeRig.position.x = yaw * 0.07; eyeRig.position.y = -pitch * 0.05;
  bodyYaw += ((ptr.down ? ptr.drag : yaw * 0.25) - bodyYaw) * k; body.rotation.y = bodyYaw; neck.rotation.y = bodyYaw * 0.6;
  // breathing, hover bob, jump
  const breathe = 1 + Math.sin(t * 1.8) * 0.014 * amp; body.scale.set(breathe, 1 + Math.sin(t * 1.8) * 0.02 * amp, breathe);
  const jt = t - jumpAt, jump = jt >= 0 && jt < 0.7 ? Math.sin((jt / 0.7) * Math.PI) * 0.55 : 0;
  cat.position.y = -0.2 + Math.sin(t * 1.35) * 0.07 * amp + jump; cat.rotation.z = jt >= 0 && jt < 0.7 ? Math.sin(jt * 18) * 0.05 : 0;
  shadow.scale.set(1.5 - jump * 0.5, 1.1 - jump * 0.35, 1); shadow.material.opacity = 0.22 - jump * 0.1;
  // tail sway: each segment bends a little more, with a travelling wave
  tailSegs.forEach((s, i) => { s.rotation.z = Math.sin(t * 1.7 - i * 0.55) * (0.1 + i * 0.012) * amp + 0.2; s.rotation.x = Math.sin(t * 1.1 - i * 0.4) * 0.04 * amp; });
  probe.tailAngle = tailSegs[4].rotation.z;
  // blink (and the occasional double blink), wider eyes when hovered or happy
  if (blinkPhase < 0 && t > nextBlink) { blinkPhase = 0; doubleBlink = Math.random() < 0.25; }
  let lid = 1;
  if (blinkPhase >= 0) { blinkPhase += dt / 0.16; lid = Math.abs(Math.cos(blinkPhase * Math.PI)); if (blinkPhase >= 1) { probe.blinks++; if (doubleBlink) { doubleBlink = false; blinkPhase = 0; } else { blinkPhase = -1; nextBlink = t + 2.2 + Math.random() * 3.2; } } }
  const wide = (hover ? 1.1 : 1) * (happy ? 0.62 : 1);                               // happy: eyes narrow into a smile-like crescent
  eyes.forEach((e) => { e.scale.set(1, Math.max(0.06, lid * wide), 1); e.children[3].material.opacity = 0.75 + Math.sin(t * 2.4) * 0.15; });
  // ears: twitch now and then, perk up on hover
  if (t > earTwitchAt) { earTwitchAt = t + 4 + Math.random() * 5; ears[Math.random() < 0.5 ? 0 : 1].userData.twitch = t; }
  ears.forEach((e, i) => { const sx = i ? 1 : -1, tw = e.userData.twitch !== undefined ? Math.max(0, 1 - (t - e.userData.twitch) / 0.35) : 0;
    e.rotation.z = -sx * 0.5 + (hover || happy ? -sx * 0.12 : 0) + Math.sin(tw * Math.PI * 3) * 0.12 * tw * sx; });
  whiskers.forEach((w) => { w.rotation.z = w.userData.base + Math.sin(t * 1.3 + w.userData.i + w.userData.sx) * 0.03 * amp; });
  phones.forEach((p) => p.scale.setScalar(1 + Math.sin(t * 3) * 0.05 * amp));
  pendant.rotation.y = t * 1.4; core.rotation.z = t * 0.8;
  probe.yaw = head.rotation.y; probe.pitch = head.rotation.x; probe.frames++; probe.eyeScale = eyes[0].scale.y;
  renderer.render(scene, camera);
}
probe.ready = true;
stage.style.cursor = 'pointer';
frame();
